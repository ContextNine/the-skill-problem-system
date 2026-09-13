# Measurement and Automation

## Contents

- Measurement model
- Local Lighthouse
- PageSpeed Insights API
- CrUX field data
- Lighthouse CI
- Reproducibility and interpretation

## Measurement Model

Use complementary evidence:

| Surface | Best for | Important limitation |
|---|---|---|
| Lighthouse CLI | Local, staging, authenticated, and repeatable lab diagnosis | Synthetic run; performance varies by hardware and throttling |
| PageSpeed Insights API | Google-hosted Lighthouse against a public URL | Cannot reach local/authenticated pages; API quotas apply |
| CrUX API/Search Console | Real-user LCP, INP, and CLS at URL or origin level | Only eligible URLs/origins with sufficient Chrome traffic |
| Browser DevTools | Waterfalls, traces, DOM, coverage, console, and manual investigation | Analyst-driven and harder to automate |
| Lighthouse CI | Regression checks across commits | Requires stable test setup and calibrated assertions |

Google documents that Lighthouse can run in DevTools, from its Node CLI, or as a Node module. CLI runs require Chrome. PageSpeed Insights v5 returns Lighthouse lab results and may include CrUX field data, but Google plans to discontinue CrUX data in PSI; use the dedicated CrUX API for durable field monitoring.

Official references: [Lighthouse overview](https://developer.chrome.com/docs/lighthouse/overview), [PageSpeed Insights API v5](https://developers.google.com/speed/docs/insights/v5/get-started), [runPagespeed method](https://developers.google.com/speed/docs/insights/rest/v5/pagespeedapi/runpagespeed), [CrUX API](https://developer.chrome.com/docs/crux/guides/crux-api), and [Lighthouse CI](https://googlechrome.github.io/lighthouse-ci/).

## Local Lighthouse

Prerequisites: current Node.js, npm/npx, and Google Chrome or Chromium. Run the bundled wrapper from the skill directory:

```bash
scripts/run-lighthouse.sh https://example.com .agents/temp/web-quality both
```

The wrapper runs the Performance, Accessibility, Best Practices, and SEO categories and retains HTML plus JSON. It prefers an installed `lighthouse` binary and otherwise uses `npx --yes lighthouse`. Use local Lighthouse for localhost, staging, or authenticated pages. For authentication, start Chrome with a dedicated debug profile or supply a reviewed Lighthouse configuration; never reuse or expose a personal browser profile without explicit permission.

Run three to five trials per device profile. Compare medians, not the best run. Keep Chrome/Lighthouse versions and hardware stable when evaluating regressions.

## PageSpeed Insights API

Run against a publicly reachable URL:

```bash
scripts/run-pagespeed-insights.sh https://example.com .agents/temp/web-quality both
```

The API supports `mobile` and `desktop`, and categories `PERFORMANCE`, `ACCESSIBILITY`, `BEST_PRACTICES`, and `SEO`. It can be called without a key for light use. For repeated automation, provide `PAGESPEED_API_KEY` through the owning environment workflow; do not place it in source or command history.

The response JSON contains `lighthouseResult` and may contain `loadingExperience` and `originLoadingExperience`. Absence of field data is not a failure; it commonly means insufficient eligible traffic.

## CrUX Field Data

Use CrUX rather than Lighthouse to determine whether real users pass Core Web Vitals at the 75th percentile. The dedicated API requires a Google Cloud API key with the Chrome UX Report API enabled. Query page-level data first and fall back to origin-level data if the page is not represented.

Do not infer field INP from Lighthouse Total Blocking Time. TBT is a useful lab diagnostic proxy, not the same metric.

## Lighthouse CI

Start by collecting several runs without hard gates. Once the baseline is stable, configure assertions that prevent regressions rather than demanding arbitrary perfect scores.

Minimal `lighthouserc.json`:

```json
{
  "ci": {
    "collect": {
      "url": ["http://localhost:3000/"],
      "numberOfRuns": 3,
      "startServerCommand": "npm run start",
      "startServerReadyPattern": "ready|started|listening"
    },
    "assert": {
      "assertions": {
        "categories:accessibility": ["error", {"minScore": 0.9}],
        "categories:seo": ["error", {"minScore": 0.9}],
        "largest-contentful-paint": ["warn", {"maxNumericValue": 2500}],
        "cumulative-layout-shift": ["warn", {"maxNumericValue": 0.1}]
      }
    },
    "upload": {"target": "filesystem", "outputDir": ".lighthouseci/reports"}
  }
}
```

Run with `npx --yes @lhci/cli autorun`. Do not use temporary public upload storage for private or authenticated reports. Pin the CLI version in a project before making it a required CI gate.

## Reproducibility and Interpretation

- Test representative templates, not only the home page.
- Record final redirected URL, locale, consent state, cache state, viewport, device strategy, and third-party blockers.
- Separate category scores from individual evidence. Scores can change when Lighthouse weighting changes.
- Validate accessibility failures manually and test keyboard flows, zoom/reflow, focus, labels, announcements, and error recovery.
- Pair SEO automation with indexability inspection, rendered content, canonical/robots headers, structured-data validation, sitemap coverage, and Search Console evidence.
- Re-run the same procedure after fixes and report before/after medians with raw artifacts.
