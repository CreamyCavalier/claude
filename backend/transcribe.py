"""YouTube audio download + basic-pitch note detection pipeline."""

import os
import subprocess
import sys
import tempfile
from typing import Callable, Optional

import yt_dlp

# basic-pitch calls pkg_resources.resource_filename to locate its model files.
# On some macOS/Python 3.11 setups setuptools doesn't register pkg_resources
# even when installed. Polyfill the one function basic-pitch actually needs.
try:
    import pkg_resources  # noqa: F401
except ImportError:
    import importlib
    import types

    _mock = types.ModuleType("pkg_resources")

    def _resource_filename(package_name: str, resource_name: str) -> str:
        pkg = importlib.import_module(package_name)
        return os.path.join(os.path.dirname(pkg.__file__), resource_name)

    _mock.resource_filename = _resource_filename
    sys.modules["pkg_resources"] = _mock

from tab_gen import notes_to_tab


def _download_audio(url: str, output_dir: str, max_duration: int) -> str:
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(output_dir, "audio_raw.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    raw_path = next(
        (os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".wav")),
        os.path.join(output_dir, "audio_raw.wav"),
    )

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
    def status(msg: str) -> None:
        if on_status:
            on_status(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        status("Downloading audio from YouTube...")
        audio_path = _download_audio(url, tmpdir, max_duration)

        status("Loading AI model...")
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH

        status("Analyzing audio — this takes 30–60 s...")
        _model_out, _midi, note_events = predict(
            audio_path,
            ICASSP_2022_MODEL_PATH,
            minimum_frequency=80.0,
            maximum_frequency=1400.0,
            onset_threshold=0.5,
            frame_threshold=0.3,
        )

        status("Generating guitar tab...")
        return notes_to_tab(note_events)
