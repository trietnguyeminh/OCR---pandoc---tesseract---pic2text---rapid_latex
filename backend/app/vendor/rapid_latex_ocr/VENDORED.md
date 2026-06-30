# Vendored: rapid_latex_ocr

This directory is a verbatim copy of **rapid_latex_ocr** (v0.0.9) by RapidAI,
bundled into this project because the upstream package caps Python at <3.13 and
this app runs on newer Python. Only `utils.py` was patched to make the `chardet`
import optional (config.yaml is ASCII).

- Upstream: https://github.com/RapidAI/RapidLaTeXOCR
- License: Apache-2.0 (see LICENSE in this folder)
- Model weights are NOT bundled; they download on first use (or place them in
  ~/FormuDoc/rapid_latex_models/). Weights derive from LaTeX-OCR (Lukas Blecher, MIT).
