#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "Usage: extract-qa-frames.sh <video.mp4> [output-dir] [fps]" >&2
  exit 2
fi

VIDEO="$1"
OUT_DIR="${2:-qa/frames}"
FPS="${3:-1/5}"

if [[ ! -f "$VIDEO" ]]; then
  echo "Video not found: $VIDEO" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
ffmpeg -hide_banner -loglevel error -y -i "$VIDEO" -vf "fps=$FPS" "$OUT_DIR/frame_%04d.png"
echo "Extracted QA frames to $OUT_DIR"
