"""YouTube audio download + basic-pitch note detection pipeline."""

import os
import subprocess
import sys
import tempfile
from typing import Callable, Dict, List, Optional, Any

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

from tab_gen import notes_to_tab, notes_to_columns

# Guitar's lowest string is E2 = MIDI 40. Only notes below that are true bass.
BASS_PITCH_THRESHOLD = 40
MIN_BASS_NOTES = 10
MIN_VOICE_NOTES = 25  # minimum notes per voice to create a separate track


def _split_guitar_voices(events):
    """Separate guitar events into lead (melodic) and rhythm (chordal) voices.

    Bins with 3+ simultaneous pitches → chordal (rhythm/strumming).
    Bins with 1-2 notes → melodic (lead/single-note lines).
    Returns a list of (events, name) pairs — either one pair or two.
    """
    q = 0.08  # 80 ms quantise window
    bins: dict = {}
    for e in events:
        start, _, _, amp, *_ = e
        if amp < 0.2:
            continue
        b = int(start / q)
        bins.setdefault(b, []).append(e)

    lead, rhythm = [], []
    for bin_events in bins.values():
        if len(bin_events) >= 3:
            rhythm.extend(bin_events)
        else:
            lead.extend(bin_events)

    if len(lead) >= MIN_VOICE_NOTES and len(rhythm) >= MIN_VOICE_NOTES:
        return [(lead, "Lead Guitar"), (rhythm, "Rhythm Guitar")]
    return [(events, "Guitar")]


def _download_audio(url: str, output_dir: str, max_duration: int) -> str:
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(output_dir, "audio_raw.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
    }
    # Try browser cookies (YouTube bot-check) — Safari first, then Chrome
    for browser in ("safari", "chrome", "chromium", "firefox", None):
        opts = dict(ydl_opts)
        if browser:
            opts["cookiesfrombrowser"] = (browser, None, None, None)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            break
        except Exception as exc:
            if browser is None:
                raise
            if "Sign in" not in str(exc) and "bot" not in str(exc):
                raise  # unrelated error, don't retry

    raw_path = next(
        (os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".wav")),
        os.path.join(output_dir, "audio_raw.wav"),
    )

    trimmed_path = os.path.join(output_dir, "audio.wav")
    subprocess.run(
        [
            "ffmpeg", "-i", raw_path,
            "-t", str(max_duration),
            "-ar", "44100", "-ac", "2",  # keep stereo + higher rate for demucs
            trimmed_path, "-y", "-loglevel", "quiet",
        ],
        check=True,
    )
    return trimmed_path


def _run_demucs(audio_path: str, stems_dir: str, on_status: Callable) -> Optional[str]:
    """Separate guitar stem with demucs htdemucs_6s model.

    Returns path to guitar.wav stem, or None if demucs is unavailable / fails.
    First call downloads ~2 GB model from the internet.
    """
    try:
        import demucs  # noqa: F401 — just check it's installed
    except ImportError:
        return None

    on_status("Separating guitar stem with AI source separation "
              "(first run downloads ~320 MB model)...")
    os.makedirs(stems_dir, exist_ok=True)

    try:
        subprocess.run(
            [
                sys.executable, "-m", "demucs",
                "--two-stems", "guitar",   # outputs guitar.wav + no_guitar.wav
                "-n", "htdemucs",          # htdemucs is compact (~320 MB vs 6-stem ~2 GB)
                "--out", stems_dir,
                audio_path,
            ],
            check=True,
            capture_output=True,
            timeout=900,  # 15-min ceiling
        )
    except Exception as exc:
        on_status(f"Source separation skipped ({type(exc).__name__}), "
                  "using full mix instead...")
        return None

    # Output layout: stems_dir/htdemucs/<audio_stem>/guitar.wav
    audio_name = os.path.splitext(os.path.basename(audio_path))[0]
    candidate = os.path.join(stems_dir, "htdemucs", audio_name, "guitar.wav")
    if os.path.exists(candidate):
        return candidate

    # Fallback: walk and find any guitar.wav
    for root, _, files in os.walk(stems_dir):
        for f in files:
            if f == "guitar.wav":
                return os.path.join(root, f)

    return None


def _to_mono_22k(src: str, dst: str) -> None:
    """Downsample to 22050 Hz mono for basic-pitch."""
    subprocess.run(
        ["ffmpeg", "-i", src, "-ar", "22050", "-ac", "1", dst, "-y", "-loglevel", "quiet"],
        check=True,
    )


def _serialize_events(note_events) -> List[List]:
    """Convert note event tuples to plain lists for JSON serialization."""
    result = []
    for event in note_events:
        start, end, pitch, amp, *_ = event
        result.append([float(start), float(end), int(pitch), float(amp)])
    return result


def transcribe_youtube(
    url: str,
    max_duration: int = 60,
    on_status: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    def status(msg: str) -> None:
        if on_status:
            on_status(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        status("Downloading audio from YouTube...")
        audio_path = _download_audio(url, tmpdir, max_duration)

        # Try demucs source separation first
        stems_dir = os.path.join(tmpdir, "stems")
        guitar_stem = _run_demucs(audio_path, stems_dir, status)

        if guitar_stem:
            # Downsample guitar stem for basic-pitch
            bp_input = os.path.join(tmpdir, "guitar_22k.wav")
            _to_mono_22k(guitar_stem, bp_input)
            status("Analyzing guitar stem with AI pitch detection...")
        else:
            # No demucs — downsample full mix
            bp_input = os.path.join(tmpdir, "audio_22k.wav")
            _to_mono_22k(audio_path, bp_input)
            status("Analyzing audio — this takes 30–60 s...")

        status("Loading AI pitch model...")
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH

        status("Detecting notes..." if guitar_stem else "Analyzing audio — this takes 30–60 s...")
        _model_out, _midi, note_events = predict(
            bp_input,
            ICASSP_2022_MODEL_PATH,
            minimum_frequency=80.0,
            maximum_frequency=1400.0,
            onset_threshold=0.5,
            frame_threshold=0.3,
            minimum_note_length=58,   # ~58 ms — filters out noise blips
        )

        status("Generating tracks...")

        guitar_events = [e for e in note_events if e[2] >= BASS_PITCH_THRESHOLD]
        bass_events   = [e for e in note_events if e[2] < BASS_PITCH_THRESHOLD]

        tracks = []

        for voice_events, voice_name in _split_guitar_voices(guitar_events):
            tracks.append({
                "name": voice_name,
                "tuning": "guitar",
                "note_events": _serialize_events(voice_events),
                "tab": notes_to_tab(voice_events, tuning="guitar"),
                "columns": notes_to_columns(voice_events, tuning="guitar"),
            })

        if len(bass_events) > MIN_BASS_NOTES:
            tracks.append({
                "name": "Bass",
                "tuning": "bass",
                "note_events": _serialize_events(bass_events),
                "tab": notes_to_tab(bass_events, tuning="bass"),
                "columns": notes_to_columns(bass_events, tuning="bass"),
            })

        duration = float(max(e[1] for e in note_events)) if note_events else 0.0

        return {
            "tracks": tracks,
            "duration": duration,
        }
