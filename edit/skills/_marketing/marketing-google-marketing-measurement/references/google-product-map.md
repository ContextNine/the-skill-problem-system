# Google Product Map

The names overlap, but these are different control planes. Start from the artifact or question, not from the word “Google.”

| Surface | Owns | Identifier examples | Best control path |
| --- | --- | --- | --- |
| Google Tag Manager | Tags, triggers, variables, templates, workspaces, container versions and publishing | Account ID, numeric container resource ID, public `GTM-…` ID | GTM UI, container JSON export/import, Tag Manager API v2 |
| Google tag | Destination/configuration tag that routes measurement to GA4, Ads, and related products | `G-…`, `AW-…`, `GT-…` | Usually configured directly or as a native tag in GTM |
| Google Analytics 4 | Accounts, properties, data streams, events, key events, audiences and reports | Numeric account/property/stream IDs; web measurement ID `G-…` | Analytics UI, Admin API for configuration, Data API for reports |
| Google Search Console | Search ownership, indexing, sitemaps, queries, pages and inspection | Verified property URL/domain | Search Console UI and API |
| Google Cloud | API enablement, OAuth clients, service accounts, billing and IAM | Project ID/number, OAuth client ID | Cloud Console and `gcloud` |
| Google Workspace Admin | Organization users, groups, domains and Workspace services | Customer/domain/org identifiers | `admin.google.com`, Admin SDK |
| Google Workspace CLI (`gws`) | Dynamic CLI for Workspace APIs such as Drive, Gmail, Calendar, Sheets, Docs, Chat and Admin | Workspace API resources | `gws`; not the primary interface for GTM, GA4, Search Console, or Lighthouse |
| Lighthouse / PageSpeed Insights | Performance, accessibility, best-practice and SEO audits | URL and Lighthouse report | Lighthouse CLI/CI or PageSpeed Insights API |

## Which API Answers Which Question?

- “What is configured in this GTM container?” → Tag Manager API or JSON export.
- “Which GA4 property/data stream receives this tag?” → GA4 Admin API plus GTM tag inspection.
- “Did events arrive and how did they perform?” → GA4 reports/Data API and DebugView for testing.
- “Why is a page not indexed or ranking?” → Search Console plus crawl/render/content inspection; GA4 does not answer indexing.
- “Can `gws` do this?” → only if the relevant Discovery API is part of Google Workspace. Use the product-specific API otherwise.

## Primary References

- GTM export/import and Git versioning: https://support.google.com/tagmanager/answer/6106997?hl=en
- GTM publishing and versions: https://support.google.com/tagmanager/answer/6107163?hl=en
- Tag Manager API v2: https://developers.google.com/tag-platform/tag-manager/api/reference/rest
- Tag Manager OAuth scopes: https://developers.google.com/tag-platform/tag-manager/api/v2/authorization
- GA4 Admin API: https://developers.google.com/analytics/devguides/config/admin/v1
- Google Workspace CLI: https://github.com/googleworkspace/cli
