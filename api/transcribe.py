"""
Vercel serverless function: POST /api/transcribe
Accepts {youtube_url} → extracts audio URL via yt-dlp → submits to Replicate.
Returns {prediction_id}.
"""

import json
import os
from http.server import BaseHTTPRequestHandler

import requests
import yt_dlp

REPLICATE_API = "https://api.replicate.com/v1"
BASIC_PITCH_MODEL = "spotify/basic-pitch"


def _cors_headers(handler):
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


def get_youtube_audio_url(youtube_url: str) -> str:
    """Extract a direct audio stream URL from a YouTube video (no download)."""
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio[acodec=opus]/bestaudio",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)

    if info.get("url"):
        return info["url"]

    for fmt in sorted(
        info.get("formats", []),
        key=lambda f: f.get("abr") or 0,
        reverse=True,
    ):
        if fmt.get("acodec") not in (None, "none") and fmt.get("url"):
            return fmt["url"]

    raise ValueError("Could not extract an audio stream URL from this video.")


def submit_to_replicate(audio_url: str, token: str) -> str:
    """Submit a prediction to Replicate's hosted basic-pitch model."""
    resp = requests.post(
        f"{REPLICATE_API}/models/{BASIC_PITCH_MODEL}/predictions",
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Prefer": "wait",  # wait up to 60 s for a fast response
        },
        json={
            "input": {
                "audio_file": audio_url,
                "onset_threshold": 0.5,
                "frame_threshold": 0.3,
                "minimum_frequency": 80,
                "maximum_frequency": 1400,
            }
        },
        timeout=25,
    )
    resp.raise_for_status()
    return resp.json()["id"]


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        _cors_headers(self)
        self.end_headers()

    def do_POST(self):
        try:
            token = os.environ.get("REPLICATE_API_TOKEN", "")
            if not token:
                raise EnvironmentError(
                    "REPLICATE_API_TOKEN is not set. "
                    "Add it in your Vercel project settings → Environment Variables."
                )

            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            youtube_url = body.get("youtube_url", "").strip()
            if not youtube_url:
                raise ValueError("youtube_url is required.")

            audio_url = get_youtube_audio_url(youtube_url)
            prediction_id = submit_to_replicate(audio_url, token)

            self._send_json({"prediction_id": prediction_id})
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        _cors_headers(self)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass  # suppress Vercel function logs noise
