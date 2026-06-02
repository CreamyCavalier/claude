#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "==> Installing Python dependencies (first run takes a few minutes)..."
pip install -r "$BACKEND_DIR/requirements.txt" --quiet

echo ""
echo "==> Checking for ffmpeg..."
if ! command -v ffmpeg &>/dev/null; then
  echo "ERROR: ffmpeg not found. Install it first:"
  echo "  macOS:         brew install ffmpeg"
  echo "  Ubuntu/Debian: sudo apt-get install ffmpeg"
  echo "  Windows:       https://ffmpeg.org/download.html"
  exit 1
fi
echo "    ffmpeg OK"

echo ""
echo "==> Starting server..."
echo "    Open http://localhost:8000 in your browser"
echo ""
cd "$BACKEND_DIR"
uvicorn main:app --host 0.0.0.0 --port 8000
