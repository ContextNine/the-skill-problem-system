---
name: video-elevenlabs-voiceover
description: Generates narrated voiceover assets with ElevenLabs, including script chunking, per-chunk audio files, timing metadata, and retry-safe manifests. Use when user mentions ElevenLabs, voice clone, TTS, narration, voiceover, or audio chunks.
---

# Video · ElevenLabs Voiceover

## Workflow

1. Start from approved/fact-checked script text.
2. Confirm speaker rights/consent and runtime credentials without reading secret files.
3. Chunk by sentence or beat, targeting under 60 seconds per chunk to reduce drift.
4. Keep chunk IDs stable: `voice_001.mp3`, `voice_002.mp3`.
5. Generate only missing or changed chunks.
6. Review audio joins before sending chunks to avatar/render pipeline.

## Manifest

Write `raw-media/voice/manifest.json` with:

- chunk ID and text
- estimated and actual duration when available
- generated file path
- provider model/settings used
- accepted/rejected status
- downstream avatar status

## Helper

Use:

```bash
# From vault root or a project with .agents/skills symlink available.
node .agents/skills/video-ai-production/scripts/chunk-script.js script.md --out raw-media/voice/chunks.json
```

Never regenerate accepted chunks unless script text or voice settings changed.
