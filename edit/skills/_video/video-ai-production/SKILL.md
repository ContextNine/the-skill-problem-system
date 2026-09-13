---
name: video-ai-production
description: Orchestrates end-to-end AI video production from prompt/source material to publication-ready MP4 using research, script, voice, avatar, HyperFrames motion graphics, FFmpeg assembly, and visual QA. Use when creating YouTube videos, AI avatar videos, prompt-to-video assets, edited explainers, or fully verified publishable videos.
---

# Video · AI Production

## Workflow

1. Capture brief, audience, runtime, format, source materials, rights/consent, and publish risk.
2. Create project folders: `reference/`, `scripts/`, `raw-media/`, `style-library/`, `style-templates/`, `renders/`, `qa/`.
3. Research and fact-check every factual claim against source material before writing final script; maintain a claim ledger.
4. Write script in presenter voice using project style sources; split into timed beats.
5. Generate voiceover chunks under 60 seconds.
6. Render avatar clips from voice/script.
7. Build HyperFrames composition with avatar visible by default and motion graphics synced to speech.
8. Assemble final MP4 with FFmpeg.
9. Run visual/audio/factual QA. Do not mark ready until defects are fixed or explicitly waived.

## Acceptance Gate

Final deliverable must include:

- `renders/final.mp4`
- source manifest with factual references and claim ledger
- timing map
- voice/avatar/render manifests when generated
- QA frame contact sheet or report
- exact render commands or project command log

## Helper Scripts

Use bundled deterministic helpers when useful:

```bash
# From vault root or a project with .agents/skills symlink available.
node .agents/skills/video-ai-production/scripts/chunk-script.js script.md --out raw-media/voice/chunks.json
node .agents/skills/video-ai-production/scripts/build-manifest.js --project . --out renders/manifest.json
bash .agents/skills/video-ai-production/scripts/check-video-props.sh renders/final.mp4
bash .agents/skills/video-ai-production/scripts/extract-qa-frames.sh renders/final.mp4 qa/frames
```

## References

- Pipeline folders: see [references/project-structure.md](references/project-structure.md)
- Provider notes: see [references/provider-notes.md](references/provider-notes.md)
- QA rubric: see [references/qa-checklist.md](references/qa-checklist.md)
