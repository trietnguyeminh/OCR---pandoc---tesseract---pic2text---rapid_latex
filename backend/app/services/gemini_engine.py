"""Gemini full-page recognizer with a verify-and-fix loop (opt-in, needs API key).

For each page image we ask Gemini to produce Markdown (Vietnamese text + LaTeX),
then run up to N refinement passes: Gemini checks its own Markdown against the
image and either replies DONE or returns a corrected version. Gemini reads
Vietnamese and mathematics natively, so this is the highest-quality path when a
(free) API key is configured. Everything degrades gracefully on error.
"""
from __future__ import annotations

import base64
import logging
import time

import fitz

from ..config import capabilities, gemini_auth, gemini_model, gemini_passes
from ..models import ConversionReport
from . import docx_builder, pdf_analyzer

logger = logging.getLogger("formudoc.gemini")

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_CONVERT_PROMPT = (
    "You are converting ONE page of a Vietnamese math exam / solution PDF to "
    "Markdown.\n"
    "Rules:\n"
    "- Keep the Vietnamese text exactly, with correct diacritics.\n"
    "- Write every mathematical expression as LaTeX: inline math as $...$, "
    "display equations as $$...$$.\n"
    "- Preserve the reading order and the paragraph/line structure of the page.\n"
    "- Reproduce tables as GitHub-flavoured Markdown tables.\n"
    "- Do NOT add any commentary. Output ONLY the Markdown of this page."
)


def is_available() -> bool:
    return capabilities().get("gemini", False)


def _b64(image_path: str) -> str:
    with open(image_path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _call(prompt: str, image_b64: str, key: str, model: str) -> str:
    import requests
    url = _ENDPOINT.format(model=model)
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": image_b64}},
            ]
        }],
        "generationConfig": {"temperature": 0.0},
    }
    r = requests.post(url, params={"key": key}, json=body, timeout=120)
    r.raise_for_status()
    js = r.json()
    return js["candidates"][0]["content"]["parts"][0]["text"]


def _clean_md(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _convert_page(image_b64: str, key: str, model: str, passes: int) -> str:
    md = _clean_md(_call(_CONVERT_PROMPT, image_b64, key, model))
    for _ in range(max(0, passes - 1)):
        time.sleep(0.5)
        review = (
            "Below is a Markdown conversion of the exam page in the image. "
            "Check it carefully against the image. If ALL Vietnamese text and "
            "EVERY formula are correct and complete, reply with exactly: DONE\n"
            "Otherwise output the corrected FULL Markdown (only the Markdown).\n\n"
            "Current Markdown:\n" + md
        )
        try:
            resp = _call(review, image_b64, key, model).strip()
        except Exception as exc:  # pragma: no cover
            logger.warning("Gemini refine call failed: %s", exc)
            break
        if resp.upper().startswith("DONE") or len(resp) < 5:
            break
        md = _clean_md(resp)
    return md


def run(pdf_path, options, out_path, settings, asset_dir, progress) -> ConversionReport:
    key = gemini_auth()
    model = gemini_model()
    passes = gemini_passes()
    analysis = pdf_analyzer.analyze(pdf_path)
    progress(5, "gemini", f"Gemini ({model}) reading pages, {passes} pass(es) each")

    parts: list[str] = []
    n_formula = 0
    with fitz.open(pdf_path) as doc:
        n = doc.page_count
        for i, page in enumerate(doc):
            progress(int(8 + 86 * i / max(n, 1)), "gemini",
                     f"Gemini reading page {i + 1}/{n}")
            img = f"{asset_dir}/page_{i}.png"
            page.get_pixmap(dpi=settings.render_dpi).save(img)
            try:
                md = _convert_page(_b64(img), key, model, passes)
            except Exception as exc:  # pragma: no cover
                logger.warning("Gemini page %d failed: %s", i, exc)
                md = ""
            n_formula += md.count("$$") // 2
            parts.append(md)

    markdown = ("\n\n" + docx_builder._pagebreak() + "\n\n").join(p for p in parts if p.strip())
    progress(92, "build", "Building Word + Markdown from Gemini output")
    docx_builder.markdown_to_docx(markdown, out_path, settings)
    # write the .md sidecar
    import os
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
    report.engines_used = {"recognizer": f"gemini:{model} ({passes}x)", "docx": "pandoc"}
    report.warnings = ["Gemini full-page mode: best text+formula quality; "
                       "uses the Gemini API (key required)."]
    progress(98, "build", "Document assembled (Gemini)")
    return report
