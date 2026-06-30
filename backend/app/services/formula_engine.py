"""Tier 3 — Formula-aware conversion.

Adapter interface so model availability is irrelevant to the pipeline:

    BaseFormulaEngine
      |- Pix2TexFormulaEngine        (LaTeX-OCR; image formula -> LaTeX)
      |- HeuristicFormulaEngine       (no model: keep unicode/text math)
      |- FallbackImageFormulaEngine   (last resort: crop -> image, never lose it)

Ideas from "Image-to-Markup Generation" (im2markup) and Nougat: a crop of the
formula region is turned into LaTeX markup; if confidence is too low we keep the
rendered image so the equation is *never* dropped.
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..config import capabilities

logger = logging.getLogger("formudoc.formula")

# Unicode ranges / symbols that strongly suggest mathematics.
_MATH_CHARS = set("∑∫∮√∞≈≠≤≥±∓×÷→←↔⇒⇔∂∇∆∈∉⊂⊆∪∩∀∃∅·∝∥⊥°ℓ"
                  "αβγδεζηθικλμνξοπρστυφχψω"
                  "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"
                  "⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉")
_MATH_FONT_HINTS = ("cmmi", "cmsy", "cmex", "math", "symbol", "stix", "mathjax",
                    "msam", "msbm", "rsfs", "esint")


@dataclass
class FormulaResult:
    latex: str | None
    confidence: float
    image_path: str | None = None


def looks_like_formula(text: str, font_names: list[str] | None = None) -> bool:
    """Heuristic detector used by the layout extractor on the text layer."""
    if not text:
        return False
    fonts = " ".join(font_names or []).lower()
    if any(h in fonts for h in _MATH_FONT_HINTS):
        return True
    stripped = text.strip()
    if not stripped:
        return False
    math_hits = sum(1 for c in stripped if c in _MATH_CHARS)
    density = math_hits / max(len(stripped), 1)
    # short line with operators/relations or several math glyphs
    operatorish = bool(re.search(r"[=<>]\s*[-\w(]", stripped)) and len(stripped) < 120
    return density > 0.06 or (math_hits >= 2 and len(stripped) < 80) or operatorish


def unicode_to_latex(text: str) -> str:
    """Best-effort conversion of unicode math to a LaTeX-ish string.

    Used when we have a text-layer formula but no OCR model. It is intentionally
    conservative — good enough for pandoc to emit an editable OMML equation.
    """
    table = {
        "∑": r"\sum", "∫": r"\int", "∮": r"\oint", "√": r"\sqrt ", "∞": r"\infty",
        "≈": r"\approx", "≠": r"\neq", "≤": r"\leq", "≥": r"\geq", "±": r"\pm",
        "∓": r"\mp", "×": r"\times", "÷": r"\div", "→": r"\to", "←": r"\leftarrow",
        "↔": r"\leftrightarrow", "⇒": r"\Rightarrow", "⇔": r"\Leftrightarrow",
        "∂": r"\partial", "∇": r"\nabla", "∆": r"\Delta", "∈": r"\in",
        "∉": r"\notin", "⊂": r"\subset", "⊆": r"\subseteq", "∪": r"\cup",
        "∩": r"\cap", "∀": r"\forall", "∃": r"\exists", "∅": r"\emptyset",
        "·": r"\cdot", "∝": r"\propto", "°": r"^\circ", "ℓ": r"\ell",
        # unicode minus, fraction slash, prime
        "−": "-", "⁄": "/", "′": "'", "″": "''", "·": r"\cdot",
        # subscript letters
        "ₐ": "_a", "ₑ": "_e", "ₒ": "_o", "ₓ": "_x", "ₕ": "_h", "ₖ": "_k",
        "ₗ": "_l", "ₘ": "_m", "ₙ": "_n", "ₚ": "_p", "ₛ": "_s", "ₜ": "_t",
        "ᵢ": "_i", "ⱼ": "_j", "ᵣ": "_r", "ᵤ": "_u", "ᵥ": "_v",
        # superscript letters
        "ⁿ": "^n", "ⁱ": "^i",
        "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
        "ε": r"\epsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta",
        "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu",
        "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau",
        "υ": r"\upsilon", "φ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
        "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda",
        "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma", "Φ": r"\Phi", "Ψ": r"\Psi",
        "Ω": r"\Omega",
        "⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4", "⁵": "^5",
        "⁶": "^6", "⁷": "^7", "⁸": "^8", "⁹": "^9",
        "₀": "_0", "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4", "₅": "_5",
        "₆": "_6", "₇": "_7", "₈": "_8", "₉": "_9",
    }
    # give every "\command" a trailing space so it can't fuse with the next
    # letter (e.g. unicode "x n" -> "\times n", not "\timesn").
    table = {k: (v + " " if re.fullmatch(r"\\[a-zA-Z]+", v) else v)
             for k, v in table.items()}
    out = []
    for ch in text:
        out.append(table.get(ch, ch))
    latex = "".join(out)
    # merge consecutive single-char subscripts/superscripts: _1_2 -> _{12}
    latex = re.sub(r"(_)([A-Za-z0-9])(?:_([A-Za-z0-9]))+",
                   lambda m: "_{" + re.sub(r"_", "", m.group(0)) + "}", latex)
    latex = re.sub(r"(\^)([A-Za-z0-9])(?:\^([A-Za-z0-9]))+",
                   lambda m: "^{" + re.sub(r"\^", "", m.group(0)) + "}", latex)
    return latex.strip()


class BaseFormulaEngine(ABC):
    name = "base"

    @abstractmethod
    def to_latex(self, image_path: str, text_hint: str = "") -> FormulaResult:
        ...


class Pix2TexFormulaEngine(BaseFormulaEngine):
    """LaTeX-OCR. Lazily loaded; only used when `pix2tex` is installed."""

    name = "pix2tex"

    def __init__(self) -> None:
        from pix2tex.cli import LatexOCR

        self._model = LatexOCR()

    def to_latex(self, image_path: str, text_hint: str = "") -> FormulaResult:
        from PIL import Image

        try:
            latex = self._model(Image.open(image_path))
            conf = 0.85 if latex and len(latex) > 1 else 0.3
            return FormulaResult(latex=latex, confidence=conf, image_path=image_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("pix2tex failed: %s", exc)
            return FormulaResult(latex=None, confidence=0.0, image_path=image_path)


class HeuristicFormulaEngine(BaseFormulaEngine):
    """No-model engine: convert the text-layer unicode math to LaTeX-ish markup."""

    name = "heuristic"

    def to_latex(self, image_path: str, text_hint: str = "") -> FormulaResult:
        if text_hint.strip():
            latex = unicode_to_latex(text_hint)
            # scrambled MathType text layers (PUA glyphs / many line breaks) give
            # garbage LaTeX -> keep confidence low so we fall back to an image.
            scrambled = (text_hint.count("\n") >= 2
                         or any(0xE000 <= ord(c) <= 0xF8FF for c in text_hint))
            if scrambled:
                conf = 0.2
            elif any(c in _MATH_CHARS for c in text_hint):
                conf = 0.6
            else:
                conf = 0.4
            return FormulaResult(latex=latex, confidence=conf, image_path=image_path)
        return FormulaResult(latex=None, confidence=0.0, image_path=image_path)


class MathpixFormulaEngine(BaseFormulaEngine):
    """Mathpix OCR: image -> LaTeX / Mathpix-Markdown (text + inline math).

    Handles lines that mix Vietnamese text and mathematics, which is exactly the
    case in these exam solutions. Returns Mathpix Markdown with math delimited by
    ``$...$`` / ``$$...$$`` so pandoc turns it into editable Word equations.
    Uses only urllib (no heavy deps) so it bundles cleanly.
    """

    name = "mathpix"
    _ENDPOINT = "https://api.mathpix.com/v3/text"

    def __init__(self) -> None:
        from ..config import mathpix_credentials
        self.app_id, self.app_key = mathpix_credentials()
        if not (self.app_id and self.app_key):
            raise RuntimeError("Mathpix credentials not configured")
        self._cache: dict[str, FormulaResult] = {}

    def to_latex(self, image_path: str, text_hint: str = "") -> FormulaResult:
        import base64
        import hashlib
        import json
        import urllib.request

        if not image_path:
            return FormulaResult(latex=None, confidence=0.0)
        try:
            raw = open(image_path, "rb").read()
        except Exception:
            return FormulaResult(latex=None, confidence=0.0, image_path=image_path)

        key = hashlib.md5(raw).hexdigest()
        if key in self._cache:
            return self._cache[key]

        b64 = base64.b64encode(raw).decode()
        body = json.dumps({
            "src": f"data:image/png;base64,{b64}",
            "formats": ["text"],
            "math_inline_delimiters": ["$", "$"],
            "math_display_delimiters": ["$$", "$$"],
            "rm_spaces": True,
        }).encode()
        req = urllib.request.Request(
            self._ENDPOINT, data=body,
            headers={"app_id": self.app_id, "app_key": self.app_key,
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # network / auth / quota -> keep the image
            logger.warning("Mathpix request failed: %s", exc)
            res = FormulaResult(latex=None, confidence=0.0, image_path=image_path)
            self._cache[key] = res
            return res

        text = (data.get("text") or "").strip()
        conf = float(data.get("confidence", 0.0) or 0.0)
        if not text:
            res = FormulaResult(latex=None, confidence=0.0, image_path=image_path)
        else:
            # Mathpix Markdown is paragraph-ready (text + $..$ math).
            res = FormulaResult(latex=text, confidence=max(conf, 0.7),
                                image_path=image_path)
        self._cache[key] = res
        return res


class FallbackImageFormulaEngine(BaseFormulaEngine):
    """Never loses a formula: just keeps the crop as an image."""

    name = "image_fallback"

    def to_latex(self, image_path: str, text_hint: str = "") -> FormulaResult:
        return FormulaResult(latex=None, confidence=0.0, image_path=image_path)


class Pix2TextFormulaEngine(BaseFormulaEngine):
    """Offline formula OCR via Pix2Text's MFR (recognize_formula). No token.

    Loaded with a Chinese/English text-OCR config (cnocr) on purpose so it does
    NOT require easyocr -- we only use its math recogniser on formula crops.
    """

    name = "pix2text_formula"

    def __init__(self) -> None:
        from pix2text import Pix2Text
        self._p2t = Pix2Text.from_config(
            total_configs={"text_formula": {"languages": ("en", "ch_sim")}},
            enable_formula=True, enable_table=False, device="cpu")

    def to_latex(self, image_path: str, text_hint: str = "") -> FormulaResult:
        try:
            latex = self._p2t.recognize_formula(image_path)
            if isinstance(latex, (list, tuple)):
                latex = "".join(str(x) for x in latex)
            latex = (latex or "").strip()
            conf = 0.85 if len(latex) > 1 else 0.2
            return FormulaResult(latex=latex or None, confidence=conf,
                                 image_path=image_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("pix2text formula failed: %s", exc)
            return FormulaResult(latex=None, confidence=0.0, image_path=image_path)


class RapidLatexFormulaEngine(BaseFormulaEngine):
    """Offline LaTeX-OCR via RapidLaTeXOCR (ONNX, no PyTorch). No token needed.

    Same underlying model family as pix2tex but lighter to install/run. Models
    are downloaded once on first init. Best on *isolated* formula crops.
    """

    name = "rapid_latex"

    def __init__(self) -> None:
        try:
            from ..vendor.rapid_latex_ocr import LaTeXOCR   # bundled (works on py3.13+)
        except Exception:
            from rapid_latex_ocr import LaTeXOCR            # pip-installed fallback
        import os
        from pathlib import Path
        # Prefer models the user dropped in ~/FormuDoc/rapid_latex_models/ (or
        # $FORMUDOC_RAPID_LATEX_DIR) so they don't have to touch site-packages.
        d = os.getenv("FORMUDOC_RAPID_LATEX_DIR")
        base = Path(d) if d else Path.home() / "FormuDoc" / "rapid_latex_models"
        f = {n: base / n for n in ("image_resizer.onnx", "encoder.onnx",
                                   "decoder.onnx", "tokenizer.json")}
        if all(p.exists() for p in f.values()):
            self._model = LaTeXOCR(
                image_resizer_path=str(f["image_resizer.onnx"]),
                encoder_path=str(f["encoder.onnx"]),
                decoder_path=str(f["decoder.onnx"]),
                tokenizer_json=str(f["tokenizer.json"]))
        else:
            self._model = LaTeXOCR()   # package's auto-downloaded models

    def to_latex(self, image_path: str, text_hint: str = "") -> FormulaResult:
        try:
            out = self._model(image_path)
            latex = out[0] if isinstance(out, (tuple, list)) else out
            latex = (latex or "").strip()
            conf = 0.82 if len(latex) > 1 else 0.2
            return FormulaResult(latex=latex or None, confidence=conf,
                                 image_path=image_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("RapidLaTeXOCR failed: %s", exc)
            return FormulaResult(latex=None, confidence=0.0, image_path=image_path)


class ChainFormulaEngine(BaseFormulaEngine):
    """Tries several engines on the cropped image; first confident LaTeX wins.

    Order is decided in :func:`get_formula_engine`: pix2tex (offline) ->
    rapid_latex (offline) -> heuristic (text layer). Anything failing or low
    confidence falls through to an image crop in the docx builder.
    """

    def __init__(self, engines: list[BaseFormulaEngine]) -> None:
        self.engines = engines
        self.name = "+".join(e.name for e in engines) or "none"

    def to_latex(self, image_path: str, text_hint: str = "") -> FormulaResult:
        best = FormulaResult(latex=None, confidence=0.0, image_path=image_path)
        for eng in self.engines:
            try:
                r = eng.to_latex(image_path, text_hint=text_hint)
            except Exception:  # pragma: no cover
                continue
            if r.latex and r.confidence >= 0.5:
                return r
            if r.confidence > best.confidence:
                best = r
        return best


def get_formula_engine(prefer_ai: bool = True) -> BaseFormulaEngine:
    caps = capabilities()
    chain: list[BaseFormulaEngine] = []
    if prefer_ai and caps.get("pix2tex"):
        try:
            chain.append(Pix2TexFormulaEngine())
            logger.info("Formula engine: pix2tex (offline) enabled")
        except Exception as exc:  # pragma: no cover
            logger.warning("pix2tex unavailable: %s", exc)
    if prefer_ai and caps.get("pix2text"):
        try:
            chain.append(Pix2TextFormulaEngine())
            logger.info("Formula engine: pix2text MFR (offline) enabled")
        except Exception as exc:  # pragma: no cover
            logger.warning("pix2text formula engine unavailable: %s", exc)
    if prefer_ai and caps.get("rapid_latex"):
        try:
            chain.append(RapidLatexFormulaEngine())
            logger.info("Formula engine: RapidLaTeXOCR (offline) enabled")
        except Exception as exc:  # pragma: no cover
            logger.warning("RapidLaTeXOCR unavailable: %s", exc)
    # heuristic always last (handles clean unicode math; low conf on scrambled)
    chain.append(HeuristicFormulaEngine())
    if len(chain) == 1:
        return chain[0]
    return ChainFormulaEngine(chain)
