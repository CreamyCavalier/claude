#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "==> Installing dependencies..."
pip install -r "$BACKEND_DIR/requirements.txt" --quiet

echo "==> Checking for ffmpeg..."
if ! command -v ffmpeg &>/dev/null; then
  echo "ERROR: ffmpeg is not installed. Please install it:"
  echo "  Ubuntu/Debian: sudo apt-get install ffmpeg"
  echo "  macOS:         brew install ffmpeg"
  exit 1
fi

echo "==> Starting server at http://localhost:8000"
cd "$BACKEND_DIR"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
