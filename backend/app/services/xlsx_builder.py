"""PDF → Excel: turn the converted document into a simple .xlsx where every
non-empty text line becomes one row (with its page number).

Built from the Markdown the pipeline already produces, so it works for BOTH the
AI-council path and the offline path. No new model or API needed.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("formudoc.xlsx")

# a pandoc raw page-break block: ```{=openxml} ... ```
_PAGEBREAK = re.compile(r"```\{=openxml\}.*?```", re.S)
# markdown table-rule / horizontal-rule lines we don't want as rows
_RULE = re.compile(r"^\|?[\s:|_-]{3,}\|?$")


def _clean_line(line: str) -> str:
    line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)        # drop heading hashes
    line = re.sub(r"</?span[^>]*>", "", line)             # drop colour-span tags
    line = line.strip()
    return line


def build_xlsx_from_markdown(md: str, out_path: str) -> str:
    """Write out_path (.xlsx): columns [Trang, Nội dung], one row per text line."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Nội dung"
    ws.append(["Trang", "Nội dung"])
    hdr_fill = PatternFill("solid", fgColor="6D5EFC")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = hdr_fill
        c.alignment = Alignment(vertical="center")

    page = 1
    for part in _PAGEBREAK.split(md or ""):
        for raw in part.split("\n"):
            line = _clean_line(raw)
            if not line or line == "---" or line.startswith("```") or _RULE.match(line):
                continue
            ws.append([page, line])
        page += 1

    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = 110
    for row in ws.iter_rows(min_row=2):
        row[0].alignment = Alignment(horizontal="center", vertical="top")
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    wb.save(out_path)
    logger.info("xlsx built: %s (%d rows)", out_path, ws.max_row - 1)
    return out_path
