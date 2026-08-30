---
name: video-heygen-avatar-render
description: Renders HeyGen avatar or digital twin clips from script or audio assets, tracks video jobs, downloads completed MP4 clips, and handles API/browser fallback paths. Use when user mentions HeyGen, avatar video, digital twin, Avatar V, talking head, or AI presenter clips.
---

# Video · HeyGen Avatar Render

## Workflow

1. Confirm approved script/audio chunks, target aspect ratio, and avatar rights/consent.
2. Confirm credentials are loaded without reading secret files.
3. Use HeyGen API first with `avatar_id`, dimensions, and script/audio input.
4. If eligible Avatar V is required, set supported engine option per current HeyGen docs.
5. Poll render jobs until complete.
6. Download clips to `raw-media/avatar/`.
7. Check duration, lip sync, crop, and audio continuity before assembly.

## Manifest

Record in `raw-media/avatar/manifest.json`:

- source audio/script chunk
- HeyGen `video_id` or job ID
- avatar and engine settings
- dimensions/aspect ratio
- output path
- retry count and errors
- lip-sync/crop review status
- browser fallback notes, if used

Use Playwright/browser fallback only when API cannot access required Studio/avatar settings. Save steps and screenshots in `qa/heygen-fallback/`.
