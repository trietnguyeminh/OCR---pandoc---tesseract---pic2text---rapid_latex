"""Central configuration + optional-dependency detection.

The whole point of this module is that FormuDoc must run on a *bare* install
(only the libraries in the non-commented part of requirements.txt). Every heavy
model is optional and probed at runtime via :func:`capabilities`.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
DATA_DIR = Path(os.getenv("FORMUDOC_DATA", BASE_DIR / "data"))


class Settings(BaseSettings):
    app_name: str = "FormuDoc Converter"
    version: str = "1.0.0"

    # storage
    upload_dir: Path = DATA_DIR / "uploads"
    output_dir: Path = DATA_DIR / "outputs"
    job_dir: Path = DATA_DIR / "jobs"
    asset_dir: Path = DATA_DIR / "assets"      # extracted images, crops

    # runtime
    max_upload_mb: int = 100
    render_dpi: int = 200                       # page rasterisation DPI
    max_workers: int = 2
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(env_prefix="FORMUDOC_", extra="ignore")

    def ensure_dirs(self) -> None:
        for d in (self.upload_dir, self.output_dir, self.job_dir, self.asset_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


@lru_cache
def capabilities() -> dict[str, bool]:
    """Probe which optional engines are available on this machine."""
    return {
        # layout
        "pymupdf": _has_module("fitz"),
        "pdfplumber": _has_module("pdfplumber"),
        "docling": _has_module("docling"),
        # ocr
        "tesseract": find_tesseract() is not None and _has_module("pytesseract"),
        "paddleocr": _has_module("paddleocr"),
        # formulas
        "pix2tex": _has_module("pix2tex"),
        "rapid_latex": (_has_module("rapid_latex_ocr")
                        or (Path(__file__).resolve().parent / "vendor"
                            / "rapid_latex_ocr" / "main.py").exists()),
        "pix2text": _has_module("pix2text"),
        "gemini": gemini_auth() is not None,
        "matplotlib": _has_module("matplotlib"),
        "latex2mathml": _has_module("latex2mathml"),
        # docx / equations
        "python_docx": _has_module("docx"),
        "mathpix": bool(mathpix_credentials()[0] and mathpix_credentials()[1]),
        "pandoc": shutil.which("pandoc") is not None or _pypandoc_pandoc(),
    }


def _pypandoc_pandoc() -> bool:
    try:
        import pypandoc

        pypandoc.get_pandoc_path()
        return True
    except Exception:
        return False


def frontend_dist():
    """Locate the built React UI so FastAPI can serve it as a single app.

    Resolution order: $FORMUDOC_DIST -> PyInstaller bundle (web/) ->
    repo layout frontend/dist -> backend/app/static.
    """
    import sys
    from pathlib import Path as _P
    cands = []
    env = os.getenv("FORMUDOC_DIST")
    if env:
        cands.append(_P(env))
    if hasattr(sys, "_MEIPASS"):
        cands.append(_P(sys._MEIPASS) / "web")
    cands.append(BASE_DIR.parent / "frontend" / "dist")
    cands.append(BASE_DIR / "app" / "static")
    for c in cands:
        try:
            if c and (c / "index.html").exists():
                return c
        except Exception:
            pass
    return None


@lru_cache
def find_tesseract():
    """Locate the tesseract executable (PATH or common Windows/mac/Linux paths)."""
    import os
    p = shutil.which("tesseract")
    if p:
        return p
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe"),
        "/usr/bin/tesseract", "/usr/local/bin/tesseract", "/opt/homebrew/bin/tesseract",
    ]
    for c in candidates:
        try:
            if c and Path(c).exists():
                return c
        except Exception:
            pass
    return None


@lru_cache
def mathpix_credentials():
    """Return (app_id, app_key) for Mathpix from env vars or a JSON config file.

    Looked up in order:
      1. env MATHPIX_APP_ID / MATHPIX_APP_KEY
      2. ~/FormuDoc/mathpix.json  (or <FORMUDOC_DATA>/../mathpix.json)
         -> {"app_id": "...", "app_key": "..."}
    """
    import json
    aid = os.getenv("MATHPIX_APP_ID")
    akey = os.getenv("MATHPIX_APP_KEY")
    if aid and akey:
        return aid, akey
    candidates = [
        Path(os.getenv("FORMUDOC_DATA", Path.home() / "FormuDoc" / "data")).parent / "mathpix.json",
        Path.home() / "FormuDoc" / "mathpix.json",
    ]
    for c in candidates:
        try:
            if c.exists():
                d = json.loads(c.read_text(encoding="utf-8"))
                if d.get("app_id") and d.get("app_key"):
                    return d["app_id"], d["app_key"]
        except Exception:
            pass
    return None, None


def gemini_auth():
    """Gemini API key (env FORMUDOC_GEMINI_KEY or ~/FormuDoc/gemini.txt).
    Get a free key at https://aistudio.google.com/apikey ."""
    import os
    key = os.getenv("FORMUDOC_GEMINI_KEY")
    if not key:
        try:
            f = Path.home() / "FormuDoc" / "gemini.txt"
            if f.exists():
                key = f.read_text(encoding="utf-8").strip()
        except Exception:
            key = None
    return key or None


def gemini_model():
    import os
    return os.getenv("FORMUDOC_GEMINI_MODEL", "gemini-2.5-flash")


def gemini_passes():
    import os
    try:
        return max(1, min(8, int(os.getenv("FORMUDOC_GEMINI_PASSES", "3"))))
    except Exception:
        return 3
