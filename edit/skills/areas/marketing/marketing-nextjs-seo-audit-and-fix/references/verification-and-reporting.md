# Verification and Reporting

## Acceptance Gates

- Preferred HTTPS URL returns `200`; HTTP and alternate host permanently redirect directly to it.
- Redirect rules preserve path/query values, edge-managed rules are reconciled with repository automation, and public `robots.txt` contains no unintended platform injection.
- Self-canonical, sitemap, internal links, Open Graph and structured data use same preferred origin.
- Important pages return useful server-rendered HTML, unique titles/descriptions and one meaningful H1.
- Robots permits intended pages; noindex routes stay out of sitemap.
- Sitemap parses, contains canonical `200` URLs, and uses accurate stable `lastmod` or none.
- JSON-LD parses and matches visible content; relevant Google/schema validators pass.
- No critical asset `404`, uncaught render error, or missing fallback.
- Mobile and desktop Lighthouse reruns preserve reports; LCP element and remaining bottleneck are named.
- Search Console inspection confirms deployed canonical/indexability when access and recrawl timing allow.
- Organic landing and conversion events are verified separately from ranking outcomes.

## Report Format

```text
Outcome
- Indexed/ranking state in one sentence.

Evidence
- Observed live
- Observed source
- Observed platform data

Findings
- P0 blocker — evidence — impact — fix — verification
- P1 material — evidence — impact — fix — verification
- P2 improvement — evidence — impact — fix — verification

Changes
- Exact files and behavior changed

Verification
- Commands/tests/reports and result

Remaining uncertainty
- Data delay, missing access, field-data wait or authority work
```

Do not promise position or timing. Technical acceptance can be immediate; recrawl, reindexing, authority and ranking lag behind deployment.
