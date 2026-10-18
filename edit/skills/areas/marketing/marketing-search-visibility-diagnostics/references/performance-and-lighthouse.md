# Performance and Lighthouse

## Choose the Evidence

- Lighthouse CLI: reproducible lab diagnosis on local, staging, or production pages.
- Lighthouse CI: repeat runs, budgets, comparisons, and deployment gates.
- Unlighthouse: site-wide crawl plus parallel Lighthouse reporting.
- PageSpeed Insights API: hosted Lighthouse analysis; usable without a key at low volume.
- CrUX API/History API: real-user field distributions when the origin or URL has enough traffic.

PageSpeed Insights plans to stop returning CrUX field data in its response; use the CrUX APIs for durable field-data automation.

## Test Protocol

1. Record URL, revision, location, device profile, throttling, consent state, and whether the page is warm or cold.
2. Run at least five comparable Lighthouse samples for meaningful before/after work and use the representative median run.
3. Keep raw JSON and a normalized summary. Performance scores vary; budgets should focus on stable metrics and material regressions.
4. Separate field and lab data. Field data measures real users over time; lab data diagnoses the current build under controlled conditions.
5. Inspect the network waterfall and LCP element. A score alone is not an implementation instruction.

## SEO Boundary

Lighthouse's SEO category checks baseline discoverability and markup; it does not test Google index coverage, query relevance, backlinks, or rankings. A performance problem can affect experience and crawling efficiency, but a missing branded result still requires Search Console and document-level evidence.

Official references:

- https://github.com/GoogleChrome/lighthouse-ci
- https://github.com/GoogleChrome/lighthouse/blob/main/docs/variability.md
- https://developers.google.com/speed/docs/insights/v5/get-started
