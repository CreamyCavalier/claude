#!/usr/bin/env python3
"""Tab a YouTube video or local audio file from the command line.

Usage:
    python3 tab.py <youtube-url-or-audio-file> [options]

Examples:
    python3 tab.py https://youtu.be/dQw4w9WgXcQ --instrument lead
    python3 tab.py /path/to/song.wav --instrument lead
    python3 tab.py /path/to/song.mp3 --instrument bass --duration 120
"""

import argparse
import os
import sys

# Activate the venv if running outside of it
_venv = os.path.join(os.path.dirname(__file__), ".venv")
_venv_python = os.path.join(_venv, "bin", "python3")
if os.path.exists(_venv_python) and sys.executable != _venv_python:
    os.execv(_venv_python, [_venv_python] + sys.argv)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate guitar/bass tabs from a YouTube video or audio file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
YouTube bot-check workaround:
  If YouTube rejects the download, pass the audio file directly instead:
    1. Download the audio any way you like (browser, online converter, etc.)
    2. python3 tab.py /path/to/audio.mp3 --instrument lead
""",
    )
    parser.add_argument("source", help="YouTube URL  OR  path to an audio/video file")
    parser.add_argument(
        "--instrument", "-i",
        default=None,
        help="Which track to show: 'guitar', 'lead', 'rhythm', 'bass'. Default: all.",
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=60,
        metavar="SECONDS",
        help="How many seconds to analyse (default: 60)",
    )
    parser.add_argument(
        "--out", "-o",
        default=None,
        metavar="DIR",
        help="Output directory (default: ./tabs/<name>)",
    )
    parser.add_argument(
        "--cookies", "-c",
        default=None,
        metavar="FILE",
        help="Netscape cookies.txt file to pass to yt-dlp (helps with bot-check)",
    )
    args = parser.parse_args()

    is_file = os.path.exists(args.source)

    # ── resolve output dir ──────────────────────────────────────────────────
    if args.out:
        out_dir = args.out
    elif is_file:
        name = os.path.splitext(os.path.basename(args.source))[0]
        out_dir = os.path.join("tabs", name)
    else:
        vid_id = _extract_video_id(args.source) or "output"
        out_dir = os.path.join("tabs", vid_id)
    os.makedirs(out_dir, exist_ok=True)

    def status(msg: str) -> None:
        print(f"  ▸ {msg}", flush=True)

    if is_file:
        print(f"\n🎸  Tabbing file: {args.source}")
        print(f"    Analysing first {args.duration}s → output in {out_dir}/\n")
        from transcribe import transcribe_file
        result = transcribe_file(args.source, args.duration, on_status=status)
    else:
        print(f"\n🎸  Tabbing: {args.source}")
        print(f"    Analysing first {args.duration}s → output in {out_dir}/\n")
        from transcribe import transcribe_youtube
        result = transcribe_youtube(
            args.source, args.duration,
            on_status=status,
            cookies_file=args.cookies,
        )

    tracks = result["tracks"]
    if not tracks:
        print("\n✗  No notes detected. Try a longer --duration or different source.")
        sys.exit(1)

    # ── filter by instrument if requested ───────────────────────────────────
    if args.instrument:
        want = args.instrument.lower()
        filtered = [t for t in tracks if want in t["name"].lower()]
        if not filtered:
            names = ", ".join(t["name"] for t in tracks)
            print(f"\n✗  No track matching '{args.instrument}'. Found: {names}")
            sys.exit(1)
        tracks = filtered

    # ── save & print each track ─────────────────────────────────────────────
    print()
    for track in tracks:
        name_slug = track["name"].lower().replace(" ", "_")

        txt_path = os.path.join(out_dir, f"{name_slug}.txt")
        with open(txt_path, "w") as f:
            f.write(track["tab"])
        print(f"  ✔  {track['name']} tab  →  {txt_path}")

        try:
            from gp_export import notes_to_gp5_bytes
            gp_bytes = notes_to_gp5_bytes(
                track["columns"],
                tuning=track["tuning"],
                tempo_bpm=120,
                track_name=track["name"],
            )
            gp_path = os.path.join(out_dir, f"{name_slug}.gp5")
            with open(gp_path, "wb") as f:
                f.write(gp_bytes)
            print(f"  ✔  {track['name']} GP5  →  {gp_path}")
        except Exception as e:
            print(f"  ✗  GP5 export failed: {e}")

        print(f"\n{'─'*60}  {track['name']}")
        print(track["tab"])
        print()

    print(f"\n✓  Done. Files saved to: {out_dir}/\n")


def _extract_video_id(url: str) -> str:
    try:
        from urllib.parse import urlparse, parse_qs
        u = urlparse(url)
        if u.hostname in ("youtu.be",):
            return u.path.lstrip("/")[:11]
        qs = parse_qs(u.query)
        if "v" in qs:
            return qs["v"][0]
    except Exception:
        pass
    import re
    m = re.search(r"[?&]v=([^&]{11})", url)
    return m.group(1) if m else None


if __name__ == "__main__":
    main()
