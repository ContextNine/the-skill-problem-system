# Event Contract

A `dataLayer` push is an interface, not proof that GA4 received an event. A matching GTM trigger and GA4 Event tag must exist and be verified.

## Canonical public-site events

| Event | When | Parameters | GA4 role |
| --- | --- | --- | --- |
| `select_content` | Visitor intentionally selects an internal marketing CTA | `content_type=cta`, stable `content_id` | Recommended engagement event |
| `generate_lead` | Newsletter/freebie action succeeds | `lead_source=newsletter|freebie`, optional stable `offer_id` | Recommended key event |

Use GA4 automatic/enhanced measurement for page views, engagement, forms, outbound links, downloads, video, search, and the default scroll event. Do not create submit, error, or duplicate page-view events.

```ts
type GoogleMarketingEvent =
  | { event: 'select_content'; content_type: 'cta'; content_id: string }
  | { event: 'generate_lead'; lead_source: 'newsletter' | 'freebie'; offer_id?: string };

window.dataLayer = window.dataLayer || [];
window.dataLayer.push(event);
```

## Rules

- Emit `generate_lead` after success, never at submit time.
- Send errors to diagnostics, not GA4.
- Do not call `gtag` from application helpers; GTM owns routing.
- Use stable low-cardinality identifiers. Never send email, form contents, lead IDs, URLs containing secrets, or raw attribution objects.
- Register a custom definition only when an actual report needs the parameter. The baseline registers event-scoped `offer_id`.
- Verify retries, React remounts, route transitions, and double-clicks do not produce duplicates.

Primary references:

- https://developers.google.com/analytics/devguides/collection/ga4/reference/events
- https://developers.google.com/tag-platform/tag-manager/datalayer
