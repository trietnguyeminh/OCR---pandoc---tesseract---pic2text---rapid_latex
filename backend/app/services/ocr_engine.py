"""OCR fallback engines (TrOCR-style task, classic engines as the workhorse).

We expose a small adapter interface so heavy engines can be swapped in:
    BaseOCREngine
      |- TesseractOCREngine   (pytesseract, needs `tesseract` binary)
      |- PaddleOCREngine      (paddleocr, optional)
      |- NullOCREngine        (always available, returns nothing + warning)

`get_ocr_engine()` picks the best available one.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..config import capabilities

logger = logging.getLogger("formudoc.ocr")

import re as _re

def _ocr_line_is_noise(text: str) -> bool:
    """Conservative: only drop obvious dotted/underscored form-field lines.
    (Letter-ratio filters would wrongly delete answer lines like
    'A. (2;-2;0). B. (-2;2;0).' so we avoid them.)"""
    t = (text or "").strip()
    if len(t) < 6:
        return False
    if _re.search(r"[._]{6,}", t):     # "......" or "______" form fields
        return True
    if t.count("\u2026") >= 2:         # repeated ellipsis
        return True
    return False


@dataclass
class OcrLine:
    text: str
    bbox: tuple[float, float, float, float]
    conf: float


class BaseOCREngine(ABC):
    name = "base"
    available = False

    @abstractmethod
    def ocr_image(self, image_path: str) -> list[OcrLine]:
        ...


class TesseractOCREngine(BaseOCREngine):
    name = "tesseract"

    def __init__(self) -> None:
        import pytesseract

        from ..config import find_tesseract
        cmd = find_tesseract()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        # use Vietnamese (+English) when the language data is installed
        self._lang = "eng"
        try:
            langs = set(pytesseract.get_languages(config=""))
            picked = [l for l in ("vie", "eng") if l in langs]
            if picked:
                self._lang = "+".join(picked)
        except Exception:
            pass
        logger.info("Tesseract OCR language: %s", self._lang)
        self.available = True

    def ocr_image(self, image_path: str) -> list[OcrLine]:
        import pytesseract
        from PIL import Image

        img = Image.open(image_path).convert("L")          # grayscale
        up = 1.0
        longest = max(img.size)
        if longest < 2600:                                  # upscale -> better accuracy
            up = 2600.0 / longest
            img = img.resize((int(img.width * up), int(img.height * up)))
        data = pytesseract.image_to_data(
            img, lang=getattr(self, "_lang", "eng"),
            config="--oem 1 --psm 3",                       # LSTM, auto page segmentation
            output_type=pytesseract.Output.DICT,
        )
        lines: dict[tuple[int, int, int], list] = {}
        for i in range(len(data["text"])):
            word = data["text"][i].strip()
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if not word or conf < 30:                       # drop low-confidence garbage
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x = data["left"][i] / up
            y = data["top"][i] / up
            w = data["width"][i] / up
            h = data["height"][i] / up
            lines.setdefault(key, []).append((word, x, y, w, h, conf))

        out: list[OcrLine] = []
        for words in lines.values():
            text = " ".join(w[0] for w in words)
            if _ocr_line_is_noise(text):                    # drop dotted/symbol noise
                continue
            x0 = min(w[1] for w in words)
            y0 = min(w[2] for w in words)
            x1 = max(w[1] + w[3] for w in words)
            y1 = max(w[2] + w[4] for w in words)
            conf = sum(w[5] for w in words) / len(words) / 100.0
            out.append(OcrLine(text=text, bbox=(x0, y0, x1, y1), conf=conf))
        out.sort(key=lambda l: (round(l.bbox[1], 1), round(l.bbox[0], 1)))
        return out


class PaddleOCREngine(BaseOCREngine):
    name = "paddleocr"

    def __init__(self) -> None:
        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        self.available = True

    def ocr_image(self, image_path: str) -> list[OcrLine]:
        result = self._ocr.ocr(image_path, cls=True)
        out: list[OcrLine] = []
        for page in result or []:
            for box, (text, conf) in page or []:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                out.append(
                    OcrLine(text=text, bbox=(min(xs), min(ys), max(xs), max(ys)),
                            conf=float(conf))
                )
        out.sort(key=lambda l: (round(l.bbox[1], 1), round(l.bbox[0], 1)))
        return out


class NullOCREngine(BaseOCREngine):
    name = "none"
    available = True

    def ocr_image(self, image_path: str) -> list[OcrLine]:
        logger.warning("No OCR engine installed; scanned content cannot be read.")
        return []


def get_ocr_engine() -> BaseOCREngine:
    caps = capabilities()
    if caps.get("tesseract"):
        try:
            return TesseractOCREngine()
        except Exception as exc:  # pragma: no cover
            logger.warning("Tesseract init failed: %s", exc)
    if caps.get("paddleocr"):
        try:
            return PaddleOCREngine()
        except Exception as exc:  # pragma: no cover
            logger.warning("PaddleOCR init failed: %s", exc)
    return NullOCREngine()
