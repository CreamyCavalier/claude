"""FastAPI server for YouTube-to-guitar-tab transcription."""

import asyncio
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="AI Guitar Tab Generator")

_jobs: Dict[str, Dict[str, Any]] = {}

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


class TranscribeRequest(BaseModel):
    youtube_url: str
    max_duration: int = 60


@app.post("/api/transcribe")
async def start_transcription(req: TranscribeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "processing", "message": "Starting...", "tabs": "", "error": ""}
    background_tasks.add_task(_run_job, job_id, req.youtube_url, req.max_duration)
    return {"job_id": job_id, **_jobs[job_id]}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, **job}


async def _run_job(job_id: str, url: str, max_duration: int) -> None:
    def set_status(msg: str) -> None:
        if job_id in _jobs:
            _jobs[job_id]["message"] = msg

    try:
        from transcribe import transcribe_youtube
        tabs = await asyncio.to_thread(transcribe_youtube, url, max_duration, set_status)
        _jobs[job_id] = {"status": "done", "message": "Done!", "tabs": tabs, "error": ""}
    except Exception as exc:
        _jobs[job_id] = {
            "status": "error",
            "message": "Failed",
            "tabs": "",
            "error": str(exc),
        }


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
