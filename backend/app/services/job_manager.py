"""In-memory job store + background worker pool."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..config import Settings
from ..models import (ConversionReport, ConvertOptions, JobInfo, JobStatus)
from . import pipeline

logger = logging.getLogger("formudoc.jobs")


@dataclass
class Job:
    id: str
    file_id: str
    filename: str
    options: ConvertOptions
    api_keys: list = field(default_factory=list)
    status: JobStatus = JobStatus.queued
    progress: int = 0
    stage: str = "queued"
    log: list[str] = field(default_factory=list)
    report: Optional[ConversionReport] = None
    error: Optional[str] = None
    out_path: Optional[str] = None
    xlsx_path: Optional[str] = None
    output_format: str = "docx"
    saved_path: Optional[str] = None
    preview: Optional[str] = None
    created: float = field(default_factory=time.time)


class JobManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=settings.max_workers)

    # ---------------------------------------------------------------- #
    def create(self, file_id: str, filename: str, options: ConvertOptions,
               api_keys: list | None = None, output_format: str = "docx") -> Job:
        job = Job(id=uuid.uuid4().hex[:12], file_id=file_id,
                  filename=filename, options=options, api_keys=api_keys or [],
                  output_format=(output_format or "docx"))
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run, job.id)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    # ---------------------------------------------------------------- #
    def _progress(self, job: Job):
        def cb(pct: int, stage: str, message: str):
            job.progress = max(job.progress, pct)
            job.stage = stage
            line = f"[{stage}] {message}"
            job.log.append(line)
            logger.info("job %s %d%% %s", job.id, pct, message)
        return cb

    def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        job.status = JobStatus.running
        job.log.append("[start] Conversion started")
        pdf_path = str(self.settings.upload_dir / f"{job.file_id}.pdf")
        out_path = str(self.settings.output_dir / f"{job.id}.docx")
        asset_dir = str(self.settings.asset_dir / job.id)
        try:
            import os
            os.makedirs(asset_dir, exist_ok=True)
            report = pipeline.run_pipeline(
                pdf_path, job.options, out_path, self.settings, asset_dir,
                self._progress(job), api_keys=job.api_keys,
            )
            job.report = report
            job.out_path = out_path
            # PDF -> Excel: rows of text (built from the .md the pipeline wrote)
            try:
                import os as _os
                md_src = _os.path.splitext(out_path)[0] + ".md"
                if _os.path.exists(md_src):
                    from . import xlsx_builder
                    xlsx_path = _os.path.splitext(out_path)[0] + ".xlsx"
                    with open(md_src, encoding="utf-8") as _fh:
                        xlsx_builder.build_xlsx_from_markdown(_fh.read(), xlsx_path)
                    job.xlsx_path = xlsx_path
            except Exception as _exc:  # noqa: BLE001
                logger.warning("Excel build skipped: %s", _exc)
            job.saved_path = self._save_to_downloads(job, out_path)
            job.preview = self._make_preview(report)
            # persist report
            with open(self.settings.job_dir / f"{job.id}.json", "w") as fh:
                json.dump(report.model_dump(), fh, indent=2)
            job.progress = 100
            job.stage = "done"
            job.status = JobStatus.done
            job.log.append("[done] Conversion finished successfully")
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.error
            job.error = str(exc)
            job.log.append(f"[error] {exc}")
            logger.error("Job %s failed: %s\n%s", job.id, exc, traceback.format_exc())

    @staticmethod
    def _safe_name(name: str) -> str:
        base = os.path.splitext(os.path.basename(name or "document"))[0]
        base = re.sub(r'[\\/:*?"<>|]', "_", base).strip() or "document"
        return base + ".docx"

    def _save_to_downloads(self, job: "Job", out_path: str) -> Optional[str]:
        """Copy the result into ~/Downloads. Saves ONLY the format the user asked
        for (Word .docx OR Excel .xlsx), plus the .md text sidecar -- it does not
        dump the other format the user did not pick."""
        try:
            downloads = Path.home() / "Downloads"
            if not downloads.exists():
                return None
            base_no_ext = os.path.splitext(out_path)[0]
            fmt = getattr(job, "output_format", "docx")
            if fmt == "xlsx" and os.path.exists(base_no_ext + ".xlsx"):
                primary_src, ext, label = base_no_ext + ".xlsx", ".xlsx", "Excel"
            else:
                primary_src, ext, label = out_path, ".docx", "Word"
            stem = self._safe_name(job.filename)[:-5]        # drop ".docx"
            dest = downloads / (stem + ext)
            i = 1
            while dest.exists():
                dest = downloads / f"{stem} ({i}){ext}"
                i += 1
            shutil.copy(primary_src, dest)
            job.log.append(f"[saved] {label} file saved to: {dest}")
            logger.info("Saved result to %s", dest)
            # clean text markdown sidecar (small, useful for copy/re-processing)
            md_src = base_no_ext + ".md"
            if os.path.exists(md_src):
                md_dest = os.path.splitext(str(dest))[0] + ".md"
                try:
                    shutil.copy(md_src, md_dest)
                    job.log.append(f"[saved] Markdown saved to: {md_dest}")
                except Exception:
                    pass
            return str(dest)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save to Downloads: %s", exc)
            return None

    @staticmethod
    def _make_preview(report: ConversionReport) -> str:
        lines = [
            "FormuDoc conversion summary",
            f"  Pages              : {report.pages}",
            f"  Classification     : {report.classification}",
            f"  Text blocks        : {report.detected_text_blocks}",
            f"  Tables             : {report.detected_tables}",
            f"  Figures            : {report.detected_figures}",
            f"  Formulas           : {report.detected_formulas}",
            f"  Editable equations : {report.editable_equations}",
            f"  Image equations    : {report.image_fallback_equations}",
            f"  Engines            : {report.engines_used}",
        ]
        if report.warnings:
            lines.append("  Warnings:")
            lines.extend(f"    - {w}" for w in report.warnings)
        return "\n".join(lines)

    def to_info(self, job: Job) -> JobInfo:
        return JobInfo(
            job_id=job.id, status=job.status, progress=job.progress,
            stage=job.stage, filename=job.filename, log=job.log[-200:],
            report=job.report, error=job.error,
            preview=job.preview,
            download_url=f"/api/download/{job.id}" if job.status == JobStatus.done else None,
            report_url=f"/api/report/{job.id}" if job.status == JobStatus.done else None,
            saved_path=job.saved_path,
        )
