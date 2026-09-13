---
name: marketing-web-quality-assessment
description: Performs evidence-based web quality assessments across Lighthouse performance, Core Web Vitals, accessibility, security and browser best practices, technical SEO, and page experience. Use when explicitly asked to audit a website, diagnose poor Lighthouse or PageSpeed scores, investigate slow pages or search-readiness, review WCAG issues, establish quality baselines, or add Lighthouse regression testing.
---

# Marketing · Web Quality Assessment

## Operating Contract

Assess the rendered experience and relevant source code. Measure before recommending changes. Distinguish Lighthouse lab data from CrUX real-user field data, and never present an automated accessibility or SEO score as a complete audit.

For a full assessment, read [audit framework](references/audit-framework.md), [measurement and automation](references/measurement-and-automation.md), and every applicable specialist module below. For a narrow request, load only the relevant modules.

## Specialist Routing

- Performance, networks, assets, JavaScript, fonts, and caching: [performance](references/performance.md).
- LCP, INP, CLS, field thresholds, and metric-specific fixes: [Core Web Vitals](references/core-web-vitals.md) and the deeper [LCP reference](references/lcp-reference.md).
- WCAG, semantics, keyboard use, focus, screen readers, and forms: [accessibility](references/accessibility.md), [patterns](references/accessibility-patterns.md), and [WCAG reference](references/wcag-reference.md).
- HTTPS, security headers, compatibility, deprecated APIs, console failures, and code quality: [best practices](references/best-practices.md).
- Crawlability, metadata, canonicalization, structured data, mobile, and international SEO: [SEO](references/seo.md).
- Severity, reporting, and whole-site synthesis: [audit framework](references/audit-framework.md).

Treat these as internal specialist workstreams, not separately installed skills. When the user explicitly authorizes parallel agent work and the runtime supports it, delegate independent modules and keep final prioritization in the root assessment; otherwise process them sequentially.

## Execution

1. Establish the goal, representative URLs, device mix, authentication state, deployment environment, and whether the task is diagnosis or implementation.
2. Inspect repository instructions and start the production-like site when auditing local code. Prefer a deployed staging URL when backend, CDN, or third-party behavior matters.
3. Create a temporary report directory unless the user requests retained artifacts.
4. Run both mobile and desktop measurements when relevant:

```bash
scripts/run-lighthouse.sh URL OUTPUT_DIR both
scripts/run-pagespeed-insights.sh URL OUTPUT_DIR both
scripts/summarize-web-quality.py OUTPUT_DIR/*.json > OUTPUT_DIR/summary.md
```

5. Repeat Lighthouse at least three times for performance comparisons and use the median. Record redirect targets, test environment, timestamp, tool version, warnings, and observed variance.
6. Inspect failing audit evidence, the rendered page, network waterfall, console, DOM, source, headers, robots directives, sitemap, and structured data as applicable.
7. Perform manual checks that automation cannot prove: keyboard-only navigation, focus order, screen-reader semantics, content intent, search intent, factual accuracy, and important user journeys.
8. Report findings by severity with URL, evidence, user/search impact, likely cause, concrete fix, and verification step. Separate quick wins from architectural work and uncertainties.

## Guardrails

- Do not chase a score at the expense of usability, conversion, security, analytics, or visual quality.
- Do not equate Lighthouse Total Blocking Time with field INP; use field data for INP when available.
- Do not treat a single lab run as a stable baseline.
- Do not claim legal accessibility compliance from automated checks alone.
- Do not mutate production, submit indexing requests, or change analytics without explicit authorization.
- Keep inherited attribution under [provenance and license](references/provenance-and-license.md).
