# Tooling and Providers

## Recommended Stack

| Need | Default | Why |
|---|---|---|
| Agent audit instructions | `addyosmani/web-quality-skills` | focused, portable Lighthouse/SEO skills with little runtime coupling |
| Broad Codex SEO reference | `AgriciDaniel/codex-seo` | extensive Codex-native workflows and deterministic runners; review before selectively adopting |
| Search Console MCP | `AminForou/mcp-gsc` | mature first-party data and URL Inspection coverage; keep destructive mode off |
| GA4 reporting MCP | `googleanalytics/google-analytics-mcp` | Google-owned experimental server for Data/Admin read operations |
| GTM automation MCP | `sprawz/gtm-mcp-server` | strong read/write/publish surface and bundled GTM skills; self-host or review hosted trust carefully |
| Single/site-wide lab audit | Lighthouse CI / Unlighthouse | official CI foundation plus efficient multi-page coverage |
| Technical crawler | SiteOne Crawler or SEOnaut | self-hostable, structured site-wide audit output |
| Keyword/SERP/backlinks | OpenSEO | open source and self-hostable; requires paid DataForSEO usage |
| Semrush data | official Semrush MCP | supported OAuth endpoint; consumes eligible plan/API units |
| Tracked short links | Shlink | self-hosted redirects and visit statistics; UTMs remain the campaign source of truth |

## Adoption Rules

- Skills are instructions, not evidence. Prefer official APIs and deterministic CLIs underneath them.
- Pin releases or commit SHAs. Inspect install scripts, credential paths, network calls, mutations, and global writes before adoption.
- Do not install a large pack merely for one workflow. Copy or adapt the smallest useful references and scripts, preserving licenses and attribution.
- Remote MCP servers receive the data and permissions sent to them. Prefer local/self-hosted deployments for Search Console and GTM when practical.
- Keep read/report and apply/publish tools separate. Require explicit approval for sitemap submission, GTM publication, provider spend, or destructive operations.

## Provider Notes

OpenSEO itself can be free to self-host, but its useful SERP, keyword, audit, and backlink data comes from DataForSEO and is pay-as-you-go. Semrush's official MCP is not a free substitute for a Semrush/API entitlement. Start with free first-party Search Console data and public crawling; buy competitor data only after it will change a decision.

The official Semrush endpoint and current authentication rules are documented at https://developer.semrush.com/api/v3/introduction/semrush-mcp/.
