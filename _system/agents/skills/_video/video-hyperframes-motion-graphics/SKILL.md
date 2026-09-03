---
name: video-hyperframes-motion-graphics
description: Builds programmatic video compositions with HyperFrames, HTML, CSS, GSAP timelines, captions, overlays, and synchronized motion graphics. Use when creating video motion graphics, HyperFrames compositions, animated explainers, captions, overlays, or HTML-to-video renders.
---

# Video · HyperFrames Motion Graphics

## Workflow

1. Prefer official HyperFrames workflow and skills when available.
2. Create composition from `scripts/timing-map.json`.
3. Use HTML/CSS/GSAP timelines for synced visuals, captions, and overlays.
4. Keep avatar visible by default; only hide it for explicit, intentional full-screen sections.
5. Run lint/preview/render loop before final assembly.
6. Capture preview screenshots for QA.

## Required Artifacts

- `index.html` or composition entrypoint
- `scripts/timing-map.json`
- `reference/style-playbook.md` or equivalent brand/voice source when available
- local assets and style files
- preview screenshots
- rendered overlay/video in `renders/` or `raw-media/graphics/`

## References

- Matt-specific standards: see [references/motion-standards.md](references/motion-standards.md)
- Provider notes: see `../video-ai-production/references/provider-notes.md`
