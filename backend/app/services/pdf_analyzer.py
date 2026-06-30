"""Tier 1 — PDF classification.

Decide, per page and for the whole document, whether content is *born-digital*
(has a usable text layer) or *scanned* (image only / broken text layer). This
drives whether downstream extraction uses the text layer or falls back to OCR.
Idea borrowed from Marker / Docling pre-processing stages.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import fitz  # PyMuPDF

logger = logging.getLogger("formudoc.analyzer")


@dataclass
class PageClassification:
    number: int
    width: float
    height: float
    char_count: int
    image_area_ratio: float
    text_coverage: float
    is_scanned: bool


@dataclass
class PdfAnalysis:
    page_count: int
    classification: str           # born_digital | scanned | mixed
    scanned_pages: int
    pages: list[PageClassification]


# A page is treated as scanned if it has almost no extractable text but is
# largely covered by raster image(s).
_MIN_CHARS_PER_PAGE = 25
_HIGH_IMAGE_RATIO = 0.55


def analyze(pdf_path: str) -> PdfAnalysis:
    pages: list[PageClassification] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            rect = page.rect
            page_area = max(rect.width * rect.height, 1.0)
            text = page.get_text("text") or ""
            char_count = len(text.strip())

            image_area = 0.0
            try:
                for info in page.get_image_info():
                    bb = info.get("bbox")
                    if bb:
                        image_area += abs((bb[2] - bb[0]) * (bb[3] - bb[1]))
            except Exception:  # pragma: no cover
                pass
            image_ratio = min(image_area / page_area, 1.0)

            # crude text coverage: area of text blocks / page area
            text_area = 0.0
            for b in page.get_text("blocks"):
                x0, y0, x1, y1 = b[:4]
                text_area += abs((x1 - x0) * (y1 - y0))
            text_coverage = min(text_area / page_area, 1.0)

            is_scanned = (
                char_count < _MIN_CHARS_PER_PAGE and image_ratio >= _HIGH_IMAGE_RATIO
            ) or char_count == 0

            pages.append(
                PageClassification(
                    number=i,
                    width=rect.width,
                    height=rect.height,
                    char_count=char_count,
                    image_area_ratio=round(image_ratio, 3),
                    text_coverage=round(text_coverage, 3),
                    is_scanned=is_scanned,
                )
            )

    scanned = sum(1 for p in pages if p.is_scanned)
    if scanned == 0:
        classification = "born_digital"
    elif scanned == len(pages):
        classification = "scanned"
    else:
        classification = "mixed"

    logger.info(
        "Analyzed %d pages -> %s (%d scanned)", len(pages), classification, scanned
    )
    return PdfAnalysis(
        page_count=len(pages),
        classification=classification,
        scanned_pages=scanned,
        pages=pages,
    )
