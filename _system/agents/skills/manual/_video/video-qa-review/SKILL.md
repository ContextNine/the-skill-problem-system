---
name: video-qa-review
description: Verifies rendered videos for publication readiness using frame extraction, visual checks, timing review, audio sanity checks, source/fact audit, and defect reporting. Use when reviewing, validating, QAing, or approving generated videos.
---

# Video · QA Review

## Workflow

1. Extract frames at regular intervals and around beat transitions.
2. Check text bounds, avatar crop, lip sync, motion timing, caption sync, brand fit, readability, audio continuity, rights/consent, and factual claims.
3. Inspect final file properties and playback.
4. Create `qa/report.md` with pass/fail status, defects, fixes made, unresolved risks, and final publish recommendation.
5. Do not say "ready to publish" unless QA passes.

## Frame Extraction

```bash
bash .agents/skills/video-ai-production/scripts/extract-qa-frames.sh renders/final.mp4 qa/frames
```

## Checklist

Use `../video-ai-production/references/qa-checklist.md` as default rubric. Add project-specific checks from brief before approval.
