#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: check-video-props.sh <video.mp4>" >&2
  exit 2
fi

VIDEO="$1"
if [[ ! -f "$VIDEO" ]]; then
  echo "Video not found: $VIDEO" >&2
  exit 1
fi

ffprobe -hide_banner -v error \
  -show_entries format=duration,bit_rate,size \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels \
  -of json "$VIDEO"

