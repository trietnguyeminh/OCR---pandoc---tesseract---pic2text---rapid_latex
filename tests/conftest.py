"""Pytest config: make `backend` importable and provide a sample PDF."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# isolate all FormuDoc data under a temp dir for the whole test session
os.environ.setdefault("FORMUDOC_DATA", str(ROOT / "backend" / "data" / "_pytest"))


def _make_pdf(path: Path) -> None:
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 90), "Test Title", fontsize=22)
    page.insert_text((72, 130), "1. Section", fontsize=15)
    page.insert_textbox(fitz.Rect(72, 150, 520, 200),
                        "A short paragraph of body text for the analyzer.",
                        fontsize=11)
    page.insert_text((120, 240), "E = m c^2  and  ∑ x_i = ∫ f(x) dx", fontsize=14)
    # a ruled table
    rows = [["A", "B"], ["1", "2"], ["3", "4"]]
    x0, y0, cw, rh = 72, 300, 120, 24
    for r in range(len(rows) + 1):
        page.draw_line(fitz.Point(x0, y0 + r * rh), fitz.Point(x0 + 2 * cw, y0 + r * rh))
    for c in range(3):
        page.draw_line(fitz.Point(x0 + c * cw, y0), fitz.Point(x0 + c * cw, y0 + 3 * rh))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            page.insert_text((x0 + c * cw + 6, y0 + r * rh + 16), v, fontsize=10)
    doc.save(str(path))
    doc.close()


@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory) -> str:
    repo_sample = ROOT / "sample_data" / "sample.pdf"
    if repo_sample.exists():
        return str(repo_sample)
    out = tmp_path_factory.mktemp("pdf") / "sample.pdf"
    _make_pdf(out)
    return str(out)
