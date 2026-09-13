# Audit Checklist

## Evidence First

Record target, date, location, device profile, deployment/version, source commit, and whether source checkout is dirty. Never merge live and local observations. A deployed site can lag a working tree.

## Search Console

- Performance: clicks, impressions, CTR, average position, queries, pages, countries, devices, and date comparison.
- Indexing: indexed/excluded counts, exact affected URLs, Google-selected versus user canonical, crawl time, robots state and fetch result.
- Sitemaps: submitted status, discovered URLs, errors, last read, and whether public sitemap matches submission.
- Enhancements and Core Web Vitals: distinguish field data from lab Lighthouse.
- Links: external domains, anchors and internally linked pages; state when report lacks enough data.
- Manual Actions and Security Issues: check before suggesting penalties.

Use Search Console API for repeatable read-only reporting when configured: Search Analytics, Sitemaps, Sites and URL Inspection. Never infer API access from Workspace CLI availability.

## Live HTTP and Crawl Surface

- Fetch HTTP, HTTPS, www and preferred host without automatic redirects. Require permanent consolidation to one HTTPS origin.
- When Cloudflare is in front, inventory live Redirect Rules and the zone's managed `robots.txt` preference; source middleware does not prove either edge behavior.
- Check status, redirect target, redirect chain, canonical, `X-Robots-Tag`, robots meta, language, title, description and one useful H1.
- Compare raw HTML for normal browser, Googlebot and HTML-limited/social user agents.
- Inspect `robots.txt` for sitemap declaration, accidental blocks, injected nonstandard directives such as `Content-Signal`, duplicate groups and platform mutations absent from repository source.
- Inspect sitemap for canonical indexable URLs, duplicates, redirecting URLs, false `lastmod`, missing important routes and orphaned pages.
- Crawl representative internal links and assets; separate application `404` from blocked third-party noise.

## Next.js Source

- Locate `metadata`, `generateMetadata`, `metadataBase`, route metadata helpers, `robots.ts`, `sitemap.ts` or route handler, middleware and edge redirects.
- Trace host/tenant selection before assuming generated canonical or metadata applies to target domain.
- Check dynamic routes return `notFound()` and noindex metadata when data is missing.
- Check preview, admin, test, auth, success and internal routes are deliberately indexable or noindex.
- Verify metadata resolves to correct absolute URLs and tenant-specific images.
- Search for JSON-LD, H1 ownership, client-only content, splash gates, WebGL/media error boundaries, cache headers and large third parties.

## Identity, Content and Authority

- Compare requested query with actual SERP intent and collisions; exact brand term can still be ambiguous.
- Keep site name separate from page title. Use brand consistently in title, H1, footer, about page, schema, social profiles and external references.
- Add useful pages only when each satisfies distinct intent: about, service, proof/case study, docs, contact and relevant resources.
- Find legitimate owned or partner pages already ranking for brand; use them as consistent entity links.
- Reject bulk directory links, paid backlink schemes, doorway pages and schema-only identity claims.

## Performance

- Run Lighthouse in mobile and desktop modes and preserve JSON reports when fixing.
- Identify actual LCP element, then break down TTFB, resource delay, load time and render delay.
- Check intro/loading animations, hydration gates, client redirects, WebGL startup, font blocking, image/video sizing, failed assets, cache TTL and unused JS.
- Use CrUX/Search Console field data when available. A Lighthouse score is one controlled run.

## Measurement Boundary

- Verify organic landings and conversions, but never present GTM/GA4 as a ranking mechanism.
- Compare application events with published GTM triggers/tags and GA4 key events.
- Keep UTMs on campaign destinations; exclude them from canonicals and sitemap URLs.
