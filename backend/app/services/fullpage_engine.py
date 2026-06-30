"""Optional FULL-PAGE recognizer using Pix2Text (offline, free, no token).

Pix2Text reads a whole page image and returns Markdown with text, tables and
LaTeX math (`$...$` / `$$...$$`) already in the right places. pandoc then turns
that into an editable Word document. This is the highest-quality offline route
for documents that mix text and mathematics (the per-block crop approach can't
match it). Heavy (pulls PyTorch) but fully local and private.

Ideas align with Pix2Text / Nougat / Marker: layout-aware page -> markup.
"""
from __future__ import annotations

import logging

import fitz

from ..config import capabilities
from ..models import ConversionReport
from . import docx_builder, pdf_analyzer
from .docx_builder import _pagebreak

logger = logging.getLogger("formudoc.fullpage")


def is_available() -> bool:
    return capabilities().get("pix2text", False)


class Pix2TextFullPage:
    name = "pix2text"

    def __init__(self) -> None:
        import os
        from pix2text import Pix2Text
        # Default text OCR is Chinese (cnocr). Switch to Vietnamese via EasyOCR by
        # passing languages that are not a subset of {en, ch_sim}. Needs easyocr
        # (pip install easyocr); if missing, from_config raises and the pipeline
        # falls back to the standard (text-layer + Tesseract-vie) pipeline.
        langs = tuple(l.strip() for l in
                      os.getenv("FORMUDOC_OCR_LANGS", "vi,en").split(",") if l.strip())
        self._p2t = Pix2Text.from_config(
            total_configs={"text_formula": {"languages": langs}},
            enable_formula=True, enable_table=True, device="cpu")
        logger.info("Pix2Text full-page text OCR languages: %s", langs)

    def page_markdown(self, image_path: str) -> str:
        md = self._p2t.recognize_text_formula(image_path, return_text=True)
        if isinstance(md, (list, tuple)):
            md = "\n\n".join(str(x) for x in md)
        return md or ""


def run(pdf_path, options, out_path, settings, asset_dir, progress) -> ConversionReport:
    """Render each page -> Pix2Text markdown -> pandoc -> .docx."""
    analysis = pdf_analyzer.analyze(pdf_path)
    progress(8, "fullpage", "Loading Pix2Text models (first run downloads them)")
    engine = Pix2TextFullPage()

    parts: list[str] = []
    n_formula = 0
    with fitz.open(pdf_path) as doc:
        n = doc.page_count
        for i, page in enumerate(doc):
            progress(int(10 + 80 * i / max(n, 1)), "fullpage",
                     f"Pix2Text reading page {i + 1}/{n}")
            img = f"{asset_dir}/page_{i}.png"
            page.get_pixmap(dpi=settings.render_dpi).save(img)
            md = engine.page_markdown(img)
            n_formula += md.count("$$") // 2
            parts.append(md)

    markdown = ("\n\n" + _pagebreak() + "\n\n").join(p for p in parts if p.strip())
    progress(90, "build", "Building Word from Pix2Text markdown")
    docx_builder.markdown_to_docx(markdown, out_path, settings)

    report = ConversionReport(pages=analysis.page_count,
                              classification=analysis.classification)
    report.detected_formulas = n_formula
    report.editable_equations = n_formula
    report.detected_text_blocks = sum(len([x for x in p.split("\n") if x.strip()])
                                      for p in parts)
    report.engines_used = {"recognizer": "pix2text(full-page)", "docx": "pandoc"}
    report.warnings = ["Full-page Pix2Text mode: figures may be omitted; "
                       "math is recognised to editable equations."]
    progress(98, "build", "Word document assembled (Pix2Text)")
    return report
