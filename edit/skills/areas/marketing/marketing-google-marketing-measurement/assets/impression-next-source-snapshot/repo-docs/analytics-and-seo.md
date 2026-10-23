# Analytics and SEO

This is the entrypoint for Impression's marketing measurement and public-search setup. Impression uses GA4 through GTM for the public site and PostHog for the production `app.` subdomain. Exact Google configuration, exports, and verification evidence live under `.docs/analytics/google/`.

## Sources of truth

- `.docs/analytics/google/README.md`: current GA4/GTM instance, exports, snapshots, hashes, event contract, and verification.
- `.docs/lead-magnets-freebies-and-utm-links.md`: lead-magnet attribution and campaign-link conventions.
- `.docs/cloudflare-cache.md`: canonical host redirects, application-owned robots output, cache verification, and deploy purging.
- `apps/next/src/config/page-titles-config.ts`: shared marketing metadata, canonicals, and sitemap inclusion policy.
- `apps/next/src/app/sitemap.ts` and `apps/next/src/app/robots.ts`: application-owned discovery surfaces.
- `.docs/public-marketing-style-guide.md`: public page structure and marketing presentation.

## Runtime boundary

- Root/non-subdomain public pages: GA4 via `NEXT_PUBLIC_GTM_ID`.
- `app.` subdomain: PostHog via `NEXT_PUBLIC_POSTHOG_KEY` and `NEXT_PUBLIC_POSTHOG_ORIGIN`.
- Do not load PostHog on public pages or GTM on the app subdomain.
- `apps/next/src/providers/public-providers.tsx` owns the lightweight public graph.
- `apps/next/src/providers/global-providers.tsx` enforces the host split for the full provider graph.

## Consent

`GoogleTagManagerConsentProvider` owns the public UI and persistence:

- Cookie: `gtm_cookie_consent`, version 2, 365 days.
- Top-level Google states: `ad_storage`, `analytics_storage`, `ad_user_data`, `ad_personalization`, `functionality_storage`, `personalization_storage`, and `security_storage`.
- Metadata: `version`, `source`, and `updated_at`.
- `autoGrant=true` grants all categories only when no stored value exists.
- A valid legacy or explicit stored choice always wins.
- The public footer's **Cookie settings** button reopens the current preferences.
- Application code writes the cookie and pushes `consent_preferences_updated`; it does not call `gtag('consent', ...)`.

GTM owns Consent Mode ordering:

- `Consent Mode - Initialize` fires on Consent Initialization and calls `setDefaultConsentState`, then restores the cookie.
- `Consent Mode - Update` fires on `consent_preferences_updated` and calls `updateConsentState`.
- GTM initially loads only when analytics is granted. Once loaded, it remains mounted for the page so withdrawal is processed; a later denied page load does not load GTM.

## GA4 event contract

Application code pushes only these custom public events:

```ts
type GoogleMarketingEvent =
  | { event: 'select_content'; content_type: 'cta'; content_id: string }
  | { event: 'generate_lead'; lead_source: 'newsletter' | 'freebie'; offer_id?: string };
```

- `select_content`: intentional internal sign-up CTA choice.
- `generate_lead`: successful newsletter or freebie action only.
- `generate_lead` is a GA4 key event.
- `offer_id` is the only custom dimension in the baseline.
- Page views, engagement, forms, outbound links, downloads, video, site search, and scroll remain GA4 automatic/enhanced measurement.
- Submit attempts, failures, custom scroll milestones, and duplicate page views are not custom GA4 events.

Relevant source:

- `apps/next/src/lib/monitoring/google-analytics.ts`
- `apps/next/src/components/marketing/freebies/freebie-signup-form.tsx`
- `apps/next/src/components/marketing/cta/newsletter/`
- `apps/next/src/components/marketing/cta/signup/`

## Attribution

`marketing_first_touch_v1` retains the first landing URL, referrer, UTMs, click IDs, and capture time for 90 days. Production writes one parent-domain cookie so the value can reach `app.impression.so`; ordinary localhost falls back to host-only behavior.

Lead signup payloads retain current and first-touch attribution. GA4 relies on its native campaign attribution instead of duplicating every UTM/click ID as custom event parameters. PostHog identification copies useful `first_touch_*` values to person properties.

## PostHog and client errors

The app subdomain keeps explicit `$pageview` capture, identify, heatmaps, replay, feature flags, and existing product events.

`ClientErrorHandler` captures browser errors and unhandled promise rejections. Route and global React error boundaries call the same reporter. Each exception is sent to PostHog `$exception` and the rate-limited `reportClientErrorAction`, which logs server-side.

Before reporting, the client strips URL query strings/fragments and redacts obvious sensitive query values, bearer tokens, and email addresses. Never attach cookies, form values, authorization headers, or request bodies.

## Google identifiers

The stable IDs, names, stream URL, retention, GTM versions, raw exports, hashes, and verification evidence live in `.docs/analytics/google/marketing-measurement.json`. Do not duplicate changing values here.

## SEO boundary

- `NEXT_PUBLIC_SITE_ORIGIN` is the metadata base for public absolute URLs.
- Shared public-page metadata and canonical paths come from `page-titles-config.ts`; dynamic blogs, changelog entries, competitors, freebies, and free tools add route-specific metadata.
- `sitemap.ts` emits the indexable marketing routes. Do not add app-subdomain or success-only routes.
- `robots.ts` publishes the canonical sitemap URL. The app subdomain remains `noindex, nofollow` through its layout and response boundary.
- Cloudflare owns the one-hop HTTP/`www` redirects, while the application owns canonical metadata, sitemap, and robots content.
- Search Console inspection, indexing requests, query performance, and Lighthouse findings are operational evidence rather than GTM configuration. Record any site-specific findings in `.docs` without modifying the immutable GTM exports.

Before changing SEO behavior, verify the public canonical URL, rendered metadata, sitemap membership, robots response, redirect chain, server-rendered primary content, and production response headers. Analytics tags must remain non-render-blocking and must not be changed merely to address indexing.

## Verification

1. Validate the manifest with the `marketing-google-marketing-measurement` skill.
2. Run focused Next tests and typecheck.
3. Use GTM Preview/Tag Assistant for first visit, stored grant, stored denial, granular update, and withdrawal.
4. Verify one `select_content` and one successful `generate_lead` in `dataLayer`, the GA request, and DebugView/Realtime.
5. Verify root has GTM without PostHog and app has PostHog without GTM.
6. Verify canonical metadata, sitemap, robots, and redirect behavior independently of measurement.
7. Export the published GTM version unchanged and record SHA-256 plus the deployed Git revision.
