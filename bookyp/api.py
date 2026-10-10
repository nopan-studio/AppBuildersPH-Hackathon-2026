"""Small web API wrapping :func:`bookyp.pipeline.process`.

Endpoints
    GET  /api/health   -> Ollama/model status
    POST /api/scan     -> multipart upload of one or more images

When ``web/dist`` exists it is served at ``/`` so a single process hosts both
the API and the built UI.
"""

from __future__ import annotations

import os
import tempfile
import threading
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import __version__, export, extract, ocr, pipeline

ALLOWED_TIERS = set(ocr.OCR_TIERS)

app = FastAPI(title="Bookyp API", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

_lock = threading.Lock()
_engine: Optional[ocr.OcrEngine] = None
_engine_tier: Optional[str] = None


def _get_engine(tier: str) -> ocr.OcrEngine:
    """Build the OCR engine once and reuse it across requests."""
    global _engine, _engine_tier
    if _engine is None or _engine_tier != tier:
        _engine = ocr.OcrEngine(tier)
        _engine_tier = tier
    return _engine


@app.get("/api/health")
def health(model: str = extract.DEFAULT_MODEL) -> Dict[str, Any]:
    ok, message = extract.check_ollama(model)
    return {"ok": ok, "message": message, "model": model}


@app.post("/api/scan")
async def scan(
    files: List[UploadFile] = File(...),
    model: str = Form(extract.DEFAULT_MODEL),
    ocr_tier: str = Form("small"),
    min_conf: float = Form(pipeline.DEFAULT_MIN_CONF),
) -> Dict[str, Any]:
    if ocr_tier not in ALLOWED_TIERS:
        raise HTTPException(
            status_code=400,
            detail="ocr_tier must be one of {}".format(", ".join(sorted(ALLOWED_TIERS))),
        )

    results: List[Dict[str, Any]] = []
    try:
        engine = _get_engine(ocr_tier)
    except ocr.OcrError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    for upload in files:
        suffix = os.path.splitext(upload.filename or "")[1] or ".png"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(await upload.read())
                tmp_path = tmp.name
            with _lock:
                result = pipeline.process(
                    tmp_path,
                    model=model,
                    ocr_tier=ocr_tier,
                    min_conf=min_conf,
                    ocr_engine=engine,
                )
            result["file"] = upload.filename or result["file"]
            results.append(result)
        except pipeline.PipelineError as exc:
            results.append(
                {
                    "file": upload.filename,
                    "status": "needs_review",
                    "review_reasons": ["error: {}".format(exc)],
                }
            )
        except (ocr.OcrError, extract.ExtractError) as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return {
        "model": model,
        "ocr_tier": ocr_tier,
        "ocr_device": getattr(engine, "device", "cpu"),
        "results": results,
    }


@app.post("/api/export")
def export_scan(payload: Dict[str, Any] = Body(...)) -> Response:
    """Turn a previous scan response (or a raw list) into an .xlsx download."""
    results = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(results, list):
        raise HTTPException(status_code=400, detail="expected a 'results' array")
    try:
        data = export.write_xlsx(results)
    except export.ExportError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    filename = export.xlsx_filename(results)
    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": 'attachment; filename="{}"'.format(filename)},
    )


_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
