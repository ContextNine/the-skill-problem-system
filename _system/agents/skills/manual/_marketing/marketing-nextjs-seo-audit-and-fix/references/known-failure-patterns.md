# Known Failure Patterns

These patterns were found in real Next.js marketing applications. They are diagnostic leads, not permanent facts about any configured site. Re-observe before reporting or fixing.

| Pattern | Evidence to collect | Why it matters | Typical fix |
|---|---|---|---|
| HTTP homepage returns `200` while HTTPS is canonical | Redirect-disabled HTTP request; Search Console indexed URLs | Splits protocol signals and wastes crawl attention | Edge/server permanent redirect plus HSTS |
| `www` and apex behavior differs | Four-origin status matrix | Conflicting canonical/redirect signals | One preferred HTTPS host everywhere |
| Cloudflare redirect automation uses unsupported `http.request.scheme` | Dashboard/API validation error plus current Rules fields reference | Intended canonical rules never deploy although source looks complete | Use `ssl`/`not ssl`; deploy and rerun the public redirect matrix |
| Dashboard-created edge rules are invisible to reference-only automation | Live rule inventory versus CLI `audit`; compare descriptions and refs | Next apply can duplicate rules or verification can report false absence | Match stable ref first, deterministic description second, preserving live ID |
| Cloudflare injects `Content-Signal` into application `robots.txt` | Compare public response, application route and zone managed-robots setting | Public crawl policy differs from source and may include unwanted nonstandard directives | Disable managed robots for the zone and verify the public body |
| Sitemap exists but was never submitted | Public fetch plus GSC Sitemaps report | Discovery signal is present but unmanaged | Submit after validating contents |
| Static/docs sitemap entries use request-time `new Date()` | Compare source and repeated sitemap responses | Falsely claims every page changed | Real content timestamp or omit `lastmod` |
| Only homepage indexed although more routes exist | GSC page indexing and sitemap comparison | Routes may be new, thin, orphaned or undiscovered | Fix discovery/content, submit sitemap, inspect URLs |
| Brand absent from live H1 or primary copy | Rendered DOM and raw HTML | Weak entity/site-name consistency | Visible natural brand/topic heading and copy |
| Site name equals full SEO title | Metadata/config trace | Mixes entity name with page-title template | Separate brand, title template and page title |
| No `WebSite`/`Organization` JSON-LD | Raw/rendered HTML and validator | Missed explicit entity/site-name signal | Truthful homepage schema matching visible content |
| Generic cross-tenant OG image | Metadata per host | Weak/incorrect share identity | Tenant-specific image, alt and dimensions |
| Metadata streamed into body | UA-specific raw HTML | Some auditors/HTML-only consumers miss it | Prefer static metadata; narrowly configure limited bots if needed |
| Intro/splash becomes LCP | Lighthouse trace and LCP selector | Meaningful content is intentionally delayed | Paint content first; make intro progressive decoration |
| WebGL/media failure replaces meaningful page | Console, network and no-GPU run | Crawlers/users receive fallback error instead of content | Stable HTML/image fallback and isolated error handling |
| Versioned assets use short cache TTL | Response headers | Repeat-load cost and wasted bandwidth | Long `immutable` cache for fingerprinted assets |
| Large unused animation/third-party JS | Lighthouse coverage/treemap | Main-thread and transfer cost | Code split, defer, remove or load after interaction |
| App emits custom analytics events but GTM has no triggers/tags | Source event inventory versus published export | Conversion reports silently incomplete | Add reviewed mappings in GTM; verify with Tag Assistant |
| Consent defaults and app updates have unclear ownership | Source, published template and event timeline | Ordering/policy ambiguity and missing hits | One documented consent state machine; verify each path |
| `autoGrant` copied across sites | Provider/component trace | Policy-sensitive behavior becomes accidental default | Tenant/config policy with explicit approval |
| Brand query collides with established product/entity intent | Neutral SERP plus GSC queries | Raw short query is harder than exact long brand | First own exact long brand and qualified variants; build entity citations |
| No meaningful external brand references | Search/link reports | Google has little corroborating entity evidence | Consistent owned profiles, partner/client proof and legitimate citations |

Measurement-specific implementation details belong in the Google Marketing Measurement skill. Time-sensitive site findings belong in matching private config.
