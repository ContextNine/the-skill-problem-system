# AI Video Project Structure

Create each video job as a self-contained project. Keep source evidence, generated media, renders, and QA artifacts separate so later agents can resume without guesswork.

## Required Folders

- `reference/`: source docs, transcripts, URLs, factual notes, script source material.
- `scripts/`: project-specific automation and timing-map builders.
- `raw-media/`: generated and imported media before final assembly.
- `raw-media/voice/`: voice chunks, `chunks.json`, voice manifest.
- `raw-media/avatar/`: HeyGen/avatar clips and avatar manifest.
- `raw-media/graphics/`: HyperFrames overlays, captions, rendered graphics tracks.
- `raw-media/assembled/`: normalized clips, concat lists, intermediate assemblies.
- `style-library/`: reusable CSS, fonts, colors, logo assets, animation conventions.
- `style-templates/`: HyperFrames/HTML templates and layout variants.
- `renders/`: final and draft exports, render logs, final manifest.
- `qa/`: extracted frames, screenshots, reports, defect notes.

## Required Files

- `reference/source-manifest.md`: factual sources, claim ledger, and rights/consent notes.
- `reference/style-playbook.md`: presenter voice, brand standards, banned phrasing, examples.
- `scripts/timing-map.json`: spoken beats, visual beats, graphics timing.
- `raw-media/voice/manifest.json`: voice chunks and generation settings.
- `raw-media/avatar/manifest.json`: avatar render jobs and downloaded clips.
- `renders/render-log.md`: exact commands, retries, and final export path.
- `qa/report.md`: publication readiness verdict and unresolved risks.

## Source Note

This structure comes from `_system/tools/ai-video-creation/video-creation-process-initial-research-doc.md`, adapted into stable agent workflow terms. Do not treat example product/model claims in that note as evergreen truth.
