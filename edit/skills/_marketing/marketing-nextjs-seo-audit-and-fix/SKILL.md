---
name: marketing-nextjs-seo-audit-and-fix
description: Audits and fixes technical, on-page, entity, indexing, performance, and measurement-adjacent SEO in Next.js sites. Use explicitly when the user invokes the Next.js SEO Audit and Fix skill or asks it to diagnose ranking, crawling, canonical, metadata, schema, sitemap, Core Web Vitals, or Search Console problems and implement verified fixes.
---

# Marketing · Next.js SEO Audit and Fix

## Start

1. Read `_system/agents/edit/settings/skills/config/marketing-nextjs-seo-audit-and-fix/README.md`; use configured targets when present.
2. Read target repository `AGENTS.md`, nearest `README.md`, and tenant/app docs before source inspection or edits.
3. Keep four evidence classes separate: `observed live`, `observed source`, `observed platform data`, and `proposed`.
4. For edits, complete repository Git preflight and preserve unrelated work.

## Audit

1. Run `node scripts/audit-live-nextjs-seo.mjs https://example.com` and save its JSON findings in working notes.
2. Follow [[references/audit-checklist|Audit Checklist]] for Search Console, SERP, crawling, metadata, schema, content, authority, and performance evidence.
3. Follow [[references/nextjs-fix-patterns|Next.js Fix Patterns]] while tracing App Router metadata, route handlers, middleware, rendering gates, and multi-tenant behavior.
4. Compare findings with [[references/known-failure-patterns|Known Failure Patterns]]; verify each against current state before reporting it.
5. Run Lighthouse mobile and desktop. Treat lab data as diagnostic, not field Core Web Vitals or a ranking score.
6. Hand GTM, GA4, Consent Mode, and data-layer work to [[_system/agents/edit/skills/_marketing/marketing-google-marketing-measurement/SKILL|Google Marketing Measurement]]. Hand managed campaign URLs to [[_system/agents/edit/skills/_marketing/marketing-manage-utm-tracking-links/SKILL|Manage UTM Tracking Links]].

## Fix Order

1. Availability and consolidation: status codes, HTTPS, preferred host, redirects, canonical consistency.
2. Indexability: robots, `noindex`, sitemap inclusion, accurate `lastmod`, internal discovery.
3. Search identity: unique title/description, semantic H1, `WebSite` and `Organization` JSON-LD, tenant-specific social metadata.
4. Rendered usefulness: meaningful server HTML, no animation/loading gate before primary content, resilient media/WebGL fallback.
5. Performance: LCP element and subparts, render-blocking work, unused JavaScript, asset failures, caching, fonts and third parties.
6. Content and authority: intent-matched pages, about/services/proof, internal links, consistent brand naming, legitimate external citations.
7. Measurement: verify organic landing attribution and conversions without treating tracking as a ranking fix.

## Verification

- Re-run live audit, targeted tests, Lighthouse, and rendered-browser checks after fixes.
- Validate structured data and inspect representative URLs in Search Console when access exists.
- Confirm HTTP/HTTPS/www behavior with redirect-disabled requests.
- When an edge dashboard was used, reconcile live rules with repository automation by stable reference or deterministic description before the next automated apply.
- Confirm sitemap contains only canonical indexable URLs and stable truthful timestamps.
- Use [[references/verification-and-reporting|Verification and Reporting]] for acceptance gates and final report.

## Guardrails

- Do not claim a penalty from low traffic. Check Manual Actions and Security Issues.
- Do not use `site:` queries as rank measurement; Search Console is source of truth for impressions and positions.
- Do not add schema for facts or entities absent from visible content.
- Do not use campaign parameters or short links as canonicals or internal navigation targets.
- Do not publish, deploy, submit sitemaps, request indexing, or mutate Google properties unless user authorizes that action.
- Scope multi-tenant changes to target tenant unless shared behavior is explicitly requested and regression-tested.
- Cite current primary guidance from [[references/primary-sources|Primary Sources]] when recommendations depend on changing search or framework behavior.
