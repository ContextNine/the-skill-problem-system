# AI Video Provider Notes

Use current official docs before provider work. APIs and plan gates change.

Do not read plaintext `.env`, key, token, kubeconfig, or secrets paths unless user explicitly asks. If provider credentials are missing from runtime, ask user to load them or use repo-approved env tooling.

## HyperFrames

- Primary reference: https://github.com/heygen-com/hyperframes
- Pipeline guide: https://hyperframes.heygen.com/guides/pipeline
- Prefer upstream HyperFrames skills when current CLI supports it:

```bash
npx skills add heygen-com/hyperframes
```

Use local `video-hyperframes-motion-graphics` skill for Matt-specific standards: avatar visibility, timing-map contract, QA expectations.

## ElevenLabs

- Text-to-speech docs: https://elevenlabs.io/docs/overview/capabilities/text-to-speech
- Generate cloned voices only with explicit rights/consent for the speaker.
- Generate stable chunk IDs and manifests before provider calls.
- Keep chunks under 60 seconds unless user explicitly accepts longer chunks.
- Record model, voice settings, output file, and accepted/rejected status.

## HeyGen

- Create video docs: https://developers.heygen.com/reference/create-video
- Render avatars only when user owns or has rights/consent to use the avatar.
- API first. Browser fallback only when Studio-only avatar settings or engine selection block required output.
- Record render job IDs, avatar/engine settings, input audio, output path, retry count, and fallback notes.

## GSAP

- Timeline docs: https://gsap.com/docs/v3/GSAP/Timeline/
- Use labels and data-driven timings from `scripts/timing-map.json`.

## FFmpeg

- Main docs: https://ffmpeg.org/ffmpeg.html
- Check input codecs/dimensions before concat.
- Keep final command in `renders/render-log.md`.

## Current-Truth Rule

Before scripting about real launches, products, prices, model names, API features, or account limits, verify against official/current sources. Source notes are starting context, not proof.
