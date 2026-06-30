"""Tier 2 — Layout-aware extraction.

Adapter interface (DocLayNet / PubLayNet style block taxonomy):

    BaseLayoutEngine
      |- PyMuPDFLayoutEngine   (no model required; font/geometry heuristics)
      |- DoclingLayoutEngine   (optional; uses IBM Docling if installed)

Produces an ordered :class:`DocumentModel` of typed blocks:
title / heading / paragraph / table / figure / caption / formula / header /
footer. Handles reading order (incl. two-column papers), repeated header/footer
removal, figure extraction and formula crops.
"""
from __future__ import annotations

import logging
import re
import statistics
from abc import ABC, abstractmethod

import fitz
from PIL import Image

from ..config import capabilities
from ..models import Block, BlockType, ConvertOptions, DocumentModel, PageInfo
from .formula_engine import (looks_like_formula, _MATH_CHARS,
                              _MATH_FONT_HINTS)
from .ocr_engine import BaseOCREngine
from .pdf_analyzer import PdfAnalysis
from .table_engine import DetectedTable

logger = logging.getLogger("formudoc.layout")

_CAPTION_RE = re.compile(r"^(figure|fig\.?|table|tab\.?|hình|bảng|chart|scheme)\s*\d",
                         re.IGNORECASE)
_FOOTNOTE_RE = re.compile(r"^\s*(\[\d+\]|\d+\.)\s")
_TABLE_PAD = 2.0


def _bbox_inside(inner, outer, pad=_TABLE_PAD) -> bool:
    ix0, iy0, ix1, iy1 = inner
    ox0, oy0, ox1, oy1 = outer
    cx = (ix0 + ix1) / 2
    cy = (iy0 + iy1) / 2
    return (ox0 - pad) <= cx <= (ox1 + pad) and (oy0 - pad) <= cy <= (oy1 + pad)


def _strip_eq_fragments(text: str) -> str:
    """Remove runs of >=4 consecutive single-character tokens (leftover equation
    fragments like '1 0 3 2 0' or '3 ( ) 4 F x x') while keeping real words and
    isolated variables in prose (e.g. 'khi x thì y')."""
    frag = set("+-=(){}[]/<>|.,;:")
    def is_frag(t):
        return len(t) == 1 and (t.isalnum() or t in frag)
    toks = text.split()          # split on any whitespace (drops empties)
    out, run = [], []
    def flush():
        if not (len(run) >= 3 and all(is_frag(t) for t in run)):
            out.extend(run)
    for t in toks:
        if is_frag(t):
            run.append(t)
        else:
            flush(); run.clear(); out.append(t)
    flush()
    return " ".join(x for x in out if x).strip()


def _is_text_line(t: str) -> bool:
    """True if a line has at least one real word (len>=2 with a letter). Drops
    pure equation-fragment lines (the scrambled MathType vertical pile)."""
    return any(len(tok) >= 2 and any(c.isalpha() for c in tok) for tok in t.split())


def _is_math_span(sp) -> bool:
    """A single text span is 'math' if its font is a math font or it contains
    math symbols / MathType PUA glyphs."""
    font = (sp.get("font") or "").lower()
    t = sp.get("text") or ""
    if any(h in font for h in _MATH_FONT_HINTS):
        return True
    return any((c in _MATH_CHARS) or (0xE000 <= ord(c) <= 0xF8FF) for c in t)


def _math_fraction(spans) -> float:
    """Fraction of a block's characters that are mathematical (math font span,
    math symbol, or MathType PUA glyph). Used to keep Vietnamese sentences as
    text and only treat predominantly-math blocks as formulas."""
    math_chars = 0
    total = 0
    for sp in spans:
        t = (sp.get("text") or "").strip()
        if not t:
            continue
        total += len(t)
        font = (sp.get("font") or "").lower()
        if any(h in font for h in _MATH_FONT_HINTS):
            math_chars += len(t)
        else:
            math_chars += sum(1 for c in t
                              if c in _MATH_CHARS or 0xE000 <= ord(c) <= 0xF8FF)
    return math_chars / total if total else 0.0


class BaseLayoutEngine(ABC):
    name = "base"

    @abstractmethod
    def extract(self, pdf_path: str, options: ConvertOptions, analysis: PdfAnalysis,
                tables: dict[int, list[DetectedTable]], ocr_engine: BaseOCREngine,
                asset_dir: str, dpi: int) -> DocumentModel:
        ...


class PyMuPDFLayoutEngine(BaseLayoutEngine):
    name = "pymupdf"

    def extract(self, pdf_path, options, analysis, tables, ocr_engine,
                asset_dir, dpi) -> DocumentModel:
        doc_model = DocumentModel(source_classification=analysis.classification)
        scale = dpi / 72.0
        force_ocr = options.mode.value == "ocr_heavy"

        with fitz.open(pdf_path) as doc:
            median_size = self._median_font_size(doc)
            for pidx, page in enumerate(doc):
                rect = page.rect
                pinfo = PageInfo(
                    number=pidx, width=rect.width, height=rect.height,
                    is_scanned=analysis.pages[pidx].is_scanned,
                    text_coverage=analysis.pages[pidx].text_coverage,
                )
                doc_model.pages.append(pinfo)

                page_img_path = f"{asset_dir}/page_{pidx}.png"
                page.get_pixmap(dpi=dpi).save(page_img_path)

                use_ocr = force_ocr or pinfo.is_scanned
                if use_ocr:
                    doc_model.blocks.extend(
                        self._ocr_page(pidx, page_img_path, scale, ocr_engine)
                    )
                else:
                    doc_model.blocks.extend(
                        self._extract_text_page(
                            doc, page, pidx, options, tables.get(pidx, []),
                            page_img_path, scale, median_size, asset_dir,
                        )
                    )
                # tables as their own blocks
                if options.detect_tables:
                    for t in tables.get(pidx, []):
                        doc_model.blocks.append(self._table_block(t, page_img_path, scale, asset_dir))

        if options.remove_headers_footers:
            self._mark_headers_footers(doc_model)

        doc_model.blocks.sort(key=lambda b: b.sort_key())
        return doc_model

    # ----------------------------------------------------------------- #
    def _median_font_size(self, doc) -> float:
        sizes = []
        for page in doc:
            for b in page.get_text("dict").get("blocks", []):
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        sizes.append(span["size"])
        return statistics.median(sizes) if sizes else 11.0

    def _columns(self, blocks, page_width) -> dict:
        """Return {block_index: column} using x-center bimodality."""
        centers = [((b["bbox"][0] + b["bbox"][2]) / 2, i) for i, b in enumerate(blocks)]
        if len(centers) < 4:
            return {i: 0 for _, i in centers}
        mid = page_width / 2
        left = [c for c, _ in centers if c < mid]
        right = [c for c, _ in centers if c >= mid]
        # two-column only if both sides are well populated and separated
        if len(left) >= 2 and len(right) >= 2 and right and left and \
                (min(right) - max(left)) > -page_width * 0.05:
            return {i: (0 if c < mid else 1) for c, i in centers}
        return {i: 0 for _, i in centers}

    def _extract_text_page(self, doc, page, pidx, options, page_tables,
                           page_img_path, scale, median_size, asset_dir):
        data = page.get_text("dict")
        raw_blocks = [b for b in data.get("blocks", []) if b.get("type", 0) == 0
                      and b.get("lines")]
        col_map = self._columns(raw_blocks, page.rect.width) if options.preserve_layout \
            else {i: 0 for i in range(len(raw_blocks))}

        out: list[Block] = []
        page_im = Image.open(page_img_path)

        def crop_spans(span_list, suffix):
            mpad = 5.0   # widen margins so equations are not clipped ("cắt ẩu")
            xs0 = min(sp["bbox"][0] for sp in span_list) - mpad
            ys0 = min(sp["bbox"][1] for sp in span_list) - mpad
            xs1 = max(sp["bbox"][2] for sp in span_list) + mpad
            ys1 = max(sp["bbox"][3] for sp in span_list) + mpad
            fbbox = (xs0, ys0, xs1, ys1)
            crop_path = f"{asset_dir}/formula_p{pidx}_{suffix}.png"
            self._crop(page_im, fbbox, scale, crop_path)
            ftext = " ".join(sp["text"] for sp in span_list)
            return Block(type=BlockType.formula, page=pidx, bbox=fbbox,
                         text=ftext, image_path=crop_path)

        for i, b in enumerate(raw_blocks):
            bbox = tuple(b["bbox"])
            if options.detect_tables and any(_bbox_inside(bbox, t.bbox) for t in page_tables):
                continue
            spans = [s for line in b["lines"] for s in line["spans"]]
            raw_text = "".join(
                ("\n" if li > 0 else "") + "".join(s["text"] for s in line["spans"])
                for li, line in enumerate(b["lines"])
            ).strip()
            if not raw_text:
                continue
            column = col_map.get(i, 0)
            max_size = max((s["size"] for s in spans), default=median_size)

            math_spans = [s for s in spans if _is_math_span(s)] if options.detect_formulas else []
            total_chars = sum(len((s.get("text") or "").strip()) for s in spans) or 1
            math_chars = sum(len((s.get("text") or "").strip()) for s in math_spans)
            math_frac = math_chars / total_chars
            # clean text from non-math spans only (drops scrambled MathType glyphs)
            clean_lines = []
            for line in b["lines"]:
                t = "".join(sp["text"] for sp in line["spans"]
                            if not (options.detect_formulas and _is_math_span(sp))).strip()
                if not t:
                    continue
                t = _strip_eq_fragments(t)
                if t and _is_text_line(t):       # keep prose lines, drop fragment piles
                    clean_lines.append(t)
            clean_text = "\n".join(clean_lines).strip()

            # (a) whole block is an equation
            if math_spans and (math_frac >= 0.6 or not clean_text):
                fb = crop_spans(spans, f"{i}")
                fb.column = column
                out.append(fb)
                continue
            # (b) mixed block: clean text paragraph + cropped equation(s)
            if math_spans and clean_text:
                para = Block(type=BlockType.paragraph, page=pidx, bbox=bbox,
                             text=clean_text, column=column)
                self._classify_text(para, clean_text, max_size, median_size, pidx)
                out.append(para)
                fb = crop_spans(math_spans, f"{i}m")
                fb.column = column
                out.append(fb)
                continue
            # (c) text only
            block = Block(type=BlockType.paragraph, page=pidx, bbox=bbox,
                          text=clean_text or raw_text, column=column)
            self._classify_text(block, clean_text or raw_text, max_size, median_size, pidx)
            out.append(block)

        # figures / embedded images
        out.extend(self._extract_images(doc, page, pidx, page_img_path, scale, asset_dir))
        return out

    def _classify_text(self, block, text, max_size, median_size, pidx):
        if _CAPTION_RE.match(text):
            block.type = BlockType.caption
        elif _FOOTNOTE_RE.match(text) and max_size < median_size * 0.95:
            block.type = BlockType.footnote
        elif max_size >= median_size * 1.55 and len(text.split()) <= 18 and "\n" not in text:
            block.type = BlockType.title if (pidx == 0 and max_size >= median_size * 1.9) \
                else BlockType.heading
            ratio = max_size / median_size
            block.level = 1 if ratio >= 1.9 else (2 if ratio >= 1.55 else 3)

    def _extract_images(self, doc, page, pidx, page_img_path, scale, asset_dir):
        figs: list[Block] = []
        try:
            infos = page.get_image_info(xrefs=True)
        except Exception:
            infos = []
        page_im = None
        for j, info in enumerate(infos):
            bbox = info.get("bbox")
            if not bbox:
                continue
            w = (bbox[2] - bbox[0]); h = (bbox[3] - bbox[1])
            if w < 16 or h < 16:        # ignore icons / rules
                continue
            xref = info.get("xref", 0)
            out_path = f"{asset_dir}/figure_p{pidx}_{j}.png"
            saved = False
            if xref:
                try:
                    ext = doc.extract_image(xref)
                    with open(f"{asset_dir}/figure_p{pidx}_{j}.{ext['ext']}", "wb") as fh:
                        fh.write(ext["image"])
                    out_path = f"{asset_dir}/figure_p{pidx}_{j}.{ext['ext']}"
                    saved = True
                except Exception:
                    saved = False
            if not saved:
                if page_im is None:
                    page_im = Image.open(page_img_path)
                self._crop(page_im, bbox, scale, out_path)
            figs.append(Block(type=BlockType.figure, page=pidx, bbox=tuple(bbox),
                              image_path=out_path,
                              column=0 if (bbox[0] + bbox[2]) / 2 < page.rect.width / 2 else 1))
        return figs

    def _ocr_page(self, pidx, page_img_path, scale, ocr_engine):
        lines = ocr_engine.ocr_image(page_img_path)
        blocks: list[Block] = []
        # group OCR lines into paragraphs by vertical proximity
        para: list = []
        prev_bottom = None
        for ln in lines:
            x0, y0, x1, y1 = [c / scale for c in ln.bbox]
            if prev_bottom is not None and (y0 - prev_bottom) > (y1 - y0) * 1.3:
                blocks.append(self._para_from_lines(pidx, para))
                para = []
            para.append((ln.text, (x0, y0, x1, y1), ln.conf))
            prev_bottom = y1
        if para:
            blocks.append(self._para_from_lines(pidx, para))
        return [b for b in blocks if b and b.text.strip()]

    @staticmethod
    def _para_from_lines(pidx, para):
        if not para:
            return None
        text = "\n".join(p[0] for p in para)
        x0 = min(p[1][0] for p in para); y0 = min(p[1][1] for p in para)
        x1 = max(p[1][2] for p in para); y1 = max(p[1][3] for p in para)
        conf = sum(p[2] for p in para) / len(para)
        return Block(type=BlockType.paragraph, page=pidx, bbox=(x0, y0, x1, y1),
                     text=text, confidence=conf)

    @staticmethod
    def _table_block(t: DetectedTable, page_img_path, scale, asset_dir):
        block = Block(type=BlockType.table, page=t.page, bbox=t.bbox,
                      table_data=t.cells, confidence=t.confidence,
                      column=0)
        if t.confidence < 0.5:          # low confidence -> keep an image fallback
            crop_path = f"{asset_dir}/table_p{t.page}_{int(t.bbox[1])}.png"
            try:
                PyMuPDFLayoutEngine._crop(Image.open(page_img_path), t.bbox, scale, crop_path)
                block.image_path = crop_path
            except Exception:
                pass
        return block

    @staticmethod
    def _crop(page_im: Image.Image, bbox, scale, out_path):
        x0, y0, x1, y1 = [c * scale for c in bbox]
        x0 = max(0, int(x0) - 2); y0 = max(0, int(y0) - 2)
        x1 = min(page_im.width, int(x1) + 2); y1 = min(page_im.height, int(y1) + 2)
        if x1 <= x0 or y1 <= y0:
            return
        page_im.crop((x0, y0, x1, y1)).save(out_path)

    def _mark_headers_footers(self, doc_model: DocumentModel):
        npages = len(doc_model.pages) or 1
        if npages < 2:
            return
        zone: dict[str, set[int]] = {}
        candidates: dict[str, list[Block]] = {}
        for b in doc_model.blocks:
            if b.type not in (BlockType.paragraph, BlockType.footnote, BlockType.heading):
                continue
            ph = doc_model.pages[b.page].height
            top = b.bbox[3] < ph * 0.10
            bot = b.bbox[1] > ph * 0.90
            if not (top or bot):
                continue
            key = re.sub(r"\d+", "#", b.text.lower()).strip()
            key = f"{'H' if top else 'F'}::{key}"
            zone.setdefault(key, set()).add(b.page)
            candidates.setdefault(key, []).append(b)
        threshold = max(2, int(npages * 0.4))
        for key, pageset in zone.items():
            if len(pageset) >= threshold:
                for b in candidates[key]:
                    b.type = BlockType.header if key.startswith("H") else BlockType.footer


class DoclingLayoutEngine(BaseLayoutEngine):
    """Optional advanced engine backed by IBM Docling (DocLayNet models).

    Falls back transparently: if anything goes wrong the orchestrator retries
    with :class:`PyMuPDFLayoutEngine`.
    """

    name = "docling"

    def __init__(self) -> None:
        from docling.document_converter import DocumentConverter  # noqa: F401

    def extract(self, pdf_path, options, analysis, tables, ocr_engine,
                asset_dir, dpi) -> DocumentModel:
        from docling.document_converter import DocumentConverter

        conv = DocumentConverter()
        result = conv.convert(pdf_path)
        dl = result.document
        doc_model = DocumentModel(source_classification=analysis.classification)
        for p in analysis.pages:
            doc_model.pages.append(PageInfo(number=p.number, width=p.width,
                                            height=p.height, is_scanned=p.is_scanned))
        order = 0
        for item, _level in dl.iterate_items():
            label = getattr(item, "label", "") or ""
            text = getattr(item, "text", "") or ""
            page_no = 0
            try:
                page_no = item.prov[0].page_no - 1
            except Exception:
                page_no = 0
            btype = self._map_label(str(label), text)
            order += 1
            doc_model.blocks.append(
                Block(type=btype, page=max(page_no, 0),
                      bbox=(0, order, 0, order), text=text)
            )
        # tables via pdfplumber are usually richer; merge them in
        if options.detect_tables:
            for pidx, tlist in tables.items():
                for t in tlist:
                    doc_model.blocks.append(
                        Block(type=BlockType.table, page=pidx, bbox=t.bbox,
                              table_data=t.cells, confidence=t.confidence))
        doc_model.blocks.sort(key=lambda b: b.sort_key())
        return doc_model

    @staticmethod
    def _map_label(label: str, text: str) -> BlockType:
        l = label.lower()
        if "title" in l:
            return BlockType.title
        if "section" in l or "head" in l:
            return BlockType.heading
        if "table" in l:
            return BlockType.table
        if "picture" in l or "figure" in l:
            return BlockType.figure
        if "caption" in l:
            return BlockType.caption
        if "formula" in l or "equation" in l:
            return BlockType.formula
        if "footnote" in l:
            return BlockType.footnote
        return BlockType.paragraph


def get_layout_engine(prefer_advanced: bool = False) -> BaseLayoutEngine:
    if prefer_advanced and capabilities().get("docling"):
        try:
            logger.info("Using Docling layout engine")
            return DoclingLayoutEngine()
        except Exception as exc:  # pragma: no cover
            logger.warning("Docling unavailable (%s); using PyMuPDF engine", exc)
    return PyMuPDFLayoutEngine()
