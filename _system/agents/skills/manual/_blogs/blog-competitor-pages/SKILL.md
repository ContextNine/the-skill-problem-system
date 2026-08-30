---
name: blog-competitor-pages
description: Create or update typed competitor comparison page data from existing competitor research briefs. Use when asked to publish competitor comparison pages, add missing competitor page entries, or refresh page data for root comparison routes.
---

# Blogs · Competitor Pages

Use `$infra-code-folder-and-computer-topology` to resolve the registered Impression repository, then work from its root.

Use this skill to turn existing competitor briefs into typed public page data for root-level comparison pages.

This is not a markdown blog-writing skill. It updates page-data entries only. But the data must read like strong public copy once rendered: human, specific, useful, and interesting enough that a serious buyer keeps reading.

## Prime Directive

Take action on the user input. Use the competitor brief as the content brief. Write for the audience and their mental state: someone comparing tools because they may buy, switch, cancel, or explain the choice to a team.

Think like a creator and ghostwriter whose long-form articles always provide a complete idea, often with what, why, and how or example. Your specific focus here is not a final article, but the same standard applied to structured comparison page fields.

Inhabit the buyer's real questions:

- Am I comparing tools that solve the same job, or forcing a bad category match?
- Where does this competitor plainly beat Impression?
- Where does Impression plainly beat this competitor?
- What should I not assume from the marketing pages?
- Is Impression a serious alternative here, or only adjacent?

Come up with the angle that taps into that mindset. Use creative judgment where the brief gives room, but keep claims faithful to the source. The page should feel written by a sharp human who knows the category, not by a schema filler.

## Inputs

Accept one competitor name or slug, multiple competitors, or `all remaining`.

Read:

```text
.agents/blog/competitors/blogs/{slug}-vs-impression.md
.agents/blog/competitors/blogs/best-{slug}-alternatives.md
apps/next/src/app/(marketing)/(competitors)/competitor-pages-data.ts
```

Read component structure when needed:

```text
apps/next/src/app/(marketing)/(competitors)/components/competitor-comparison-pages.tsx
```

Do not browse unless the user explicitly asks for live refresh first.

## Output

Update typed entries only:

```text
apps/next/src/app/(marketing)/(competitors)/competitor-pages-data.ts
```

Each competitor needs:

```text
/{slug}-vs-impression
/best-{slug}-alternatives
```

Do not create blog posts, source maps, markdown sidecars, or redirects.

## Workflow

1. Resolve slug using repo naming.
2. If input is `all remaining`, compare paired brief files against registry entries and add missing paired competitors only.
3. Read the vs brief, alternatives brief, and existing registry entry.
4. Preserve existing optional media fields:
   - `competitorYoutubeVideoId`
   - `impressionYoutubeVideoId`
   - global `impressionYoutubeVideoId`
5. Convert brief substance into both page data entries.
6. Keep shutdown, category-mismatch, weak pricing confidence, coming-soon, and compliance caveats visible.
7. Run formatter if TypeScript formatting changes.
8. Run `pnpm --dir apps/next typecheck` after page-data edits.

## Required Page Shapes

Comparison page:

```text
CompetitorComparisonPage
slug: "{slug}-vs-impression"
path: "/{slug}-vs-impression"
```

Alternatives page:

```text
CompetitorAlternativesPage
slug: "best-{slug}-alternatives"
path: "/best-{slug}-alternatives"
alternatives: 3-5 items
```

Fill all required fields already defined in `competitor-pages-data.ts`. Preserve existing ordering and style where practical.

## Copy Standard

Follow the spirit of `ArticleBasePrompt`, adapted for structured page data.

Write crisp copy. Waste no words. Avoid purple prose. Use active voice most of the time. Give readers the "what's in it for me" quickly. No clickbait.

Specificity is the main quality bar. Turn vague claims into concrete ones:

- Say `LinkedIn inbox triage`, not `engagement workflow`.
- Say `historical creator analytics`, not `insights`.
- Say `brand-context drafting from docs and saved posts`, not `AI content`.
- Say `closed down`, `winding down`, or `pricing confidence is weak` when the brief says so.

Each field should contain a real thought, not a label in sentence form. Strong fields have tension:

- `Shield was stronger for historical personal LinkedIn analytics, but it has closed down. Impression belongs only as a current content-workflow alternative, not as a one-for-one analytics replacement.`
- `Kondo wins when the inbox is the product. Impression wins when content planning, publishing, and follow-up need to sit together.`

Weak fields sound replaceable:

- `Both tools help users improve LinkedIn.`
- `Impression is a powerful platform for creators.`

## Human Voice Rules

Use plain language actual buyers use. The tone should be direct, opinionated, fair, and useful.

Good page data should:

- Hook with a clear angle, even inside `thesis` or `searchIntent`.
- Build intrigue through honest contrast, not hype.
- Make the comparison feel situated in a real workflow.
- Use natural terms from the brief and product category.
- Let Impression win where it should, and lose where it should.
- Make verdicts feel earned.

Do not flatten everything into safe corporate phrasing. Prefer a sentence with a point of view over a sentence that could fit every competitor.

## Disallowed Style

Remove or rewrite generic, over-used, academic, or AI-sounding phrasing.

Avoid:

- `in a world of`
- `fast-paced landscape`
- `as you can see`
- `in conclusion`
- `in summary`
- `let's dive in`
- `delve`
- `game-changer`
- `unlock`
- `unleash`
- `elevate`
- `skyrocket`
- `thrive`
- `superpower`
- `secret weapon`
- `content is king`
- `one-stop shop`
- `ultimate guide`

Avoid unsupported comparison shortcuts:

- `best overall`
- `better than` without an axis
- `replaces` when tools are adjacent
- `all-in-one` unless source supports it

Do not use exclamation points. Do not start visible public fields with a question.

## Source Fidelity

Use only:

- requested briefs
- existing registry entries for same competitor
- explicitly requested refreshed research

Do not add pricing, product status, or feature claims from memory.

Separate official claims from third-party framing when briefs do. Mark weak pricing confidence. State shutdown or winding-down status on both page types when relevant.

## Comparison And Alternatives Logic

Comparison rows need mixed, honest results. Each row should compare one axis: core job, buyer, ideation, drafting, planning, publishing, analytics, inbox, team workflow, pricing, or risk.

Alternatives lists need 3-5 fair options. Include Impression only when the brief gives a credible angle. Do not rank Impression first unless the brief supports it.

Verdicts should name:

- who should choose competitor
- who should choose Impression
- caveat that prevents overclaiming

Claims to avoid should be public-readable safety rails, not private notes.

## Routing Rules

Use root paths only:

```text
/shield-vs-impression
/best-shield-alternatives
```

Do not add compatibility redirects. Old `/blog/{slug}` competitor URLs must not exist. `/blog` remains for real blog posts only.

Unknown competitor slugs must still 404.

## Final Check

Before finishing, confirm:

- Both page entries exist for requested competitors.
- Optional video IDs survived.
- No blog briefs changed unless requested.
- No redirects added.
- `pnpm --dir apps/next typecheck` ran after TypeScript page-data edits.

If only this skill markdown changed, app typecheck is not required.
