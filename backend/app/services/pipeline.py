"""Orchestrates the 3-tier pipeline end to end.

Tier 1  pdf_analyzer      -> born-digital vs scanned
Tier 2  table_engine + layout_extractor (+ ocr_engine when scanned)
Tier 3  formula_engine    -> LaTeX (editable) or image fallback
Then    docx_builder      -> .docx + conversion report
"""
from __future__ import annotations

import logging
from typing import Callable

from ..config import Settings, capabilities
from ..models import BlockType, ConversionReport, ConvertOptions, DocumentModel
from . import docx_builder, pdf_analyzer, table_engine
from .formula_engine import get_formula_engine
from .layout_extractor import get_layout_engine
from .ocr_engine import get_ocr_engine

logger = logging.getLogger("formudoc.pipeline")

ProgressCb = Callable[[int, str, str], None]   # (percent, stage, message)


def run_pipeline(pdf_path: str, options: ConvertOptions, out_path: str,
                 settings: Settings, asset_dir: str,
                 progress: ProgressCb, api_keys=None) -> ConversionReport:
    caps = capabilities()

    # AI COUNCIL: if the user supplied API keys, several models cross-critique.
    if api_keys and options.mode.value == "scientific":
        from . import council_engine
        try:
            from ..config import gemini_passes
            return council_engine.run(pdf_path, options, out_path, settings,
                                      asset_dir, progress, api_keys,
                                      rounds=gemini_passes() if gemini_passes() > 1 else 6)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI council failed (%s); trying next engine", exc)

    # Best quality when a Gemini API key is configured: Gemini reads each page
    # (Vietnamese text + LaTeX) with a verify-and-fix loop.
    if options.mode.value == "scientific" and caps.get("gemini"):
        from . import gemini_engine
        try:
            progress(2, "analyze", "Using Gemini page recognizer (API)")
            return gemini_engine.run(pdf_path, options, out_path, settings,
                                     asset_dir, progress)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini path failed (%s); trying next engine", exc)

    # Highest-quality offline route for mixed text+math: Pix2Text full-page.
    import os as _os
    _fullpage = _os.getenv("FORMUDOC_FULLPAGE") == "1"
    if _fullpage and options.mode.value == "scientific" and caps.get("pix2text"):
        from . import fullpage_engine
        try:
            progress(3, "analyze", "Using Pix2Text full-page recognizer (offline)")
            return fullpage_engine.run(pdf_path, options, out_path, settings,
                                       asset_dir, progress)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pix2Text full-page failed (%s); using standard pipeline", exc)

    report = ConversionReport()
    warnings: list[str] = []

    # --- Tier 1: classification -------------------------------------- #
    progress(5, "analyze", "Tier 1 · classifying PDF (born-digital vs scanned)")
    analysis = pdf_analyzer.analyze(pdf_path)
    report.pages = analysis.page_count
    report.classification = analysis.classification
    progress(15, "analyze",
             f"Classified as {analysis.classification} "
             f"({analysis.scanned_pages}/{analysis.page_count} scanned pages)")

    # --- Tier 2a: tables --------------------------------------------- #
    tables = {}
    if options.detect_tables and analysis.classification != "scanned":
        progress(28, "tables", "Tier 2 · detecting tables (PubTables-style)")
        tables = table_engine.detect_tables(pdf_path)
        n_tables = sum(len(v) for v in tables.values())
        progress(35, "tables", f"Found {n_tables} candidate table(s)")
    elif options.detect_tables:
        warnings.append("Scanned document: table grids approximated from OCR text.")

    # --- Tier 2b: layout extraction ---------------------------------- #
    ocr_engine = get_ocr_engine()
    if analysis.classification != "born_digital" or options.mode.value == "ocr_heavy":
        if ocr_engine.name == "none":
            warnings.append("OCR needed but no OCR engine installed "
                            "(install pytesseract + tesseract binary).")
    layout_engine = get_layout_engine(prefer_advanced=(options.mode.value == "scientific"))
    progress(45, "layout",
             f"Tier 2 · extracting layout with '{layout_engine.name}' engine")
    document: DocumentModel = layout_engine.extract(
        pdf_path, options, analysis, tables, ocr_engine, asset_dir, settings.render_dpi
    )
    progress(60, "layout", f"Extracted {len(document.blocks)} ordered blocks")

    # --- Tier 3: formulas -------------------------------------------- #
    formula_blocks = [b for b in document.blocks if b.type == BlockType.formula]
    _ocr_mode = _os.getenv("FORMUDOC_FORMULA_OCR", "auto").strip().lower()
    if options.detect_formulas and formula_blocks and _ocr_mode in ("off", "0", "false", "no"):
        # FAST PATH: skip the (slow) per-formula LaTeX recogniser entirely and
        # embed each formula as a cropped image. Near-instant; not editable.
        n_f = len(formula_blocks)
        progress(70, "formula",
                 f"Tier 3 · keeping {n_f} formula(s) as images "
                 "(FORMUDOC_FORMULA_OCR=off, fast)")
        report.engines_used["formula"] = "image-only"
        warnings.append("Formula OCR disabled (FORMUDOC_FORMULA_OCR=off): "
                        "equations embedded as images, not editable.")
    elif options.detect_formulas and formula_blocks:
        engine = get_formula_engine(prefer_ai=(options.mode.value != "fast"))
        n_f = len(formula_blocks)
        progress(70, "formula",
                 f"Tier 3 · recognising {n_f} formula(s) via '{engine.name}'")
        is_markdown = engine.name == "mathpix"
        try:
            _workers = max(1, int(_os.getenv("FORMUDOC_FORMULA_WORKERS", "2")))
        except ValueError:
            _workers = 2

        def _reco(_b):
            try:
                return _b, engine.to_latex(_b.image_path or "", text_hint=_b.text)
            except Exception as exc:  # degrade to image; never crash the job
                logger.warning("formula OCR failed (%s); keeping as image", exc)
                from .formula_engine import FormulaResult
                return _b, FormulaResult(latex=None, confidence=0.0,
                                         image_path=_b.image_path or "")

        results = []
        if _workers > 1 and n_f > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            done = 0
            with ThreadPoolExecutor(max_workers=_workers) as _ex:
                _futs = [_ex.submit(_reco, b) for b in formula_blocks]
                for _fut in as_completed(_futs):
                    results.append(_fut.result())
                    done += 1
                    if done % 5 == 0 or done == n_f:
                        progress(70 + int(20 * done / n_f), "formula",
                                 f"Tier 3 · formula {done}/{n_f} done "
                                 f"({_workers} parallel)")
        else:
            for _i, b in enumerate(formula_blocks, 1):
                results.append(_reco(b))
                if _i % 5 == 0 or _i == n_f:
                    progress(70 + int(20 * _i / n_f), "formula",
                             f"Tier 3 · formula {_i}/{n_f} done")

        for b, res in results:
            b.latex = res.latex
            b.confidence = res.confidence
            if is_markdown and res.latex is not None and "$" not in res.latex:
                # Mathpix found only text (no math) -> keep it as a normal
                # paragraph instead of a (broken) equation.
                b.type = BlockType.paragraph
                b.text = res.latex
                b.latex = None
                b.editable_equation = False
                continue
            b.editable_equation = bool(
                options.convert_formulas_editable and res.latex
                and res.confidence >= 0.45 and caps.get("pandoc")
            )
        report.engines_used["formula"] = engine.name
        if not caps.get("pandoc"):
            warnings.append("pandoc not found: equations rendered as images "
                            "(install pandoc for editable Word equations).")
    elif formula_blocks:
        for b in formula_blocks:          # keep them as plain math text
            b.type = BlockType.paragraph

    # --- Report counts (pre-build) ----------------------------------- #
    text_types = {BlockType.paragraph, BlockType.heading, BlockType.title,
                  BlockType.caption, BlockType.footnote, BlockType.list_item}
    report.detected_text_blocks = sum(1 for b in document.blocks if b.type in text_types)
    report.detected_tables = sum(1 for b in document.blocks if b.type == BlockType.table)
    report.detected_formulas = len(formula_blocks)
    report.detected_figures = sum(1 for b in document.blocks if b.type == BlockType.figure)
    report.engines_used.update({
        "layout": layout_engine.name,
        "ocr": ocr_engine.name,
        "docx": "pandoc" if caps.get("pandoc") else "python-docx",
    })

    # --- Build DOCX --------------------------------------------------- #
    progress(85, "build", "Building Word document")
    stats = docx_builder.build_docx(document, options, out_path, settings)
    report.editable_equations = stats.get("editable_equations", 0)
    report.image_fallback_equations = stats.get("image_fallback_equations", 0)
    report.removed_headers_footers = stats.get("removed_headers_footers", 0)
    report.engines_used["docx"] = stats.get("backend", report.engines_used.get("docx"))

    if report.detected_formulas and report.editable_equations == 0 and \
            report.image_fallback_equations > 0:
        warnings.append("Equations kept as images (no editable OMML produced).")
    report.warnings = warnings
    progress(98, "build", "Word document assembled")
    return report


def build_preview(document_blocks_text: str) -> str:
    return document_blocks_text[:1800]
