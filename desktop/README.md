# FormuDoc — Desktop app

Turn FormuDoc into a **single, double-clickable application** that opens in its
own window (no terminal, no browser tab).

## Build the .exe (Windows, one time)

Prerequisites: **Python 3.10+** and **Node.js**.

```bat
cd desktop
build_exe.bat
```

Result: **`desktop\dist\FormuDoc.exe`** — double-click to run. You can copy that
single file anywhere, or pin it to the taskbar / Start menu.

> For **editable Word equations** install [pandoc](https://pandoc.org/installing.html);
> for **OCR** of scanned PDFs install
> [tesseract](https://github.com/UB-Mannheim/tesseract/wiki). Without them the
> app still works (equations become images, scans stay images).

## Run without building (dev)

```bat
cd desktop
run_from_source.bat
```
or manually:
```bash
pip install -r backend/requirements.txt pywebview
cd frontend && npm install && npm run build && cd ..
python desktop/launcher.py
```

## How it works

`app.py` starts the FastAPI server (which serves both the API and the built
React UI on one port) in a background thread, then opens a native window
(pywebview) pointed at it. The user's files are written under
`~/FormuDoc/data`.

## Troubleshooting

**`pip` tries to "build wheel from source" / numpy meson / GCC error.**
Your Python is newer than some packages' prebuilt wheels (common on Python
3.13/3.14). Two fixes, either works:

1. The scripts already pass `--prefer-binary` and auto-pick `py -3.12` if you
   have it. **Install Python 3.12** from <https://www.python.org/downloads/> and
   re-run `build_exe.bat` — it will use 3.12 automatically.
2. Or install deps manually with prebuilt wheels:
   ```bat
   py -3.12 -m pip install --prefer-binary -r ..\backend\requirements.txt pywebview pyinstaller
   ```

**`npm` not recognized** → install Node.js from <https://nodejs.org> (LTS).

**Equations show as images, not editable** → install
[pandoc](https://pandoc.org/installing.html) and rebuild.
