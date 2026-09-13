---
name: marketing-search-visibility-diagnostics
description: Diagnose why a website or brand is absent from Google, distinguish crawling, indexing, canonicalization, rendering, content, authority, and measurement problems, and verify fixes with public HTTP evidence, Google Search Console, Lighthouse, and optional SEO providers. Use explicitly for search visibility, indexing, technical SEO, Search Console, Lighthouse, Core Web Vitals, branded-query ranking, Semrush, OpenSEO, or SEO tooling research.
---

# Marketing · Search Visibility Diagnostics

## Operating Order

1. Establish the exact branded and non-branded queries, canonical origin, intended indexable URLs, countries, and languages.
2. Run the bundled public audit before authenticating to anything:

```bash
SKILL_DIR="$(vault root)/_system/agents/edit/skills/_marketing/marketing-search-visibility-diagnostics"
node "$SKILL_DIR/scripts/public-search-audit.mjs" https://example.com --pages /,/about,/contact
```

3. Inspect both source and rendered output. Test a browser, Googlebot, Bingbot, and Google Inspection user agent; compare cache headers and ensure title, description, robots, and canonical metadata remain inside `<head>` for every response shape.
4. Use Search Console next. Prefer a domain property, verify ownership, inspect the canonical homepage and sitemap URLs, then query branded terms, pages, devices, and countries. Start read-only and separate snapshot/report commands from sitemap submissions or other mutations.
5. Run repeatable performance tests. Use field data for user experience trends and multiple controlled Lighthouse runs for code regressions; never infer an indexing cause from one score.
6. Only after first-party evidence is collected, use optional keyword, SERP, competitor, or backlink providers.
7. Record evidence, code revision, deployment, cache purge, validation date, and the next Search Console checkpoint. Indexing and ranking changes are asynchronous.

## Routes

- End-to-end reasoning and severity: [[references/diagnostic-sequence|Diagnostic Sequence]].
- Search Console properties, API, inspection, and safe auth: [[references/google-search-console|Google Search Console]].
- Lighthouse, PageSpeed Insights, CrUX, and performance budgets: [[references/performance-and-lighthouse|Performance and Lighthouse]].
- Candidate skills, MCP servers, crawlers, providers, and adoption rules: [[references/tooling-and-providers|Tooling and Providers]].
- UTM construction and GA4/GTM measurement: use `$marketing-google-marketing-measurement`; SEO and analytics answer different questions.
- Tracked short links: build the destination URL with that measurement skill, then shorten it with the owning Shlink instance. Preserve the complete query string.

## Guardrails

- Never promise ranking or indexing. Prove eligibility, request or observe recrawling, and monitor outcomes.
- Do not use the Indexing API for ordinary web pages; it is limited to supported job-posting and livestream cases.
- Do not treat `site:` searches as a complete index count. Search Console URL Inspection is the authoritative page-level diagnostic available to the site owner.
- Keep API credentials local. Do not read plaintext credential files into the conversation or commit tokens, exports containing user data, or lead data.
- Do not enable APIs, submit sitemaps, request indexing, edit metadata, purge caches, or publish provider changes merely because diagnostics are requested.
- Separate reproducible facts from hypotheses. A missing result can be caused by discovery, indexing, canonical selection, content quality, query interpretation, or authority; measurement cannot make a page rank.
