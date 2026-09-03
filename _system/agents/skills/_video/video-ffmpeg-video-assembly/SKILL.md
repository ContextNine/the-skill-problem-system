---
name: video-ffmpeg-video-assembly
description: Assembles final video deliverables with FFmpeg by concatenating clips, overlaying graphics, mixing audio, normalizing formats, extracting frames, and exporting MP4 files. Use when stitching, combining, overlaying, transcoding, extracting frames, or producing final video renders.
---

# Video · FFmpeg Video Assembly

## Workflow

1. Inspect inputs with `ffprobe`.
2. Normalize dimensions, frame rate, codecs, and sample rates before concat when needed.
3. Use concat demuxer only when inputs match; otherwise transcode through filtergraph.
4. Overlay graphics/captions from HyperFrames outputs.
5. Export high-quality H.264 MP4 to `renders/final.mp4`.
6. Keep intermediate files in `raw-media/assembled/`.

## Required Log

Write exact commands used to `renders/render-log.md`, including:

- input paths
- normalization commands
- concat list path
- overlay/filtergraph command
- final export command
- warnings or compromises

## Helpers

```bash
bash .agents/skills/video-ai-production/scripts/check-video-props.sh renders/final.mp4
bash .agents/skills/video-ai-production/scripts/extract-qa-frames.sh renders/final.mp4 qa/frames
```
