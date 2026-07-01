"""AI Council: several models cross-critique the conversion of each PDF page.

The user supplies a list of API keys (each "provider:key", or a bare key =
Gemini). The keys become "seats". For every page the seats rotate through roles:

    Reader  -> first Markdown (Vietnamese text + LaTeX) from the page image
    Critic  -> compares Markdown to the image, lists mistakes (or says OK)
    Fixer   -> rewrites the corrected Markdown

This repeats for up to N rounds (the "circle"), so a different seat critiques
what another produced. With keys from different providers you get genuine
multi-model debate; with one provider it is self-critique + load spreading.
Everything degrades gracefully on error.

Supported providers: gemini (verified), openrouter / openai (OpenAI-compatible
vision), anthropic. Models are overridable via env vars.
"""
from __future__ import annotations

import base64
import logging
import os
import time

import fitz

from ..models import ConversionReport
from . import docx_builder, pdf_analyzer

logger = logging.getLogger("formudoc.council")

_GEMINI_MODEL = os.getenv("FORMUDOC_GEMINI_MODEL", "gemini-2.5-flash")
_OPENROUTER_MODEL = os.getenv("FORMUDOC_OPENROUTER_MODEL", "openai/gpt-4o-mini")
_OPENAI_MODEL = os.getenv("FORMUDOC_OPENAI_MODEL", "gpt-4o-mini")
_ANTHROPIC_MODEL = os.getenv("FORMUDOC_ANTHROPIC_MODEL", "claude-sonnet-4-6")
try:
    _TIMEOUT = max(15, int(os.getenv("FORMUDOC_API_TIMEOUT", "90")))
except ValueError:
    _TIMEOUT = 90
_KNOWN = ("gemini", "anthropic", "openai", "openrouter", "nvidia", "groq",
          "mistral", "github")

# OpenAI-compatible providers: provider -> (base_url, env_model, default_model)
_OAI = {
    "openai":     ("https://api.openai.com/v1", "FORMUDOC_OPENAI_MODEL", "gpt-4o-mini"),
    "openrouter": ("https://openrouter.ai/api/v1", "FORMUDOC_OPENROUTER_MODEL",
                   "openai/gpt-4o-mini"),
    "nvidia":     ("https://integrate.api.nvidia.com/v1", "FORMUDOC_NVIDIA_MODEL",
                   "meta/llama-3.2-90b-vision-instruct"),
    "groq":       ("https://api.groq.com/openai/v1", "FORMUDOC_GROQ_MODEL",
                   "meta-llama/llama-4-scout-17b-16e-instruct"),
    "mistral":    ("https://api.mistral.ai/v1", "FORMUDOC_MISTRAL_MODEL",
                   "pixtral-12b-2409"),
    "github":     ("https://models.inference.ai.azure.com", "FORMUDOC_GITHUB_MODEL",
                   "gpt-4o"),
}

_CONVERT = (
    "You are a faithful OCR transcriber. Transcribe EXACTLY what is printed on "
    "this ONE page to Markdown — nothing more, nothing less.\n"
    "STRICT RULES:\n"
    "- Do NOT solve anything. Do NOT add answers, explanations, or a solution "
    "guide (no 'HƯỚNG DẪN GIẢI', no 'Lời giải', no commentary). If it is not "
    "printed on the page, do NOT write it.\n"
    "- Do NOT repeat or duplicate any line, block, or problem.\n"
    "- Keep Vietnamese text exactly, with correct diacritics.\n"
    "- Preserve Vietnamese decimal commas exactly: write 1,4 — never 1.4.\n"
    "- STRICT text colour: if a piece of text is printed in a non-black colour, "
    "wrap EXACTLY that text as <span style=\"color:#RRGGBB\">...</span> using the "
    "closest hex colour (e.g. red heading -> #C00000, blue -> #0070C0). Black / "
    "default text: NO span. Do not colour anything that is actually black.\n"
    "- Write every formula as LaTeX ($...$ inline, $$...$$ display).\n"
    "- Preserve reading order and line breaks.\n"
    "- If the page is a TABLE / list / roster / grade sheet, output it as a "
    "PROPER Markdown table: a header row, then a |---| separator, then ONE row "
    "per record with every column aligned (STT, họ tên, ngày sinh, ... each in "
    "its own column). Do not merge columns into one cell.\n"
    "Output ONLY the page's Markdown, with no preamble or trailing notes."
)
_CRITIC = (
    "You are reviewing a Markdown transcription of the page in the image. "
    "Flag ONLY deviations from what is actually printed: missing/extra text, "
    "wrong Vietnamese diacritics, decimal points that should be commas, "
    "incorrect or incomplete LaTeX, wrong reading order, broken tables, wrong or "
    "missing text COLOUR (non-black text must be in a matching <span color> tag), and "
    "especially any DUPLICATED block or any added solution/answer that is NOT "
    "printed on the page. Do not ask for solutions to be added. "
    "If it faithfully matches the page, reply with exactly: OK\n"
    "Otherwise list the problems briefly.\n\nMarkdown:\n{md}"
)
_FIX = (
    "Rewrite the Markdown so it faithfully matches ONLY what is printed on the "
    "page in the image, fixing the listed problems. Do NOT add solutions, "
    "answers, or commentary. Do NOT duplicate any block. Vietnamese with correct "
    "diacritics; preserve decimal commas (1,4 not 1.4); keep non-black text in "
    "<span style=\"color:#RRGGBB\"> tags; all math as "
    "$...$/$$...$$; tables as Markdown. Output ONLY the corrected Markdown.\n\n"
    "Problems:\n{issues}\n\nCurrent Markdown:\n{md}"
)


def _infer_provider(key: str) -> str:
    """Guess the provider from a bare key's prefix, so users don't have to type
    a 'provider:' prefix. Explicit 'provider:key' always wins over this."""
    k = (key or "").strip()
    low = k.lower()
    if low.startswith("nvapi-"):
        return "nvidia"          # NVIDIA build.nvidia.com keys
    if low.startswith("sk-or-"):
        return "openrouter"
    if low.startswith("sk-ant-"):
        return "anthropic"
    if low.startswith("gsk_"):
        return "groq"
    if k.startswith("AIza"):
        return "gemini"          # classic Google API key
    if low.startswith("sk-"):
        return "openai"
    return "gemini"              # safe catch-all (also covers AQ.* Gemini keys)


def parse_keys(api_keys) -> list[tuple[str, str]]:
    seats = []
    for raw in api_keys or []:
        raw = (raw or "").strip()
        if not raw:
            continue
        if ":" in raw and raw.split(":", 1)[0].lower() in _KNOWN:
            prov, key = raw.split(":", 1)
            seats.append((prov.lower().strip(), key.strip()))
        else:
            seats.append((_infer_provider(raw), raw))   # auto-detect by prefix
    return seats


def _clean_md(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _usage(provider: str, j: dict) -> dict:
    """Normalise each provider's token-usage block to {prompt, completion, total}."""
    if provider == "gemini":
        u = j.get("usageMetadata", {}) or {}
        p = int(u.get("promptTokenCount", 0) or 0)
        c = int(u.get("candidatesTokenCount", 0) or 0)
        t = int(u.get("totalTokenCount", p + c) or (p + c))
        return {"prompt": p, "completion": c, "total": t}
    if provider == "anthropic":
        u = j.get("usage", {}) or {}
        p = int(u.get("input_tokens", 0) or 0)
        c = int(u.get("output_tokens", 0) or 0)
        return {"prompt": p, "completion": c, "total": p + c}
    u = j.get("usage", {}) or {}            # OpenAI-compatible (nvidia/groq/...)
    p = int(u.get("prompt_tokens", 0) or 0)
    c = int(u.get("completion_tokens", 0) or 0)
    t = int(u.get("total_tokens", p + c) or (p + c))
    return {"prompt": p, "completion": c, "total": t}


def _vision(seat, prompt: str, image_b64: str, timeout: int = None):
    """Return (text, usage). usage = {prompt, completion, total} token counts."""
    import requests
    timeout = timeout or _TIMEOUT
    provider, key = seat
    if provider == "gemini":
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{_GEMINI_MODEL}:generateContent")
        body = {"contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": image_b64}}]}],
            "generationConfig": {"temperature": 0.0}}
        r = requests.post(url, params={"key": key}, json=body, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        return j["candidates"][0]["content"]["parts"][0]["text"], _usage(provider, j)
    if provider in _OAI:
        import os
        base, env_model, default_model = _OAI[provider]
        model = os.getenv(env_model, default_model)
        content = [{"type": "text", "text": prompt},
                   {"type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"}}]
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": model, "temperature": 0.0, "max_tokens": 4096,
                                "messages": [{"role": "user", "content": content}]},
                          timeout=timeout)
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"], _usage(provider, j)
    if provider == "anthropic":
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key,
                                   "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": _ANTHROPIC_MODEL, "max_tokens": 4096,
                                "messages": [{"role": "user", "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image", "source": {
                                        "type": "base64", "media_type": "image/png",
                                        "data": image_b64}}]}]},
                          timeout=timeout)
        r.raise_for_status()
        j = r.json()
        return j["content"][0]["text"], _usage(provider, j)
    raise ValueError(f"unknown provider: {provider}")


import re as _re

def _count_formulas(md: str) -> int:
    display = len(_re.findall(r"\$\$.+?\$\$", md, _re.S))
    no_disp = _re.sub(r"\$\$.+?\$\$", "", md, flags=_re.S)
    inline = len(_re.findall(r"(?<!\$)\$[^$\n]+\$(?!\$)", no_disp))
    return display + inline


def _b64(path: str) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _fail_kind(exc) -> str:
    """Classify a seat failure: 'permanent' (bad key 401/403, quota 429 — disable
    immediately), 'timeout' (slow/overloaded — disable only after repeated hits),
    or 'other' (transient — just try another seat)."""
    if getattr(getattr(exc, "response", None), "status_code", None) in (401, 403, 429):
        return "permanent"
    try:
        import requests
        if isinstance(exc, (requests.exceptions.ReadTimeout,
                            requests.exceptions.ConnectTimeout,
                            requests.exceptions.ConnectionError)):
            return "timeout"
    except Exception:
        pass
    return "other"


def _ask(seats, start, prompt, image_b64, log, role, tally=None, dead=None, strikes=None):
    """Try seats starting at `start`, rotating, until one returns non-empty text.
    Seats in `dead` are skipped; a fatal failure adds the seat to `dead`."""
    n = len(seats)
    for k in range(n):
        idx = (start + k) % n
        if dead is not None and idx in dead:
            continue
        prov = seats[idx][0]
        try:
            t, usage = _vision(seats[idx], prompt, image_b64)
            if tally is not None and usage:
                acc = tally.setdefault(prov, {"prompt": 0, "completion": 0,
                                              "total": 0, "calls": 0})
                acc["prompt"] += usage["prompt"]
                acc["completion"] += usage["completion"]
                acc["total"] += usage["total"]
                acc["calls"] += 1
            if t and t.strip():
                if usage and usage["total"]:
                    log(f"   ↳ {role} seat{idx+1}({prov}) tokens: {usage['total']}"
                        f" (in {usage['prompt']} + out {usage['completion']})")
                return t, idx
            log(f"{role} seat{idx+1}({prov}) returned empty")
        except Exception as exc:
            kind = _fail_kind(exc)
            if dead is not None and kind == "permanent":
                dead.add(idx)
                log(f"{role} seat{idx+1}({prov}) FAILED: {exc} "
                    "— seat disabled for the rest of this run (key/quota)")
            elif dead is not None and kind == "timeout":
                if strikes is not None:
                    strikes[idx] = strikes.get(idx, 0) + 1
                if strikes is not None and strikes[idx] >= 2:
                    dead.add(idx)
                    log(f"{role} seat{idx+1}({prov}) timed out again "
                        "— seat disabled for the rest of this run")
                else:
                    log(f"{role} seat{idx+1}({prov}) timed out: {exc}")
            else:
                log(f"{role} seat{idx+1}({prov}) FAILED: {exc}")
    return None, None


def _alive_distinct(seats, dead) -> int:
    alive = [i for i in range(len(seats)) if not (dead and i in dead)]
    return len({seats[i][0] for i in alive})


def _extract_table_header(md: str):
    """Return the first Markdown table header row (a `| a | b |` line) or None."""
    for line in (md or "").split("\n"):
        s = line.strip()
        if s.startswith("|") and s.count("|") >= 2 and not _re.fullmatch(r"\|[-:\s|]+\|", s):
            return s
    return None


def _debate_page(image_b64: str, seats, rounds: int, page_no: int = 0,
                 log=lambda m: None, tally=None, dead=None, strikes=None,
                 table_hint=None) -> str:
    lbl = lambda i: f"seat{i+1}({seats[i][0]})"
    reader_prompt = _CONVERT
    if table_hint:
        reader_prompt = _CONVERT + (
            "\n\nCONTEXT — column consistency: an earlier page held a table whose "
            "header row is:\n" + table_hint + "\nIf THIS page CONTINUES that same "
            "table (more rows of the same roster/list), reuse EXACTLY these column "
            "headers, in this exact order and count, and start the page's table with "
            "this same header row, so all pages stack into ONE aligned table. Only "
            "use different columns if this page is clearly a different table.")
    resp, ridx = _ask(seats, 0, reader_prompt, image_b64, log, "reader", tally, dead, strikes)
    if resp is None:
        log(f"page {page_no}: ALL reader seats failed (check keys/quota)")
        return ""
    md = _clean_md(resp)
    log(f"page {page_no}: reader = {lbl(ridx)} ({len(md)} chars, "
        f"{_count_formulas(md)} formula(s))")
    for r in range(rounds):
        # Cross-critique only helps with >=2 DIFFERENT live models. Once a
        # provider dies (quota/timeout), stop — self-critique by one weak model
        # just burns time/tokens and tends to degrade the text.
        if _alive_distinct(seats, dead) < 2:
            log(f"page {page_no}: only one provider still alive — "
                "skipping further cross-critique")
            break
        issues, cidx = _ask(seats, ridx + 1 + r, _CRITIC.format(md=md),
                            image_b64, log, "critic", tally, dead, strikes)
        if issues is None:
            break
        if issues.strip().upper().startswith("OK") or len(issues.strip()) < 3:
            log(f"page {page_no} round {r+1}: critic {lbl(cidx)} -> OK (no more fixes)")
            break
        log(f"page {page_no} round {r+1}: critic {lbl(cidx)} -> fixes: "
            f"{' '.join(issues.split())[:80]}")
        fix, fidx = _ask(seats, cidx + 1, _FIX.format(issues=issues, md=md),
                         image_b64, log, "fixer", tally, dead, strikes)
        if fix is None:
            break
        md = _clean_md(fix)
        log(f"page {page_no} round {r+1}: fixer {lbl(fidx)} rewrote "
            f"({len(md)} chars, {_count_formulas(md)} formula(s))")
        time.sleep(0.4)
    return md



_STRONG_HALLUC_MARKERS = (
    "không phải đáp án chính thức",   # model confessing it invented the solution
    "của cá nhân chứ không phải",
    "(của cá nhân",
)


def _norm_block(b: str) -> str:
    import re
    t = re.sub(r"[*_#>`]", "", b)
    t = re.sub(r"\\(?:quad|qquad|[,;:! ])", "", t)
    t = re.sub(r"\s+", "", t).lower()
    return t


def _postprocess(md: str) -> str:
    """Deterministic, API-free safety net applied to every council output.

    Two jobs the model cannot be trusted to do consistently:
      1. Remove DUPLICATED blocks (a single model critiquing itself often
         re-emits whole problems). Near-duplicate long blocks are collapsed,
         keeping the first occurrence.
      2. Strip any model-INVENTED solution appendix (e.g. a 'HƯỚNG DẪN GIẢI'
         the model admits is '(của cá nhân ... không phải đáp án chính thức)').
    This makes faithfulness independent of the model behaving on a given run.
    """
    import difflib, re
    if not md or not md.strip():
        return md
    blocks = md.split("\n\n")
    out, seen = [], []
    for b in blocks:
        raw = b.strip()
        if not raw:
            continue
        low = raw.lower()
        if any(m in low for m in _STRONG_HALLUC_MARKERS):
            break  # cut the invented solution and everything after it
        if "=openxml" in raw:            # keep structural page-break blocks
            out.append(b)
            continue
        n = _norm_block(raw)
        dup = False
        if len(n) >= 60:
            for prev in seen:
                if len(prev) >= 60 and difflib.SequenceMatcher(None, n, prev).ratio() >= 0.92:
                    dup = True
                    break
        if dup:
            continue
        seen.append(n)
        out.append(b)
    # drop a now-orphaned solution heading left at the tail
    while out and re.sub(r"[*_#\\s]", "", out[-1]).lower() in ("hướngdẫngiải", "lờigiải"):
        out.pop()
    return docx_builder.normalize_dates("\n\n".join(out).strip())


def run(pdf_path, options, out_path, settings, asset_dir, progress,
        api_keys, rounds: int = 6) -> ConversionReport:
    seats = parse_keys(api_keys)
    if not seats:
        raise RuntimeError("no API keys provided for the council")
    analysis = pdf_analyzer.analyze(pdf_path)
    provs = ", ".join(sorted({p for p, _ in seats}))
    distinct = len({p for p, _ in seats})
    # Cross-critique only helps when >=2 DIFFERENT models can disagree. With a
    # single model, the "critic" and "fixer" are the same model judging itself,
    # which amplifies its own errors (duplication, invented solutions, decimal
    # drift) and triples API calls. So a lone provider does ONE faithful pass.
    eff_rounds = rounds if distinct >= 2 else 0
    mode_txt = (f"{distinct} models, {eff_rounds} cross-critique rounds"
                if eff_rounds else "single faithful pass (1 model, no self-critique)")
    progress(4, "council", f"AI council: {len(seats)} seat(s) [{provs}] — {mode_txt}")

    parts, n_formula, ok_pages = [], 0, 0
    ai_pages, ocr_pages = 0, 0        # AI-read pages vs offline-OCR-filled pages
    _ocr = [None]                     # lazy offline OCR engine (per-page fallback)
    table_hint = None   # last table header, reused to keep columns consistent
    tally = {}   # provider -> token usage accumulator
    dead = set()      # seat indices disabled mid-run (quota/auth)
    strikes = {}      # seat -> consecutive timeout count
    with fitz.open(pdf_path) as doc:
        n = doc.page_count
        for i, page in enumerate(doc):
            progress(int(8 + 86 * i / max(n, 1)), "council",
                     f"Council debating page {i + 1}/{n}")
            img = f"{asset_dir}/page_{i}.png"
            page.get_pixmap(dpi=settings.render_dpi).save(img)
            pct = int(8 + 86 * i / max(n, 1))
            page_log = lambda m, _p=pct: progress(_p, "council", m)
            try:
                md = _debate_page(_b64(img), seats, eff_rounds, page_no=i + 1,
                                  log=page_log, tally=tally, dead=dead,
                                  strikes=strikes, table_hint=table_hint)
            except Exception as exc:  # pragma: no cover
                logger.warning("council page %d failed: %s", i, exc)
                md = ""
            if md.strip():
                ok_pages += 1
                ai_pages += 1
            else:
                # HYBRID: don't throw away the good AI pages. OCR just THIS failed
                # page (offline) so it isn't empty and the AI pages survive.
                try:
                    if _ocr[0] is None:
                        from .ocr_engine import get_ocr_engine
                        _ocr[0] = get_ocr_engine()
                    _lines = _ocr[0].ocr_image(img)
                    _txt = "\n".join(l.text for l in _lines if (l.text or "").strip())
                    if _txt.strip():
                        md = _txt
                        ok_pages += 1
                        ocr_pages += 1
                        page_log(f"page {i + 1}: AI empty -> filled by offline OCR "
                                 f"({len(_txt)} chars)")
                except Exception as _e:  # pragma: no cover
                    logger.warning("per-page OCR fallback failed: %s", _e)
            n_formula += _count_formulas(md)
            parts.append(md)
            _h = _extract_table_header(md)      # thread columns to the next page
            if _h:
                table_hint = _h

    markdown = ("\n\n" + docx_builder._pagebreak() + "\n\n").join(p for p in parts if p.strip())
    markdown = _postprocess(markdown)

    # MANDATORY RULE: the AI council must convert EVERY page. If even one page
    # came back empty (API quota/tokens ran out, seats died mid-document, or
    # timeouts), we do NOT ship a half-finished document. We abort so the
    # pipeline falls back to the standard OFFLINE pipeline, which reliably
    # converts ALL pages. (This also covers the "0-byte Word" case.)
    # Only fall back to the whole-document offline pipeline if the AI produced
    # NOTHING usable. If it read at least one page, we keep those pages and the
    # rest were OCR-filled above -> the AI work is never wasted.
    if ai_pages == 0 or len(markdown.strip()) < 5:
        raise RuntimeError(
            f"AI council produced no usable page (seats: {provs}) — exhausted "
            "quota/tokens or dead seats. Falling back to the offline pipeline.")

    progress(92, "build", "Building Word + Markdown from council output")
    docx_builder.markdown_to_docx(markdown, out_path, settings)
    try:
        with open(os.path.splitext(out_path)[0] + ".md", "w", encoding="utf-8") as fh:
            fh.write(markdown)
    except Exception:
        pass

    report = ConversionReport(pages=analysis.page_count,
                              classification=analysis.classification)
    report.detected_formulas = n_formula
    report.editable_equations = n_formula
    report.detected_text_blocks = markdown.count("\n\n") + 1
    report.engines_used = {"recognizer": f"council({len(seats)} seats: {provs})",
                           "docx": "pandoc"}
    warn = [f"AI council: {len(seats)} seat(s) [{provs}] — {mode_txt}."]
    if ocr_pages:
        warn.append(f"{ai_pages}/{n} page(s) read by AI; {ocr_pages} page(s) "
                    "filled by offline OCR (AI quota/timeout on those pages).")
    grand = 0
    for prov, u in sorted(tally.items()):
        grand += u["total"]
        line = (f"Tokens · {prov}: {u['total']:,} total "
                f"(in {u['prompt']:,} + out {u['completion']:,}) over {u['calls']} call(s)")
        warn.append(line)
        progress(97, "build", line)
    if grand:
        progress(97, "build", f"Total tokens used this conversion: {grand:,}")
    report.warnings = warn
    progress(98, "build", "Document assembled (council)")
    return report
