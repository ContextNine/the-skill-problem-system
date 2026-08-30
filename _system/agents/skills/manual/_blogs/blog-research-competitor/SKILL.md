---
name: blog-research-competitor
description: Research one or more Impression competitors and create or refresh source-backed competitor dossiers under .agents/blog/competitors/research. Use when asked to research competitor blog targets, add competitor research, refresh pricing/positioning, or prepare research before comparison briefs.
---

# Blogs · Research Competitor

Use `$infra-code-folder-and-computer-topology` to resolve the registered Impression repository, then work from its root.

Use this skill to create or update competitor research dossiers only. Do not write final public blog posts. Do not create the deep `vs Impression` or `best alternatives` briefs; ask the user to explicitly invoke `$blog-research-create-briefs` for that manual workflow.

## Inputs

- Competitor name or names from the user.
- Any explicit blog intent or angle the user gives.
- Existing repo context:
  - `.agents/blog/competitors/research`
  - `.agents/blog/competitors/blogs`
  - `apps/next/src/config/footer-config.tsx`
  - `.docs/exported-feature-descriptions.md`

## Output

Create or refresh exactly one dossier per competitor:

```text
.agents/blog/competitors/research/{slug}.md
```

Slug rules:

- Reuse existing slug conventions and existing files when present.
- Prefer lowercase kebab-like slugs.
- Check for near-duplicates before creating a new file.
- If a competitor name is ambiguous, resolve the likely product before writing.

## Required Research Workflow

1. Read relevant existing repo files:
   - matching dossier if it exists
   - nearby research examples in `.agents/blog/competitors/research`
   - `apps/next/src/config/footer-config.tsx`
   - `.docs/exported-feature-descriptions.md`
2. Browse live web every run. Pricing, packaging, positioning, and feature claims are date-sensitive.
3. Use official sources first:
   - homepage
   - pricing page
   - docs/help center
   - official blog
   - official comparison or alternatives pages
4. Add third-party sources second:
   - comparison roundups
   - reviews
   - tool directories
   - community threads only when they add real signal
5. Separate official product claims from outside-market framing.
6. Mark weak or third-party pricing confidence clearly.
7. Preserve category boundaries. Do not force Impression into categories where it is only adjacent.

Aim for 8-15 useful sources for a well-covered competitor. Use fewer for obscure tools if fewer strong sources exist. Do not pad the source log with weak pages.

## Dossier Template

Use this structure:

```markdown
# {Competitor} Research Dossier

Updated: YYYY-MM-DD

## Snapshot
- Official site:
- Category:
- Best-fit ICP:
- Core promise:

## Pricing Snapshot
- ...

## Product Notes
- ...

## Comparison Notes From Other Blogs
- ...

## Impression Comparison Notes
- ...

## Gaps / Caveats
- ...

## Source Log
- `https://...` - source purpose.
```

## Quality Bar

- Every non-trivial claim must trace to a source in the dossier or repo docs.
- Pricing notes must say whether they came from official pages or lower-confidence third-party sources.
- Impression claims must stay grounded in repo docs.
- The dossier should be durable research for future writers, not polished article prose.
- Do not create sidecar source maps; useful facts and source log belong in the markdown file.
