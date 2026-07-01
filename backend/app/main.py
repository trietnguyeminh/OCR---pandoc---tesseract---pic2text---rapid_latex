"""FastAPI entrypoint for FormuDoc Converter.

Endpoints
    GET  /health
    POST /api/analyze-pdf      (multipart file)        -> AnalyzeResponse
    POST /api/convert          (json: file_id+options) -> {job_id}
    GET  /api/jobs/{job_id}                              -> JobInfo
    GET  /api/download/{job_id}                          -> .docx
    GET  /api/report/{job_id}                            -> report JSON
"""
from __future__ import annotations

import logging
import uuid

import fitz
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import capabilities, frontend_dist, get_settings
from .models import (AnalyzeResponse, ConvertRequest, JobStatus)
from .services.job_manager import JobManager
from .services.pdf_analyzer import analyze as analyze_pdf
from .utils.logging_config import configure_root

configure_root()
logger = logging.getLogger("formudoc.api")
settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs = JobManager(settings)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "capabilities": capabilities(),
    }


@app.post("/api/analyze-pdf", response_model=AnalyzeResponse)
async def analyze_pdf_endpoint(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only .pdf files are supported")
    data = await file.read()
    size = len(data)
    if size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit")

    file_id = uuid.uuid4().hex[:12]
    dest = settings.upload_dir / f"{file_id}.pdf"
    dest.write_bytes(data)

    # validate + analyze
    try:
        with fitz.open(str(dest)) as doc:
            if doc.page_count == 0:
                raise ValueError("PDF has no pages")
        analysis = analyze_pdf(str(dest))
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not read PDF: {exc}")

    return AnalyzeResponse(
        file_id=file_id,
        filename=file.filename,
        size_bytes=size,
        pages=analysis.page_count,
        classification=analysis.classification,
        scanned_pages=analysis.scanned_pages,
        capabilities=capabilities(),
        page_info=[
            {"number": p.number, "width": round(p.width, 1),
             "height": round(p.height, 1), "is_scanned": p.is_scanned,
             "chars": p.char_count, "text_coverage": p.text_coverage}
            for p in analysis.pages
        ],
    )


@app.post("/api/convert")
def convert_endpoint(req: ConvertRequest):
    pdf_path = settings.upload_dir / f"{req.file_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "file_id not found — call /api/analyze-pdf first")
    job = jobs.create(req.file_id, req.filename or f"{req.file_id}.pdf", req.options, req.api_keys)
    return {"job_id": job.id, "status": job.status}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return jobs.to_info(job)


@app.get("/api/download/{job_id}")
def download(job_id: str):
    job = jobs.get(job_id)
    if not job or job.status != JobStatus.done or not job.out_path:
        raise HTTPException(404, "result not ready")
    name = job.filename.replace(".pdf", "") + ".docx"
    return FileResponse(
        job.out_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=name,
    )


@app.get("/api/report/{job_id}")
def report(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if not job.report:
        return JSONResponse({"status": job.status, "message": "report not ready"})
    return job.report.model_dump()


@app.get("/api/markdown/{job_id}")
def markdown(job_id: str):
    """Return the converted document as plain Markdown text (for copy-in-app)."""
    import os as _os
    from fastapi.responses import PlainTextResponse
    job = jobs.get(job_id)
    if not job or job.status != JobStatus.done or not job.out_path:
        raise HTTPException(404, "result not ready")
    md_path = _os.path.splitext(job.out_path)[0] + ".md"
    if not _os.path.exists(md_path):
        raise HTTPException(404, "no markdown for this job")
    with open(md_path, encoding="utf-8") as fh:
        return PlainTextResponse(fh.read(), media_type="text/markdown; charset=utf-8")


# --------------------------------------------------------------------------- #
#  Serve the built React UI from the same origin (single-app mode).
#  Registered LAST so /health and /api/* always take precedence.
# --------------------------------------------------------------------------- #
from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = frontend_dist()
if _DIST is not None:
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="ui")
    logger.info("Serving bundled UI from %s", _DIST)
else:
    @app.get("/")
    def _no_ui():
        return {
            "message": "FormuDoc API is running, but the UI is not built yet.",
            "hint": "Run `cd frontend && npm run build`, or use the desktop app.",
            "docs": "/docs",
        }
