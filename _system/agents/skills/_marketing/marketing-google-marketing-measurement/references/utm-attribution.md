# UTM Attribution

Use stable lowercase values with underscores. Require `utm_source`, `utm_medium`, and `utm_campaign`; add `utm_content`, `utm_term`, or `utm_id` only when they distinguish a real report dimension.

```bash
node scripts/campaign-url.mjs build https://example.com/offer \
  --source linkedin \
  --medium organic_social \
  --campaign product_launch \
  --content hero_post

node scripts/campaign-url.mjs parse 'https://example.com/offer?utm_source=linkedin&utm_medium=organic_social&utm_campaign=product_launch'
```

## First-touch contract

- Capture the first landing URL, host/path, referrer, UTMs, click IDs, and timestamp once.
- Use one parent-domain cookie in production when attribution must cross from the public root to an app subdomain.
- Use host-only cookies when no registrable parent domain exists, including ordinary localhost testing.
- Preserve full attribution in the lead store/CRM/PostHog person properties. Do not copy every UTM or click ID into GA4 custom parameters; GA4 already owns session/campaign attribution and high-cardinality custom dimensions create noise.
- Short links must preserve the full query string. A self-hosted shortener is a separate operational system, not part of the baseline.

Test in a fresh context. Verify the landing URL, one stored first-touch value, form payload, downstream lead record, and final analytics event independently.
