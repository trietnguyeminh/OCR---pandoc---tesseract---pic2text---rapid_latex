# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for FormuDoc Converter (single-file desktop app).
# Build on Windows:  pyinstaller --noconfirm FormuDoc.spec
import os
from PyInstaller.utils.hooks import collect_all

spec_dir = os.path.dirname(os.path.abspath(SPECPATH))
backend = os.path.join(spec_dir, "backend")
dist_ui = os.path.join(spec_dir, "frontend", "dist")

# bundle the built UI under "web/" (config.frontend_dist() looks in _MEIPASS/web)
datas = [(dist_ui, "web")]
binaries = []
hiddenimports = [
    "app.main", "app.config", "app.models",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.loops.asyncio",
    "pytesseract",
    "requests",
]

# pull data files / submodules of the heavy libs so the exe is self-contained
for pkg in [
    "webview", "fitz", "pymupdf", "pdfplumber", "pdfminer", "docx",
    "latex2mathml", "matplotlib", "PIL", "fastapi", "starlette", "uvicorn", "pytesseract",
    "anyio", "h11", "pydantic", "pydantic_settings", "pypandoc", "lxml",
    "numpy",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # pragma: no cover
        print("collect_all skipped", pkg, exc)

a = Analysis(
    [os.path.join(spec_dir, "run_formudoc.py")],
    pathex=[backend],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = os.path.join(spec_dir, "desktop", "icon.ico")
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="FormuDoc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                # no console window -> looks like a real app
    icon=icon if os.path.exists(icon) else None,
)
