"""Tier 2 — Table reconstruction.

Inspired by PubTables-1M / Table Transformer: try to rebuild a *real* table
(grid of cell strings) so it can be emitted as an editable Word table. When the
structure confidence is too low we fall back to a cropped image of the table so
nothing is lost. We use pdfplumber's ruling/word clustering as the detector,
which works well on born-digital PDFs without any GPU model.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pdfplumber

logger = logging.getLogger("formudoc.table")


@dataclass
class DetectedTable:
    page: int
    bbox: tuple[float, float, float, float]
    cells: list[list[str]] = field(default_factory=list)
    confidence: float = 0.0
    n_rows: int = 0
    n_cols: int = 0


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def _score(grid: list[list[str]]) -> float:
    """Confidence = regularity * fill ratio."""
    if not grid:
        return 0.0
    n_rows = len(grid)
    col_counts = [len(r) for r in grid]
    n_cols = max(col_counts)
    if n_rows < 2 or n_cols < 2:
        return 0.0
    regularity = sum(1 for c in col_counts if c == n_cols) / n_rows
    filled = sum(1 for r in grid for c in r if c.strip())
    fill_ratio = filled / (n_rows * n_cols)
    return round(0.5 * regularity + 0.5 * fill_ratio, 3)


def detect_tables(pdf_path: str, page_numbers: list[int] | None = None
                  ) -> dict[int, list[DetectedTable]]:
    """Return {page_index: [DetectedTable, ...]} for born-digital pages."""
    results: dict[int, list[DetectedTable]] = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for idx, page in enumerate(pdf.pages):
                if page_numbers is not None and idx not in page_numbers:
                    continue
                try:
                    found = page.find_tables()
                except Exception as exc:  # pragma: no cover
                    logger.debug("find_tables failed on page %d: %s", idx, exc)
                    continue
                page_tables: list[DetectedTable] = []
                for t in found:
                    try:
                        raw = t.extract() or []
                    except Exception:
                        raw = []
                    grid = [[_clean(c) for c in row] for row in raw if row]
                    if not grid:
                        continue
                    conf = _score(grid)
                    x0, y0, x1, y1 = t.bbox
                    page_tables.append(
                        DetectedTable(
                            page=idx,
                            bbox=(x0, y0, x1, y1),
                            cells=grid,
                            confidence=conf,
                            n_rows=len(grid),
                            n_cols=max(len(r) for r in grid),
                        )
                    )
                if page_tables:
                    results[idx] = page_tables
                    logger.info("Page %d: %d table(s) detected", idx, len(page_tables))
    except Exception as exc:  # pragma: no cover
        logger.warning("Table detection error: %s", exc)
    return results
