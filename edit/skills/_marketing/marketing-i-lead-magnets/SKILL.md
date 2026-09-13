---
name: marketing-i-lead-magnets
description: Designs and implements repository-native lead magnets, freebies, double opt-in, confirmation delivery, download pages, VSL pages, attribution, and related upsells. Use when creating, changing, auditing, or standardizing an email-gated resource or post-confirmation customer journey.
---

# Marketing · Lead Magnets

Lead magnets share a delivery contract, not a component library. Audit the owning repository before changing its signup, consent, confirmation, analytics, email, or UI behavior. Keep each page hand-authored for its offer and repository.

Read the references needed for the task:

- [Double Opt-in and Delivery](references/double-opt-in-and-delivery.md) for every gated resource.
- [Full VSL Page](references/full-vsl-page.md) for long-form post-opt-in selling.
- [Minimal Download Page](references/minimal-download-page.md) for intentionally small delivery pages.
- [Impression Adapter](references/impression-adapter.md) or [Personal Monorepo Adapter](references/personal-monorepo-adapter.md) for repository-specific source locations.

## Default workflow

1. Audit the current acquisition URL, consent record, token lifecycle, provider sync, email, confirmation redirect, analytics, and delivery asset.
2. Keep one durable lower-kebab offer slug across routes, database state, email copy, analytics, and asset keys.
3. Prefer the repository's DB-backed double opt-in when it already owns consent state.
4. Redirect a confirmed lead to `confirmationDestinationUrl`; tenant-local configs may use `confirmationDestinationPath`.
5. Let that destination expose the actual `downloadUrl` and any optional VSL or upsell.
6. Use `$infra-i-file-upload` for requested public or lead-magnet assets.
7. Use `$marketing-manage-utm-tracking-links` only when the user explicitly invokes it for managed campaign links.
8. Validate tenant/offer isolation, accessibility, mobile layout, analytics, and the complete email-to-download journey.

## Boundaries

- Never wrap a secret confirmation-token URL in a short-link service. Promotion URLs may use managed links.
- Store original signup attribution separately from a fixed confirmation-email visit attribution.
- A public asset is not secret merely because email confirmation precedes it.
- Do not invent proof, outcomes, testimonials, medical claims, or urgency. Remove unsupported VSL sections.
- Do not add a shared React package, page builder, or universal template unless explicitly requested.
- Create and select static layout mocks before non-trivial UI implementation when the owning repository requires that workflow.
