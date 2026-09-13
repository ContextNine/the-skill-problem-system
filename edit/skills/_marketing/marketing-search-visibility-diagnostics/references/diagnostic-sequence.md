# Diagnostic Sequence

## Evidence Ladder

| Layer | Question | Strongest evidence | Typical failure |
|---|---|---|---|
| DNS/TLS/HTTP | Can crawlers reach one stable origin? | Redirect matrix and response headers | loops, mixed canonical hosts, 4xx/5xx |
| Crawl permission | Is discovery allowed? | robots.txt and crawl response | global disallow, blocked assets |
| Discovery | Does Google know the URLs? | sitemap readback and referring sitemap | stale or non-canonical sitemap URLs |
| Rendered document | Is the primary content and metadata valid? | raw HTML plus rendered DOM | client-only content, metadata outside `<head>` |
| Index eligibility | Is the URL indexable? | robots directives, status, canonical | noindex, soft 404, duplicate canonical |
| Google selection | What did Google choose? | URL Inspection coverage and selected canonical | crawled-not-indexed, duplicate, alternate canonical |
| Query relevance | Does the page clearly answer the query? | page copy, title/H1, entities, internal links | ambiguous brand, thin or mismatched content |
| Authority | Is the site trusted enough to surface? | first-party trends, genuine mentions and links | brand/entity collision, no external corroboration |
| Experience | Can users load and use it reliably? | CrUX plus repeated lab tests | poor LCP/INP/CLS, intrusive gates |

## Branded Query Recovery

For a new or weakly indexed brand, prioritize the homepage, a concise statement connecting the brand spelling to the product or organization, Organization/WebSite structured data, consistent social/profile citations, and descriptive internal links. Search both the compact and spaced forms of the brand, but do not stuff variants into hidden text or repetitive metadata.

When the public checks pass but the page remains absent, inspect in Search Console:

1. `page is not indexed` reason and last crawl.
2. User-declared versus Google-selected canonical.
3. Referring sitemap and crawl permission.
4. Rendered screenshot and page resources.
5. Query/page impressions over 16 months and the most recent complete period.

## Cache and Streaming Failure Pattern

A CDN can cache anonymous HTML independently of user agent while a framework streams metadata for ordinary browsers but not known bots. A browser-populated cache entry can then be replayed to a crawler with canonical or description tags after `</head>`. Compare a cache miss and hit for multiple user agents, inspect `Vary`, `Age`, and vendor cache headers, and prefer one standards-valid document shape when the cache key cannot vary safely.

## Closure

A fix is complete only when the committed revision is deployed, public HTML is rechecked after cache invalidation, Search Console sees the intended canonical/indexability state, and a dated follow-up is recorded. Ranking movement may lag the technical fix.
