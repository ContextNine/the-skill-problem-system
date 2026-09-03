# HyperFrames Motion Standards

## Composition Principles

- Avatar stays visible by default; full-screen hides require explicit intent and short duration.
- Motion graphics explain active spoken concept.
- Do not add decorative movement that competes with presenter.
- Prefer clear cards, labels, callouts, diagrams, captions, and product/source visuals.
- Build from `scripts/timing-map.json`, not hand-guessed timings.
- Use project `reference/style-playbook.md` for brand and presenter taste.

## Layout Patterns

- Avatar left or right with graphic canvas opposite.
- Rounded avatar crop with subtle shadow when full background motion is needed.
- Slide-in callout cards for definitions, numbers, and short quotes.
- Timeline labels and GSAP markers for every spoken beat.
- Captions in safe lower third when they do not collide with avatar or graphics.

## QA Targets

- Text inside safe margins at 1920x1080 and target social crop.
- No overlapping caption/avatar/card regions.
- No blank background after transition.
- Motion begins close to relevant phrase and completes before next idea.
- All fonts/assets local or bundled.
- Visuals do not imply unsupported facts beyond source manifest.

## Upstream Reference

Prefer official HyperFrames docs and skills where available:

```bash
npx skills add heygen-com/hyperframes
```
