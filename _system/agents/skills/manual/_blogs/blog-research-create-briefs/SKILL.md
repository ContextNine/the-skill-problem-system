---
name: blog-research-create-briefs
description: Create deep internal competitor blog research briefs for Impression comparison and alternatives posts from existing competitor dossiers. Use when asked to create vs Impression or best alternatives research briefs, not final public articles.
---

# Blogs · Research Create Briefs

Use `$infra-code-folder-and-computer-topology` to resolve the registered Impression repository, then work from its root.

Use this skill to create deep internal research briefs from existing competitor dossiers. These are writer handoff briefs, not final public blog posts.

Do not browse by default unless the dossier is stale, incomplete, or the user asks for a refresh. If live facts need updating, ask the user to explicitly invoke `$blog-research-competitor` first or refresh the dossier within the current request before writing briefs.

## Inputs

- Competitor name or names from the user.
- Required dossier:

```text
.agents/blog/competitors/research/{slug}.md
```

- Impression proof sources:
  - `.docs/exported-feature-descriptions.md`
  - `.docs/DMs-and-outreach.md`
  - `.docs/auto-dm-auto-reply-auto-plug.md`
  - extra `.docs/*` files only when relevant to the comparison
- Existing examples in:
  - `.agents/blog/competitors/blogs`

## Outputs

Create or refresh both files per competitor:

```text
.agents/blog/competitors/blogs/{slug}-vs-impression.md
.agents/blog/competitors/blogs/best-{slug}-alternatives.md
```

Slug rules:

- Reuse the dossier slug.
- Update existing brief files instead of creating duplicates.
- Keep file names consistent with existing examples.

## Required Workflow

1. Read the competitor dossier.
2. Read existing nearby briefs to match structure and depth.
3. Read Impression proof docs relevant to the competitor category.
4. Pull competitor facts from the dossier into each brief so the brief stands alone.
5. Pull Impression facts directly into each brief with available-now and coming-soon claims separated.
6. Frame the competitor honestly:
   - where competitor wins
   - where Impression wins
   - where categories only partially overlap
7. Rank Impression honestly in alternatives briefs. Do not force `#1`.

## `vs Impression` Brief Template

Use this structure:

```markdown
# {Competitor} vs Impression - Deep Research Brief

Updated: YYYY-MM-DD

## Search Intent And Honest Thesis
- Search intent:
- Honest thesis:

## Competitor Snapshot
- Category:
- Best-fit ICP:
- Pricing confidence:
- Strongest wins:
- Category boundaries:

## Impression Snapshot
- Relevant available-now capabilities:
- Relevant coming-soon capabilities to mention carefully:
- Best Impression angle for this comparison:

## Comparison Axes
- Core job:
- Ideation:
- Drafting:
- Planning and publishing:
- Analytics:
- Inbox and outreach:
- Collaboration:
- Pricing model:
- Best-fit team:

## Additional Information
### Tool Background And Pricing
- ...

### Product Notes That Matter For The Writer
- ...

### Market Framing And Article Caveats
- ...

## Claims To Avoid
- ...
```

Adjust axes when a category makes a row irrelevant, but keep enough comparable structure for writers.

## `Best Alternatives` Brief Template

Use this structure:

```markdown
# Best {Competitor} Alternatives - Deep Research Brief

Updated: YYYY-MM-DD

## Search Intent And Realistic Impression Rank
- Search intent:
- Realistic Impression rank:

## Fair Candidate Set And Why It Is Fair
- Fair candidate set:
- Why this set is fair:

## Why Users Leave {Competitor}
- ...

## Why Impression Belongs Or Does Not Belong In The List
- Why Impression belongs:
- When Impression should not be overstated:

## Exact Impression Angle To Use
- ...

## Additional Information
### Competitor Context For The Writer
- ...

### Pricing And Packaging Context
- ...

### Product And Market Notes
- ...

### Caveats To Keep In The Article
- ...

## Claims To Avoid
- ...
```

## Impression Claim Rules

- Treat available-now claims in `.docs/exported-feature-descriptions.md` as live.
- Use `.docs/DMs-and-outreach.md` for manual inbox, synced conversations, AI reply suggestions, labels/lists, and workflow state.
- Use `.docs/auto-dm-auto-reply-auto-plug.md` for Auto DM, Auto Reply, Auto Plug, LinkedIn automation prerequisites, and execution nuance.
- Clearly label coming-soon features when mentioned.
- Do not claim full replacement where the dossier shows only adjacent fit.

## Quality Bar

- Briefs must contain comparable competitor and Impression info directly in the markdown file.
- No source map sidecar.
- No polished public article prose.
- Claims to avoid must be explicit enough to prevent writer overreach.
- The `vs` thesis and alternatives ranking must not contradict each other.
