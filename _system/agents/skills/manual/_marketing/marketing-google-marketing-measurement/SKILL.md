---
name: marketing-google-marketing-measurement
description: Document, audit, snapshot, diff, apply, publish, version, reuse, and troubleshoot GA4 and Google Tag Manager implementations, including Consent Mode, dataLayer events, UTM attribution, Tag Assistant verification, PostHog boundaries, and container portability. Use explicitly for the Google Marketing Measurement skill, Impression analytics, GTM/GA4 consent audits, tracked campaign links, or version-controlled measurement setups.
---

# Marketing · Google Marketing Measurement

## Start

1. Read `_system/agents/_package/instance/skills/config/marketing-google-marketing-measurement/README.md`; resolve the target repository through topology config.
2. Read the target repo's `.docs/analytics-and-seo.md`, then its instance manifest when present. For Impression, use `.docs/analytics/google/marketing-measurement.json`.
3. Classify every fact as `observed live`, `captured export`, `repository intended`, or `proposed`; never collapse those states.
4. Capture and hash the published GTM version plus a GA4 snapshot before mutation.

## Route References

- Product/account/API confusion: [[references/google-product-map|Google Product Map]].
- Consent implementation or debugging: [[references/consent-initialization|Consent Initialization]].
- Event names, parameters, and duplicate prevention: [[references/event-contract|Event Contract]].
- Export, import, publishing, or rollback: [[references/container-version-control|Container Version Control]].
- OAuth, Admin API, GTM API, and scripts: [[references/api-and-automation|API and Automation]].
- UTMs and first-touch cookies: [[references/utm-attribution|UTM Attribution]].
- GA4/PostHog separation and client errors: [[references/posthog-error-boundary|PostHog Error Boundary]].
- Porting the baseline to another app: [[references/reuse-and-migration|Reuse and Migration]].
- Impression-specific evidence: [[references/impression-current-state|Impression Current State]].

## Operate

```bash
SKILL_DIR="$(vault root)/_system/agents/skills/manual/_marketing/marketing-google-marketing-measurement"
node "$SKILL_DIR/scripts/google-marketing.mjs" validate --manifest .docs/analytics/google/marketing-measurement.json
node "$SKILL_DIR/scripts/google-marketing.mjs" snapshot --manifest .docs/analytics/google/marketing-measurement.json --out .docs/analytics/google/ga4-gtm-live.json
node "$SKILL_DIR/scripts/google-marketing.mjs" diff --manifest .docs/analytics/google/marketing-measurement.json --snapshot .docs/analytics/google/ga4-gtm-live.json
node "$SKILL_DIR/scripts/campaign-url.mjs" build https://example.com/offer --source linkedin --medium organic_social --campaign launch
```

`apply` and `publish` dry-run unless both `--execute` and the printed exact `--confirm` value are supplied. Prefer the signed-in UI when API coverage or OAuth is incomplete; still read back and snapshot the result.

## Acceptance

1. Validate source code and manifests.
2. Use GTM Preview/Tag Assistant to prove Consent Initialization precedes measurement.
3. Test first visit, stored grant, stored denial, granular update, withdrawal, and malformed legacy storage.
4. Verify each approved event once in `dataLayer`, the GA request, and DebugView/Realtime.
5. Verify public GA4 and app PostHog do not overlap.
6. Export the published GTM version unchanged; record IDs, time, source commit, counts, SHA-256, and verification evidence.

## Guardrails

- Never commit credentials, OAuth tokens, client-secret downloads, API secrets, raw leads, or PostHog keys.
- Use a dedicated GTM workspace. Inspect Detailed Changes; treat Overwrite and publish as destructive.
- Keep publish separate from apply and require explicit user authorization.
- Preserve existing IDs/history unless the user explicitly chooses migration.
- Do not invent consent policy, lead values, custom dimensions, or events without a reporting use.
- Keep exact instance mappings in matching private config, not in the reusable skill.
