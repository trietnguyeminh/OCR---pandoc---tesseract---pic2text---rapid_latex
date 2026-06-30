<p align="center">
  <img src="frontend/public/logo.svg" width="72" alt="FormuDoc logo"/>
</p>

<h1 align="center">FormuDoc Converter</h1>

<p align="center">
  <b>PDF → Word (.docx)</b> that preserves text, layout, tables, images and
  <b>math</b> — including <b>editable</b> Word equations (OMML).
</p>

---

FormuDoc is a research-grade PDF→DOCX converter built around a **3-tier
pipeline**. It runs out of the box on a plain install (no GPU, no heavy model)
and *gracefully upgrades* when optional AI engines are present.

The design borrows ideas from:

| Paper / project | What we use it for |
|---|---|
| **Nougat** | Treating a formula region as an image→markup problem; never drop a formula |
| **DocLayNet** | Block taxonomy: title / heading / paragraph / table / figure / caption / formula / header / footer |
| **PubLayNet** | Layout-region thinking for reading order & figure/caption pairing |
| **Image-to-Markup (im2markup)** | Crop → LaTeX markup for image formulas |
| **TrOCR** | Transformer-OCR mindset for the OCR fallback stage |
| **PubTables-1M / Table Transformer** | Reconstruct *real* table grids, fall back to image on low confidence |
| **Docling** | Optional advanced layout engine (adapter) + pre-processing classification |
| **Marker** | Born-digital vs scanned classification, pandoc-style markdown bridge to DOCX |

## Architecture

```
                         ┌─────────────────────────────────────────────┐
  PDF  ──►  FastAPI  ──► │                 PIPELINE                     │ ──► .docx
                         │                                             │      +report.json
  Tier 1  pdf_analyzer   │  born-digital? scanned?  (text coverage)    │
  Tier 2  table_engine   │  tables (PubTables)                         │
          layout_extractor│ blocks + reading order + 2-col + HF removal│
          ocr_engine     │  Tesseract/Paddle fallback for scans        │
  Tier 3  formula_engine │  crop → LaTeX (pix2tex / heuristic)         │
          docx_builder   │  pandoc → editable OMML  (or python-docx)   │
                         └─────────────────────────────────────────────┘
```

Everything is built behind **adapter interfaces** so heavy models are optional:

```
BaseLayoutEngine   → PyMuPDFLayoutEngine   (default) | DoclingLayoutEngine (optional)
BaseOCREngine      → TesseractOCREngine | PaddleOCREngine | NullOCREngine
BaseFormulaEngine  → Pix2TexFormulaEngine | HeuristicFormulaEngine | FallbackImageFormulaEngine
docx_builder       → pandoc backend (editable equations) | python-docx backend (image fallback)
```

If pandoc is installed, equations become **real, editable Word equations**. If
not, they are rendered to images so they are *never lost* (and the report says
so).

## Project layout

```
formudoc-converter/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI + routes
│   │   ├── config.py          # settings + optional-dependency probing
│   │   ├── models.py          # Pydantic schemas + internal document model
│   │   ├── services/
│   │   │   ├── pdf_analyzer.py     # Tier 1
│   │   │   ├── table_engine.py     # Tier 2 (tables)
│   │   │   ├── layout_extractor.py # Tier 2 (layout, reading order, figures)
│   │   │   ├── ocr_engine.py       # Tier 2 (OCR fallback)
│   │   │   ├── formula_engine.py   # Tier 3 (formulas)
│   │   │   ├── docx_builder.py     # DOCX assembly (pandoc / python-docx)
│   │   │   ├── pipeline.py         # orchestrator
│   │   │   └── job_manager.py      # background jobs
│   │   └── utils/logging_config.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                  # React + Vite + TailwindCSS + TypeScript
│   └── src/{App.tsx, api.ts, components/*}
├── tests/                     # pytest (unit + end-to-end)
├── sample_data/make_sample.py # generates a test PDF
├── docker-compose.yml
└── README.md
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status + detected engine capabilities |
| POST | `/api/analyze-pdf` | upload PDF → file_id, pages, classification |
| POST | `/api/convert` | `{file_id, options}` → `{job_id}` |
| GET | `/api/jobs/{job_id}` | status, progress, log, report, download URL |
| GET | `/api/download/{job_id}` | the generated `.docx` |
| GET | `/api/report/{job_id}` | conversion report JSON |

## Run it

### Option 0 — Desktop app (recommended, one click) 🖥️

Package everything into **one `FormuDoc.exe`** that opens in its own window
(like a normal app — no terminal, no browser tab). On Windows, with Python 3.10+
and Node.js installed:

```bat
cd desktop
build_exe.bat
```
This builds the UI, then produces **`desktop\\dist\\FormuDoc.exe`** — double-click
to launch. Copy that file anywhere or pin it to the taskbar. See
[`desktop/README.md`](desktop/README.md). To just try it without packaging:
`cd desktop && run_from_source.bat`.


### Option A — local (two terminals)

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # optional
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173  (proxies /api to :8000)
```

Open http://localhost:5173, drop a PDF, pick a mode, click **Convert**.

> **Editable equations & OCR** need two CLI tools. Without them the app still
> works (equations become images, scans stay images):
> - **pandoc** → editable Word equations: `apt install pandoc` / `brew install pandoc`
> - **tesseract** → OCR fallback: `apt install tesseract-ocr` / `brew install tesseract`

### Option B — Docker (one command)

```bash
docker compose up --build
```
- Frontend → http://localhost:5173
- Backend  → http://localhost:8000
The backend image already includes **pandoc** and **tesseract**.

### Tests
```bash
pip install pytest
pytest -q
```

### Generate a sample PDF
```bash
python sample_data/make_sample.py     # writes sample_data/sample.pdf
```

## Conversion modes & options

- **Fast Convert** — text layer only, quickest.
- **Scientific Accurate** *(default)* — full layout + tables + formulas.
- **OCR Heavy** — force OCR on every page (for scans / broken text layers).

Toggles: *Preserve layout*, *Detect formulas*, *Convert formulas to editable
Word equations*, *Detect tables*, *Remove repeated headers/footers*.

## Conversion report

Every job emits a JSON report, e.g.:

```json
{
  "pages": 2,
  "detected_text_blocks": 9,
  "detected_tables": 1,
  "detected_formulas": 2,
  "editable_equations": 2,
  "image_fallback_equations": 0,
  "detected_figures": 1,
  "removed_headers_footers": 4,
  "classification": "born_digital",
  "engines_used": {"layout": "pymupdf", "ocr": "tesseract",
                   "formula": "heuristic", "docx": "pandoc"},
  "warnings": []
}
```

## Enabling the heavy AI engines (optional)

Uncomment the relevant lines in `backend/requirements.txt`:

- `pix2tex` → image-formula → LaTeX (LaTeX-OCR). Auto-detected by `formula_engine`.
- `docling` → DocLayNet-grade layout. Auto-detected by `layout_extractor`.
- `paddleocr` → alternative OCR. Auto-detected by `ocr_engine`.

No code changes needed — the adapters pick them up at runtime via
`config.capabilities()`.

## Notes & limitations

- Inline math inside born-digital paragraphs is preserved as Unicode text;
  *display* formulas are turned into editable equations (or images).
- Table reconstruction targets ruled/born-digital tables; low-confidence tables
  fall back to a cropped image (flagged in the report).
- The app never crashes on a malformed PDF — it returns a 422 / job error
  instead.

---

## License

This project's source code is licensed under the **MIT License** (see `LICENSE`).

It depends on third-party components under their own licenses — see
`THIRD_PARTY_NOTICES.md`. **Note:** `PyMuPDF` is AGPL-3.0; the MIT terms cover
*this* source only. A binary that bundles PyMuPDF (the PyInstaller `.exe`) is a
combined work and is effectively **AGPL-3.0** — don't redistribute that `.exe`
as MIT. The bundled `rapid_latex_ocr` (Apache-2.0) is in
`backend/app/vendor/rapid_latex_ocr/` with its original LICENSE.
