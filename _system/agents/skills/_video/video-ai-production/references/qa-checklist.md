# AI Video QA Checklist

Run QA after every draft export. Do not say "ready to publish" unless checks pass or user explicitly waives defects.

## Factual QA

- Every factual claim maps to source material.
- Claim ledger covers script line/beat, claim, source, and confidence/status.
- No example-only claims from project notes are presented as current truth.
- Script avoids unsupported pricing, dates, model abilities, metrics, or availability claims.
- Source manifest includes title, URL or local path, access date when web source used, and covered claims.
- Rights/consent for voice, avatar, music, stock, screenshots, and logos is documented or explicitly waived.

## Visual QA

- Text stays inside frame and safe margins.
- Avatar crop is intentional and never hides face/mouth.
- Motion graphics support spoken idea, not random decoration.
- Captions and labels are readable on desktop and mobile.
- No out-of-bounds assets, overlapping UI, dead frames, flicker, or blank sections.
- Brand styling remains consistent across sections.

## Timing QA

- Beat transitions match speech.
- Graphics enter before or during relevant line, not after concept passes.
- Captions align with audio.
- No awkward pauses between chunks.

## Audio QA

- No clipped peaks, dropouts, doubling, or abrupt cuts.
- Chunk joins sound natural.
- Music/SFX, when present, do not mask speech.
- Final file has expected audio stream.

## Deliverable QA

- `renders/final.mp4` exists and opens.
- Duration matches brief.
- Aspect ratio matches target platform.
- Title/packaging promise matches actual video content.
- `renders/render-log.md` captures final commands.
- `qa/report.md` states pass/fail, fixes made, unresolved risks, and final recommendation.
