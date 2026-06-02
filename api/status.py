"""
Vercel serverless function: GET /api/status?prediction_id=xxx
Polls Replicate for completion, then converts MIDI output to ASCII tab.
"""

import io
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import mido
import requests

REPLICATE_API = "https://api.replicate.com/v1"


def _cors_headers(handler):
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


def check_replicate(prediction_id: str, token: str) -> dict:
    resp = requests.get(
        f"{REPLICATE_API}/predictions/{prediction_id}",
        headers={"Authorization": f"Token {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def midi_bytes_to_note_events(midi_bytes: bytes):
    """Parse MIDI bytes into (start_s, end_s, pitch, velocity_norm) tuples."""
    mid = mido.MidiFile(file=io.BytesIO(midi_bytes))
    tpb = mid.ticks_per_beat
    events = []

    for track in mid.tracks:
        tempo = 500000
        tick = 0
        seconds = 0.0
        note_starts: dict = {}

        for msg in track:
            delta_s = mido.tick2second(msg.time, tpb, tempo)
            tick += msg.time
            seconds += delta_s

            if msg.type == "set_tempo":
                tempo = msg.tempo
            elif msg.type == "note_on" and msg.velocity > 0:
                note_starts[msg.note] = (seconds, msg.velocity)
            elif msg.type in ("note_off",) or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                if msg.note in note_starts:
                    start_s, vel = note_starts.pop(msg.note)
                    events.append((start_s, seconds, msg.note, vel / 127.0))

    return events


def find_midi_url(output) -> str:
    """Locate the MIDI file URL in Replicate's output (handles different formats)."""
    if isinstance(output, str) and (".mid" in output.lower() or ".midi" in output.lower()):
        return output
    if isinstance(output, dict):
        for key in ("midi_file", "midi", "output"):
            val = output.get(key)
            if val and isinstance(val, str):
                return val
    if isinstance(output, list):
        for item in output:
            url = find_midi_url(item)
            if url:
                return url
    return ""


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        _cors_headers(self)
        self.end_headers()

    def do_GET(self):
        try:
            token = os.environ.get("REPLICATE_API_TOKEN", "")
            if not token:
                raise EnvironmentError("REPLICATE_API_TOKEN is not configured.")

            qs = parse_qs(urlparse(self.path).query)
            prediction_id = (qs.get("prediction_id") or [""])[0].strip()
            if not prediction_id:
                raise ValueError("prediction_id query param is required.")

            prediction = check_replicate(prediction_id, token)
            status = prediction.get("status", "unknown")

            if status in ("starting", "processing"):
                self._send_json({"status": "processing", "message": "AI is analyzing the audio..."})
                return

            if status == "failed":
                error = prediction.get("error") or "Replicate prediction failed."
                self._send_json({"status": "error", "error": error})
                return

            if status == "succeeded":
                output = prediction.get("output")
                midi_url = find_midi_url(output)
                if not midi_url:
                    raise ValueError(f"No MIDI file found in output: {output}")

                midi_resp = requests.get(midi_url, timeout=15)
                midi_resp.raise_for_status()

                note_events = midi_bytes_to_note_events(midi_resp.content)

                # Import from same api/ directory
                import sys, os as _os
                sys.path.insert(0, _os.path.dirname(__file__))
                from tab_gen import notes_to_tab

                tabs = notes_to_tab(note_events)
                self._send_json({"status": "done", "tabs": tabs})
                return

            self._send_json({"status": "processing", "message": f"Status: {status}"})

        except Exception as exc:
            self._send_json({"status": "error", "error": str(exc)}, status=500)

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        _cors_headers(self)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass
