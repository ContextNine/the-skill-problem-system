# Impression Next.js Source Snapshot

This folder preserves the canonical baseline implementation prepared on 2026-07-29 and refreshed on 2026-07-30 from logical repository `impression`. Work began at clean commit `0091f832d`; the source snapshot was refreshed through hotfix commit `bd8666bfe`, and the owning repository's `.docs/analytics/google/marketing-measurement.json` records the released measurement revision.

The copied source paths were clean at that commit. Files retain their original imports and Impression-specific assumptions, so treat them as provenance and working examples rather than a ready-made package.

## Included

- `components/`: GTM consent form, banner/settings/config, footer reopening control, host-level provider wiring, freebie outcome tracking and React error boundaries.
- `lib/`: versioned consent contract, typed GTM event helpers, sanitized client-error reporting, marketing attribution and shared-cookie logic.
- `repo-docs/`: the repository's canonical analytics/SEO and UTM/freebie setup notes.

| Snapshot path | Original repository path |
| --- | --- |
| `components/google-tag-manager-consent-form.tsx` | `apps/next/src/components/forms_dialogs/cookies/google-tag-manager-consent-form.tsx` |
| `components/cookie-banner.tsx` | `apps/next/src/components/forms_dialogs/cookies/cookie-banner.tsx` |
| `components/cookie-settings-dialog.tsx` | `apps/next/src/components/forms_dialogs/cookies/cookie-settings-dialog.tsx` |
| `components/cookie-config.tsx` | `apps/next/src/components/forms_dialogs/cookies/cookie-config.tsx` |
| `components/global-providers.tsx` | `apps/next/src/providers/global-providers.tsx` |
| `components/public-providers.tsx` | `apps/next/src/providers/public-providers.tsx` |
| `components/footer.tsx` | `apps/next/src/components/marketing/marketing-layout/footer.tsx` |
| `components/marketing-analytics-bootstrap.tsx` | `apps/next/src/components/marketing/marketing-layout/marketing-analytics-bootstrap.tsx` |
| `components/freebie-attribution-bootstrap.tsx` | `apps/next/src/components/marketing/freebies/freebie-attribution-bootstrap.tsx` |
| `components/freebie-signup-form.tsx` | `apps/next/src/components/marketing/freebies/freebie-signup-form.tsx` |
| `components/route-error.tsx` | `apps/next/src/app/error.tsx` |
| `components/global-error.tsx` | `apps/next/src/app/global-error.tsx` |
| `lib/google-analytics.ts` | `apps/next/src/lib/monitoring/google-analytics.ts` |
| `lib/google-consent.ts` | `apps/next/src/lib/monitoring/google-consent.ts` |
| `lib/client-error-handler.tsx` | `apps/next/src/lib/monitoring/client-error-handler.tsx` |
| `lib/marketing-attribution.ts` | `apps/next/src/lib/monitoring/marketing-attribution.ts` |
| `lib/cookies.ts` | `apps/next/src/lib/browser-apis/cookies.ts` |
| `lib/shared-cookies.ts` | `apps/next/src/lib/browser-apis/shared-cookies.ts` |
| `repo-docs/analytics-and-seo.md` | `.docs/analytics-and-seo.md` |
| `repo-docs/lead-magnets-freebies-and-utm-links.md` | `.docs/lead-magnets-freebies-and-utm-links.md` |

Before reusing code, extract a smaller package/API, decide the consent policy, replace repository-specific imports, supply the destination GTM ID through the target repo’s env workflow and test the complete consent/event matrix.
