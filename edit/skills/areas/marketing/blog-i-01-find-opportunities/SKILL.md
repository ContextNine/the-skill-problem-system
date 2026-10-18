---
name: blog-i-01-find-opportunities
description: Use when the user asks what blog articles to write or update, requests a blog audit, SEO or AEO opportunity analysis, or wants a weekly blog digest. Ranks new articles and focused refreshes using available search performance, customer questions, competitor visibility, and previous decisions.
---

# 1. Blog · Find opportunities

Produce an evidence-backed queue for one site or tenant. Recommend create, refresh, investigate, skip, or leave alone. This skill selects work; it does not write or publish articles.

## Scope and inputs

- Resolve the owning repository with `$fleet-i-code-folder-and-computer-topology`. Read root instructions, the nearest content README, brand/product guidance, content source configuration, and analytics docs.
- Establish the site, tenant, canonical host and path prefix, audience, commercial goal, locale, and analysis period. Keep tenants and unrelated products separate.
- Inventory all enabled sources, including Notion where the source mode uses it, and map each public URL to its authoritative source. Use `$blog-i-03-write-and-refresh` for the source-integration contract when needed.
- Use available Search Console and public analytics exports or configured tools. Record missing, stale, partial, or unverified sources before drawing conclusions. Do not assume an account or integration exists from a config placeholder.
- Existing transcripts/support notes may supply customer evidence. Count distinct customers and link specific excerpts; repeated mentions in one call are not multiple customers. Keep sensitive details out of public drafts and shared digests.

## Evidence and priority

- Scan content hygiene first: verified broken links, stale pricing/features, positioning drift, missing metadata, duplication, and unsupported claims. Distinguish a confirmed broken link from a timeout, blocked crawler, or temporary error. Propose fixes with evidence that replacements support the original claim.
- Use cheap available evidence across the inventory, then deeply investigate only the highest-value candidates, normally up to 15. Technical indexing/canonical/robots failures belong with `$marketing-search-visibility-diagnostics` or `$marketing-nextjs-seo-audit-and-fix`.
- Compare complete equivalent periods, initially the last 28 days against the preceding 28; account for seasonality, incomplete dates, and changed query mix. Show absolute clicks and impressions alongside percentage changes.
- Separate observed lost clicks from estimated CTR/rank upside. Compare CTR within suitable query, country, device, position, and search-layout cohorts. Show assumptions and bounds for `impressions × CTR gap`. Do not add overlapping estimates into an invented total.
- Business fit and distinct customer evidence may outrank raw volume. Low measured demand is different from unavailable demand. Flag potential query cannibalization and prefer improving a page that already owns the intent.
- For AI visibility, keep mentions, recommendations, and citations separate. Use consistent prompt sets, engines, locales, observation dates, and repeated executions. One response is exploratory evidence, not a trend or universal ranking.
- Profound or another available source may add estimated prompt demand and trends. Preserve the provider's definitions and coverage. Google keyword volume, AI prompt volume, and tracked visibility are different metrics.
- A normal initial customer window is 7 days and AI visibility window 4 weeks. Expand sparse windows transparently. Generate only as many themes and candidate queries as evidence supports; do not force quotas.

## Output and history

Return up to five strong recommendations, fewer when justified. Each needs:

- Suggested title/angle, target question cluster, audience, and create/refresh decision.
- Existing or proposed URL, authoritative source, and any overlap with current content.
- Why now, concrete evidence links/excerpts, measured values, estimates, uncertainty, and expected effort.
- Smallest useful change or the information a new article would add.
- Success measure, baseline period, and proposed evaluation date.

Include the strongest signal, biggest supported competitor gap, a short watch list, and source coverage. Do not manufacture a gap when visibility data is missing.

Reuse the owning site's research conventions. When absent, use repository-relative `./.agents/blog/<site-or-tenant>/` for private audit/digest and decision artifacts. Keep private evidence out of article bodies. Record accepted, edited, skipped, and discarded recommendations with reasons; reuse prior decisions instead of pitching them again without new evidence.

Track actual published changes and their baseline. Start a normal 28-day cooldown at observed publication, not drafting or commit. Urgent factual and functional fixes bypass the cooldown. Compare follow-up results honestly; a before/after change alone does not establish causality.

## Composition and services

For selected work, compose `$blog-i-02-research-and-brief`, then `$blog-i-03-write-and-refresh`; use `$blog-i-04-improve-faqs` when relevant. Do not stop for repeated skill-invocation permission inside an authorized workflow.

Search Console is needed for measured Google opportunities; GA4 supplies public outcomes where configured. Customer exports, Profound, DataForSEO, Semrush, and Ahrefs are optional evidence sources. Exports suffice. Never invent inaccessible metrics or subscribe to services. Weekly execution, Slack/email delivery, and live publishing require a separate request.
