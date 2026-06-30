"""Unit + end-to-end tests for the FormuDoc pipeline."""
import os
import zipfile

import pytest

from app.config import capabilities, get_settings
from app.models import ConvertMode, ConvertOptions
from app.services import pdf_analyzer, pipeline
from app.services.formula_engine import looks_like_formula, unicode_to_latex


# ----------------------------- unit tests ----------------------------- #
def test_capabilities_keys():
    caps = capabilities()
    for key in ("pymupdf", "pdfplumber", "python_docx", "pandoc", "tesseract"):
        assert key in caps


@pytest.mark.parametrize("text,expected", [
    ("∑ x_i = ∫ f(x) dx", True),
    ("E = mc^2", True),
    ("The quick brown fox jumps over the lazy dog.", False),
    ("Introduction to the topic", False),
])
def test_formula_detection(text, expected):
    assert looks_like_formula(text) is expected


def test_unicode_to_latex():
    out = unicode_to_latex("∑ᵢ θⱼ² − λ")
    assert "\\sum" in out and "\\theta" in out and "\\lambda" in out
    assert "−" not in out  # unicode minus normalised


def test_analyzer_born_digital(sample_pdf):
    analysis = pdf_analyzer.analyze(sample_pdf)
    assert analysis.page_count >= 1
    assert analysis.classification in ("born_digital", "mixed")


# --------------------------- end-to-end test --------------------------- #
def test_full_conversion_creates_docx(sample_pdf, tmp_path):
    settings = get_settings()
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    out = tmp_path / "out.docx"
    report = pipeline.run_pipeline(
        sample_pdf, ConvertOptions(mode=ConvertMode.scientific), str(out),
        settings, str(asset_dir), lambda p, s, m: None,
    )
    assert out.exists() and out.stat().st_size > 1000
    assert report.pages >= 1
    assert report.detected_text_blocks >= 1
    assert report.detected_tables >= 1

    # docx must be a valid zip with a document part
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "word/document.xml" in names
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
        assert "<w:tbl>" in xml  # the table survived as a real Word table
        if capabilities().get("pandoc") and report.editable_equations:
            assert "<m:oMath" in xml  # editable OMML equation present


def test_corrupt_pdf_does_not_crash(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 not a real pdf")
    with pytest.raises(Exception):
        pdf_analyzer.analyze(str(bad))
