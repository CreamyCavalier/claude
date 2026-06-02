"""FastAPI server for YouTube-to-guitar-tab transcription."""

import asyncio
import os
import uuid
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

app = FastAPI(title="AI Guitar Tab Generator")

# In-memory job store  {job_id: {status, message, tabs?, error?}}
_jobs: Dict[str, Dict[str, Any]] = {}

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


class TranscribeRequest(BaseModel):
    youtube_url: str
    max_duration: int = 60  # seconds


class JobStatus(BaseModel):
    status: str          # "processing" | "done" | "error" | "not_found"
    message: str = ""
    tabs: str = ""
    error: str = ""


@app.post("/api/transcribe", response_model=JobStatus)
async def start_transcription(req: TranscribeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "processing", "message": "Starting...", "tabs": "", "error": ""}
    background_tasks.add_task(_run_job, job_id, req.youtube_url, req.max_duration)
    return {**_jobs[job_id], "job_id": job_id}


@app.get("/api/status/{job_id}", response_model=dict)
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
        tabs = await asyncio.to_thread(
            transcribe_youtube, url, max_duration, set_status
        )
        _jobs[job_id] = {"status": "done", "message": "Done!", "tabs": tabs, "error": ""}
    except Exception as exc:
        _jobs[job_id] = {
            "status": "error",
            "message": "Failed",
            "tabs": "",
            "error": str(exc),
        }


# Serve the frontend for all non-API routes
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {"message": "Frontend not found. Run from the project root."}
