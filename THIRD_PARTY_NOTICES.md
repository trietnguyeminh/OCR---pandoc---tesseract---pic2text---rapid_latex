# Third-party notices

FormuDoc's own source code is licensed **MIT** (see LICENSE). It relies on
third-party components that keep their own licenses. This file documents them.

> Not legal advice — verify before commercial distribution.

## ⚠️ Important: PyMuPDF is AGPL-3.0
`PyMuPDF` (`fitz`) is a **core dependency** and is licensed **AGPL-3.0** (or
commercial). It is NOT included in this repository — it is installed by the
user via `pip`. Consequences:

- **The source repo (MIT) is fine** — it does not redistribute PyMuPDF.
- **A bundled binary that includes PyMuPDF (e.g. the PyInstaller `.exe`) is a
  combined work and is effectively AGPL-3.0.** Do not relabel that binary as
  MIT. Either (a) don't distribute the `.exe`, (b) distribute it under AGPL-3.0
  and offer the corresponding source, or (c) rebuild after replacing PyMuPDF
  with a permissive renderer (e.g. `pypdfium2`, Apache/BSD).
- **Running it as a network service** triggers AGPL §13 (offer source of the
  combined work).

## Dependency licenses
| Component | License | How it's used |
|---|---|---|
| PyMuPDF (fitz) | **AGPL-3.0** | PDF render + text/spans (see caveat above) |
| pandoc | GPL-2.0+ | external program, called via subprocess (not bundled) |
| Tesseract OCR | Apache-2.0 | external program (OCR) |
| pdfplumber | MIT | table/text extraction |
| python-docx | MIT | DOCX writing |
| pix2text (optional) | MIT | offline layout+formula |
| rapid_latex_ocr (vendored) | Apache-2.0 | formula→LaTeX — see backend/app/vendor/rapid_latex_ocr/LICENSE |
| Pillow | HPND (MIT-like) | image handling |
| numpy | BSD-3-Clause | arrays |
| FastAPI / Starlette / uvicorn | MIT/BSD | web server |
| pydantic | MIT | models |
| React / Vite / Tailwind | MIT | frontend |

Model weights (LaTeX-OCR, downloaded at runtime) derive from
**LaTeX-OCR** by Lukas Blecher (MIT); they are not bundled in this repo.
