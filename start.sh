#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
VENV_DIR="$SCRIPT_DIR/.venv"

# ── Find a compatible Python (3.10 or 3.11) ──────────────────────────────────
PYTHON=""
for cmd in python3.11 python3.10; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo ""
  echo "ERROR: Python 3.11 or 3.10 is required."
  echo "       Python 3.12+ breaks basic-pitch's dependencies."
  echo ""
  echo "Install Python 3.11 with Homebrew:"
  echo "  brew install python@3.11"
  echo ""
  exit 1
fi

echo "==> Using $PYTHON ($(${PYTHON} --version))"

# ── Create virtual environment once ──────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
  echo "==> Creating virtual environment..."
  "$PYTHON" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── Install dependencies ──────────────────────────────────────────────────────
echo "==> Installing dependencies (first run takes a few minutes)..."
pip install --upgrade pip setuptools wheel --quiet
pip install -r "$BACKEND_DIR/requirements.txt" --quiet

# ── Check ffmpeg ──────────────────────────────────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
  echo ""
  echo "ERROR: ffmpeg not found."
  echo "  macOS:  brew install ffmpeg"
  echo "  Linux:  sudo apt-get install ffmpeg"
  echo ""
  exit 1
fi

echo ""
echo "==> Server starting — open http://localhost:8000 in your browser"
echo "    (Press Ctrl+C to stop)"
echo ""
cd "$BACKEND_DIR"
uvicorn main:app --host 0.0.0.0 --port 8000
