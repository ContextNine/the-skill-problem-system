# Google Search Console

## Product Boundaries

Search Console owns Google Search performance, verified properties, sitemaps, and URL Inspection. GA4 owns on-site behavior after a visit. GTM routes tags. Google Workspace Admin owns Workspace identities and services. The Google Workspace CLI dynamically exposes Workspace APIs, not the Search Console, Analytics Admin, or Tag Manager product APIs.

Official API surface: https://developers.google.com/webmaster-tools/v1/api_reference_index

## Property Choice

- Prefer `sc-domain:example.com` when the user controls DNS; it includes protocols and subdomains.
- Use a URL-prefix property when access must be limited to one prefix.
- Confirm the exact property before querying. Do not combine results from overlapping properties without labelling them.

## Read-Only Baseline

1. List accessible properties and permission levels.
2. List submitted sitemaps and their warnings/errors.
3. Inspect the homepage and every intended canonical URL.
4. Query 16 months, 90 days, and the latest comparable complete periods.
5. Group by query, page, device, country, date, and search appearance as needed.
6. Separate branded variants from non-branded demand.
7. Save normalized results without OAuth tokens or user-level private data.

Search Analytics is not exhaustive for every low-volume row, and recent data can be provisional. State date ranges and data state.

## Safe Tooling

`AminForou/mcp-gsc` is a practical local MCP option with Search Analytics, URL Inspection, and sitemap tools. Its destructive site/sitemap actions are disabled unless explicitly enabled. Pin a reviewed release and use the read-only OAuth scope where possible.

For a custom script, use the official Search Console API with `webmasters.readonly`. Keep OAuth login/setup separate from audit execution. A request to inspect a URL is diagnostic; a sitemap submission or property mutation requires explicit authorization.

URL Inspection reports the version in Google's index, not a guaranteed live crawl. The public URL test in the web UI is a separate live check.

## Indexing API Warning

Google's Indexing API is for supported `JobPosting` pages and livestream pages with `BroadcastEvent` in `VideoObject`. Do not use it as a general-purpose indexing submission tool.
