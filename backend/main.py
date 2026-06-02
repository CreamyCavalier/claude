"""FastAPI server for YouTube-to-guitar-tab transcription."""

import asyncio
import io
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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
    _jobs[job_id] = {"status": "processing", "message": "Starting...", "tracks": [], "duration": 0.0, "error": ""}
    background_tasks.add_task(_run_job, job_id, req.youtube_url, req.max_duration)
    return {"job_id": job_id, **_jobs[job_id]}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, **job}


@app.get("/api/export/{job_id}/{track_idx}")
async def export_midi(job_id: str, track_idx: int):
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(status_code=404, detail="Job not found or not complete")
    tracks = job.get("tracks", [])
    if track_idx >= len(tracks):
        raise HTTPException(status_code=404, detail="Track not found")
    track = tracks[track_idx]
    from midi_export import notes_to_midi_bytes
    instrument = 34 if track["tuning"] == "bass" else 25
    midi_bytes = notes_to_midi_bytes(track["note_events"], instrument=instrument)
    filename = f"{track['name'].lower()}_tab.mid"
    return StreamingResponse(
        io.BytesIO(midi_bytes),
        media_type="audio/midi",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/export/gp/{job_id}/{track_idx}")
async def export_gp(job_id: str, track_idx: int):
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(status_code=404, detail="Job not found or not complete")
    tracks = job.get("tracks", [])
    if track_idx >= len(tracks):
        raise HTTPException(status_code=404, detail="Track not found")
    track = tracks[track_idx]
    from gp_export import notes_to_gp5_bytes
    gp_bytes = notes_to_gp5_bytes(
        track["columns"],
        tuning=track["tuning"],
        tempo_bpm=120,
        track_name=track["name"],
    )
    filename = f"{track['name'].lower()}_tab.gp5"
    return StreamingResponse(
        io.BytesIO(gp_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _run_job(job_id: str, url: str, max_duration: int) -> None:
    def set_status(msg: str) -> None:
        if job_id in _jobs:
            _jobs[job_id]["message"] = msg

    try:
        from transcribe import transcribe_youtube
        result = await asyncio.to_thread(transcribe_youtube, url, max_duration, set_status)
        _jobs[job_id] = {
            "status": "done",
            "message": "Done!",
            "tracks": result["tracks"],
            "duration": result["duration"],
            "error": "",
        }
    except Exception as exc:
        _jobs[job_id] = {
            "status": "error",
            "message": "Failed",
            "tracks": [],
            "duration": 0.0,
            "error": str(exc),
        }


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
