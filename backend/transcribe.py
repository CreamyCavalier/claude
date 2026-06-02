"""YouTube audio download + basic-pitch note detection pipeline."""

import os
import subprocess
import tempfile
from typing import Callable, Optional

import yt_dlp

from tab_gen import notes_to_tab


def _download_audio(url: str, output_dir: str, max_duration: int) -> str:
    """Download audio from YouTube and trim to max_duration seconds."""
    raw_path = os.path.join(output_dir, "audio_raw.wav")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(output_dir, "audio_raw.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Find the downloaded wav (yt-dlp may use a different name)
    for f in os.listdir(output_dir):
        if f.endswith(".wav"):
            raw_path = os.path.join(output_dir, f)
            break

    trimmed_path = os.path.join(output_dir, "audio.wav")
    subprocess.run(
        [
            "ffmpeg", "-i", raw_path,
            "-t", str(max_duration),
            "-ar", "22050", "-ac", "1",
            trimmed_path, "-y", "-loglevel", "quiet",
        ],
        check=True,
    )
    return trimmed_path


def transcribe_youtube(
    url: str,
    max_duration: int = 60,
    on_status: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Full pipeline: YouTube URL -> ASCII guitar tab string.

    max_duration: seconds of audio to process (keep low for speed).
    on_status: optional callback for status updates.
    """
    def status(msg: str) -> None:
        if on_status:
            on_status(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        status("Downloading audio from YouTube...")
        audio_path = _download_audio(url, tmpdir, max_duration)

        status("Loading AI model...")
        from basic_pitch.inference import predict  # lazy import (TF is slow to load)
        from basic_pitch import ICASSP_2022_MODEL_PATH

        status("Analyzing audio for notes (this takes ~30–60 s)...")
        _model_out, _midi, note_events = predict(
            audio_path,
            ICASSP_2022_MODEL_PATH,
            minimum_frequency=80.0,   # below low E on guitar
            maximum_frequency=1400.0, # above high e on guitar
            onset_threshold=0.5,
            frame_threshold=0.3,
        )

        status("Generating guitar tab...")
        return notes_to_tab(note_events)
