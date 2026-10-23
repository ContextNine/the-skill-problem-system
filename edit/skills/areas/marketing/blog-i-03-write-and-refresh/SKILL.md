---
name: blog-i-03-write-and-refresh
description: Use when the user asks to write, draft, build, or refresh a blog article, SEO page, comparison, alternatives roundup, pricing guide, how-to, or glossary page. Produces researched drafts or focused edits in the site's Markdown, Vault, Notion, or typed page format.
---

# 3. Blog · Write and refresh

Write a useful article or make the smallest worthwhile improvement to an existing one. Preserve the author's voice and the owning site's source conventions.

Read `./references/site-integration.md` before choosing a source or integrating content. Resolve the repository with `$fleet-i-code-folder-and-computer-topology`; repository instructions and current implementation are authoritative over examples in this skill.

## Writing contract

- Establish the site/tenant, audience, locale, target query, format, and new/refresh intent. Read brand/product guidance, the relevant brief, existing page, and nearby articles.
- Compose `$blog-i-02-research-and-brief` when evidence is missing or stale. Verify changeable claims during the task; do not copy outdated pricing or availability from a previously accepted brief.
- Prefer one complete article per run. If asked for many, prioritize the queue and produce the requested scope without copying substantial prose, FAQs, summaries, or quotations across sibling pages.
- Give the reader a clear answer and point of view. Match the form to the audience and question. Comparisons need fair deciding axes; guides need concrete examples and limitations; refreshes need an identified defect or opportunity.
- Add original experience, verified examples, data, or useful judgment. Never invent experiments, customer stories, quotations, author experience, metrics, or product capabilities.
- Preserve handwritten prose outside the requested improvement. Favor a title/summary fix, supported factual correction, internal link, or small section edit over rewriting the whole post.
- Disclose an owner-product relationship when evaluating competitors. Include relevant owner drawbacks and competitor strengths. Separate shipped, marketed, and planned features.
- Apply `$unslop`. Use direct language, minimal copy, no em dashes, no decorative section labels, and no repetitive template padding. Keep the existing site's visual components and author conventions.
- Use `$blog-i-04-improve-faqs` when useful unanswered questions remain. Do not append an FAQ to every article or promise AI visibility from formatting.

## Draft and integration boundary

For a request to draft, save outside loaded public content in the owning site's research/draft area. Without an existing convention, use repository-relative `./.agents/blog/<site-or-tenant>/drafts/<slug>.md`. Vault-authored blogs use their real nonpublished status. Never assume a local Markdown `draft` flag works.

For an authorized source edit or integration request, update the authoritative source in its existing format. Source editing, committing, compiling, changing publication status, and deploying are distinct actions. Follow the user's established authorization and repository Git workflow; do not introduce repeated permission questions. A request for a draft does not authorize live publication or a published status change.

Preserve URL and original publication date on refreshes. Use the existing supported modified-date field. Keep metadata, visible content, canonical URL, author, images, internal links, and existing structured data consistent. Do not invent unsupported metadata fields or schema properties. Add no compatibility redirects or duplicate source.

## Verification and handoff

- Check every changed factual claim, quotation, link, image, and date. Remove placeholders, unsupported superlatives, repeated paragraphs, and captured cookie/bot-wall text.
- Verify the source maps to the intended host/tenant/route and survives hybrid-source collision rules. For Vault projection, compile/check through the owning projection skill and inspect the generated diff.
- For integrated changes, inspect the rendered article and changed metadata where an available preview permits it. Run repository-required checks appropriate to the files changed, including application typecheck after TypeScript edits. Do not add tests for wording or run app checks for skill-only changes.
- Report article/source location, target question, evidence gaps, precise edits, verification, and publication state. Record the actual public deployment date separately when known so subsequent audits have an honest baseline.

No new CMS is required. Notion access is conditional on the selected post source; web research and supplied evidence suffice for writing. Existing repository tools own integration and deployment.
