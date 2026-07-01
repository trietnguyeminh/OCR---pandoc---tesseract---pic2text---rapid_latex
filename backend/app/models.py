"""Pydantic API schemas + internal dataclasses for the document model."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
#  Enums
# --------------------------------------------------------------------------- #
class ConvertMode(str, Enum):
    fast = "fast"                 # text-layer only, quickest
    scientific = "scientific"     # full layout + tables + formulas (default)
    ocr_heavy = "ocr_heavy"       # force OCR on every page


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class BlockType(str, Enum):
    title = "title"
    heading = "heading"
    paragraph = "paragraph"
    table = "table"
    figure = "figure"
    caption = "caption"
    formula = "formula"
    footnote = "footnote"
    header = "header"
    footer = "footer"
    list_item = "list_item"


# --------------------------------------------------------------------------- #
#  Internal document model (not serialised over the wire as-is)
# --------------------------------------------------------------------------- #
@dataclass
class Block:
    type: BlockType
    page: int
    bbox: tuple[float, float, float, float]      # x0, y0, x1, y1 (PDF coords)
    text: str = ""
    level: int = 0                               # heading level (1..6)
    column: int = 0                              # 0 = left/single, 1 = right
    latex: Optional[str] = None                  # for formulas
    image_path: Optional[str] = None             # for figures / formula fallback
    table_data: Optional[list[list[str]]] = None # for tables
    confidence: float = 1.0
    editable_equation: bool = False              # formula will be true OMML

    def sort_key(self) -> tuple[int, float, float]:
        # reading order: page -> column -> vertical -> horizontal
        return (self.page, self.column, round(self.bbox[1], 1), round(self.bbox[0], 1))


@dataclass
class PageInfo:
    number: int
    width: float
    height: float
    is_scanned: bool = False
    text_coverage: float = 0.0


@dataclass
class DocumentModel:
    blocks: list[Block] = field(default_factory=list)
    pages: list[PageInfo] = field(default_factory=list)
    source_classification: str = "born_digital"   # or "scanned" / "mixed"


# --------------------------------------------------------------------------- #
#  API request / response schemas
# --------------------------------------------------------------------------- #
class ConvertOptions(BaseModel):
    mode: ConvertMode = ConvertMode.scientific
    preserve_layout: bool = True
    detect_formulas: bool = True
    convert_formulas_editable: bool = True
    detect_tables: bool = True
    remove_headers_footers: bool = True


class AnalyzeResponse(BaseModel):
    file_id: str
    filename: str
    size_bytes: int
    pages: int
    classification: str
    scanned_pages: int
    capabilities: dict[str, bool]
    page_info: list[dict[str, Any]]


class ConvertRequest(BaseModel):
    file_id: str
    filename: Optional[str] = None        # original upload name (for nice output name)
    api_keys: list[str] = Field(default_factory=list)   # AI council keys ("provider:key")
    options: ConvertOptions = Field(default_factory=ConvertOptions)
    output_format: str = "docx"          # "docx" (Word) or "xlsx" (Excel)


class ConversionReport(BaseModel):
    pages: int = 0
    detected_text_blocks: int = 0
    detected_tables: int = 0
    detected_formulas: int = 0
    editable_equations: int = 0
    image_fallback_equations: int = 0
    detected_figures: int = 0
    removed_headers_footers: int = 0
    classification: str = "born_digital"
    engines_used: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class JobInfo(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = 0
    stage: str = ""
    filename: str = ""
    log: list[str] = Field(default_factory=list)
    report: Optional[ConversionReport] = None
    error: Optional[str] = None
    download_url: Optional[str] = None
    report_url: Optional[str] = None
    preview: Optional[str] = None
    saved_path: Optional[str] = None       # where we auto-saved the .docx (desktop)
