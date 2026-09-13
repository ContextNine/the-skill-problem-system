# Impression Current State

Implementation baseline date: 2026-07-29. Start at `impression/.docs/analytics-and-seo.md`, then resolve the live source commit and final GTM version from `impression/.docs/analytics/google/marketing-measurement.json`; do not copy IDs from this reusable reference.

## Runtime boundary

- Public/root hosts use GA4 through GTM.
- `app.` uses PostHog in production and does not load GTM.
- First-touch attribution crosses the public/app boundary in one parent-domain production cookie.
- PostHog page views are explicit; replay, heatmaps, identification, first-touch person properties, and client exceptions remain app-only.

## Consent

- `autoGrant=true` creates a fully granted versioned cookie only when no stored value exists.
- A valid legacy or explicit stored choice wins over auto-grant.
- The footer reopens preferences.
- The application pushes `consent_preferences_updated`; GTM's template owns default/update Consent APIs.

## Events

- `select_content`: internal sign-up CTA selection.
- `generate_lead`: successful newsletter/freebie outcome; the freebie slug or newsletter placement is `offer_id`.
- GA4 enhanced measurement owns the remaining common public interactions.
- Errors flow to PostHog and the rate-limited server logger, including route/global React errors.

## Pre-change evidence

Published GTM v11 had only a Google tag and one Consent Initialization tag, with no custom triggers or variables. GA4 therefore received page views/enhanced events but none of the repository's legacy custom pushes. Exact v11 export and screenshots live in private config; the Impression repo also retains the immutable v11 export for rollback.

## Source snapshot

`assets/impression-next-source-snapshot/` contains provenance-tagged examples of the consent provider, typed events, attribution helper, and repository docs. Treat the owning Impression repo as authoritative.
