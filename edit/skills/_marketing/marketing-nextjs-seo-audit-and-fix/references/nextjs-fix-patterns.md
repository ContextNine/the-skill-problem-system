# Next.js Fix Patterns

## Metadata

- Prefer static `metadata` when values are build-time facts. Use `generateMetadata` only when request, route or content data requires it.
- Set `metadataBase`, then verify emitted absolute canonical, Open Graph and Twitter URLs on every tenant/host.
- Next.js may stream resolved metadata into `<body>` for JavaScript-capable bots. Googlebot can interpret this, but HTML-only auditors may fail it. First make metadata static/cacheable where possible. Use `htmlLimitedBots` narrowly only after measuring TTFB cost; do not blindly set `/.*/`.
- Keep `siteName`/brand (`Context Nine`) separate from full default page title (`Context Nine — …`).

## Canonical Hosts and Protocols

- Middleware can normalize host, but Cloudflare/load balancer may terminate TLS and forward HTTP. Test public HTTP directly.
- Use permanent `301` or `308` redirects from HTTP and alternate host to preferred HTTPS origin.
- In Cloudflare Rules expressions, use the current supported Boolean `ssl`/`not ssl` test for the visitor connection; `http.request.scheme` is not a valid field in this ruleset language. Validate expressions in the live zone before relying on repository automation.
- Give managed rules stable references and deterministic descriptions. When a dashboard-created rule has no repository reference, reconcile it by description and preserve its live rule ID so the next automated apply updates instead of duplicates it.
- Align redirects, self-canonical, sitemap URLs, internal links and structured-data URLs.
- For multi-tenant apps, resolve tenant before metadata and reject unknown hosts rather than leaking another tenant's canonical.

## Robots and Sitemaps

- Generate robots per canonical tenant; non-indexable preview/admin hosts should return explicit noindex and should not appear in sitemap.
- If Cloudflare manages `robots.txt`, compare the public response with the application route. Disable the platform feature when it injects unwanted nonstandard policy text, then verify the public body again.
- Use actual content modification time. Do not default static/docs `lastModified` to `new Date()` per request or deploy unless content truly changed then.
- Omit `lastmod` when no trustworthy source exists. Do not emit `changefreq`/priority as a substitute for accurate discovery.
- Include only canonical `200` pages that should appear in search. Ensure important routes have crawlable internal links.

## Structured Data

- Put `WebSite` on homepage with stable `name`, `alternateName` and canonical `url`.
- Put `Organization` on homepage or about page with visible, truthful name, logo, founder/contact/location and `sameAs` values.
- Use Article/Breadcrumb/SoftwareApplication/Service only when page content supports them. Serialize JSON safely and validate rendered output.

## Semantic and Resilient Rendering

- Render primary heading, proposition and navigation in server HTML. One page-level H1 should communicate brand/topic without keyword stuffing.
- Decorative intros must not delay useful content or become LCP. Reveal effects after first paint; honor reduced motion; skip on return visits only as enhancement.
- WebGL/canvas/video must have HTML/image fallback. A renderer or asset failure must not replace the page with an error boundary.
- Use tenant-specific OG assets and descriptive image text where image conveys meaning.

## Performance

- Versioned `/_next/static/` and immutable tenant assets should receive long immutable caching. HTML remains revalidated appropriately.
- Preload only true critical fonts/media. Avoid autoplay video or large animation libraries before LCP.
- Delay GTM and other third parties when measurement requirements allow, but preserve consent/event order.
- Fix network `404`s before tuning scores; failed media can trigger fallbacks and distort LCP.

## Testing

- Add focused integration/E2E coverage for redirect, metadata, sitemap, robots and tenant isolation. Avoid wording-lock tests.
- Test live-like headers (`Host`, forwarded protocol) because local Next middleware alone cannot prove edge behavior.
