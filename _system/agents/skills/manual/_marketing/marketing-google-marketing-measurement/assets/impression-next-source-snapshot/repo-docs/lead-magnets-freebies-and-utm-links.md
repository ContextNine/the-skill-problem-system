# Lead Magnets, Freebies, and UTM Links

Public lead magnet pages live at `/freebie/[slug]`.

Example:

`https://impression.so/freebie/claude-in-10mins?utm_source=linkedin&utm_medium=organic_social&utm_campaign=claude_freebie&utm_content=post_hook_1`

## Where They Live

- Route: `apps/next/src/app/(freebies)/freebie/[slug]/page.tsx`
- Success page: `apps/next/src/app/(freebies)/freebie/[slug]/success/page.tsx`
- Confirmation route: `apps/next/src/app/api/freebie/[slug]/confirm/route.ts`
- Page config: `apps/next/src/config/freebies-config.ts`
- Per-freebie config: `apps/next/src/config/freebies/<slug>.ts`
- Signup form: `apps/next/src/components/marketing/freebies/freebie-signup-form.tsx`
- Server action: `apps/next/src/app/(marketing)/(actions)/email-actions.ts`
- Next use case: `apps/next/src/lib/freebies/freebie-signup.ts`
- DB lead service: `apps/node/src/domain/freebie-leads/freebie-lead.service.ts`

## Add New Freebie

1. Copy `apps/next/src/config/freebies/claude-in-10mins.ts` to `apps/next/src/config/freebies/<slug>.ts`.
2. Set `slug`, `title`, `description`, `shortDescription`, `image`, `delivery`, and `success` copy.
3. Import config into `apps/next/src/config/freebies-config.ts`.
4. Add config object to `FREEBIE_LEAD_MAGNETS`.
5. Add or reuse public image/asset under `apps/next/public`.

## Delivery Modes

Kit mode:

```ts
delivery: {
  mode: 'kit',
  formId: '123456',
}
```

Kit mode subscribes email to that Kit form. Kit automation must send asset. App tracks GA4 events and passes attribution fields into Kit.

DB mode:

```ts
delivery: {
  mode: 'db',
  resourceUrl: '/freebies/claude-in-10mins.pdf',
  email: {
    subject: 'Your Claude in 10 minutes resource',
    heading: 'Confirm your email',
    body: 'Click below to confirm your email and open the resource.',
    ctaText: 'Get your free resource',
  },
}
```

DB mode stores pending lead in `FreebieLead`, sends one confirmation/resource email, confirms on `/api/freebie/[slug]/confirm?token=...`, redirects to `resourceUrl`, then creates/updates Kit subscriber. Kit sync retries 3 times. If Kit sync still fails, resource redirect still works and failure is stored/logged.

If no ConvertKit form exists for lead magnet, use DB mode. Do not leave `mode: 'kit'` with placeholder form id.

## Tracking

Freebie forms send one GA4 event through GTM after a successful signup:

- `generate_lead`
- `lead_source=freebie`
- `offer_id=<freebie slug>`

Submit attempts and failures are not GA4 events. Failures remain in application/server diagnostics. GA4 uses its native campaign attribution instead of receiving a second copy of every UTM and click ID as custom event parameters.

Signup also sends same attribution fields to Kit or DB, plus first-touch cookie fields like `first_touch_landing_path` and `first_touch_utm_source`.

PostHog stays app-only. Public freebie pages use GA4. Existing first-touch cookie still carries attribution into app-side PostHog person properties after signup/login.

## Attribution Mental Model

GA4 is event ledger. GTM is router. UTM and click ids are attribution hints.

Flow:

1. Visitor lands on tagged URL.
2. `marketing_first_touch_v1` captures first known landing attribution for 90 days.
3. Form submit reads current URL attribution plus first-touch cookie.
4. Signup action stores/sends attribution through Kit mode or DB mode.
5. A successful action pushes `generate_lead` with the stable freebie slug as `offer_id`.
6. GTM routes the event to GA4, where `generate_lead` is a key event.

Use GA4 for acquisition reporting. Use DB/Kit for lead fulfillment and follow-up. Do not treat Kit as analytics source of truth.

## GTM / GA4 Setup

In GTM:

1. Keep Google tag / GA4 measurement tag loaded by GTM.
2. Add Custom Event trigger for `generate_lead`.
3. Add GA4 Event tag named `generate_lead`.
4. Map `lead_source` and `offer_id` only.
5. In GA4, mark `generate_lead` as key event.
6. Register `offer_id` as an event-scoped custom dimension.

## UTM Links

Use one final URL per source/placement/creative. Generate links in a spreadsheet, not by hand in browser bar.

Pattern:

```text
utm_source = platform/vendor
utm_medium = channel
utm_campaign = offer_or_launch
utm_content = placement_or_creative
utm_term = paid keyword/audience only
utm_id = stable campaign id when needed
```

Examples:

```text
https://impression.so/freebie/claude-in-10mins?utm_source=linkedin&utm_medium=organic_social&utm_campaign=claude_freebie&utm_content=post_hook_1

https://impression.so/freebie/claude-in-10mins?utm_source=linkedin&utm_medium=organic_social&utm_campaign=claude_freebie&utm_content=bio_link

https://impression.so/freebie/claude-in-10mins?utm_source=newsletter&utm_medium=email&utm_campaign=claude_freebie&utm_content=issue_042_cta

https://impression.so/freebie/claude-in-10mins?utm_source=partner_acme&utm_medium=referral&utm_campaign=claude_freebie&utm_content=resource_page
```

Rules:

- lowercase only.
- use `_`, not spaces.
- never rename campaign mid-flight.
- short links must preserve full query string.
- paid ads keep UTMs plus platform click ids.

## Page Shell

Freebie pages intentionally do not use marketing nav/footer wrapper. They are forced to light mode through `FORCED_LIGHT_THEME_ROUTES`, show only a small icon-only Impression home link at top left, and keep lead magnet section fully bordered.
