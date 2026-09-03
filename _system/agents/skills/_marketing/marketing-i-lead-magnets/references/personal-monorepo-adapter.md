# Personal monorepo adapter

Read repository `AGENTS.md`, `.docs/audience-growth-and-attribution.md`, and `.docs/tenants/ReadMe-<tenant-id>.md` before changing a tenant.

Current audience boundaries in `apps/next_multi_tenant`:

- `src/config/audiences/index.ts`: tenant ownership, offer copy, and `confirmationDestinationPath`.
- `src/app/api/audience/signup/route.ts`: signup and consent persistence.
- `src/app/api/audience/confirm/route.ts`: confirmation and redirect boundary.
- `src/lib/audiences/`: email, Kit, attribution, and validation.
- `src/__tests__/audience-growth.test.ts`: focused tenant isolation and provider flow.

Keep tenant destinations local unless an external destination is intentional. A custom destination belongs at `/freebie/<slug>/download`; its tenant-owned config/copy owns `downloadUrl`, resource copy, optional video/proof, analytics, and upsell destination.

Before non-trivial tenant UI, create static layout mocks and obtain selection under the repository workflow. Run the focused audience test and app typecheck. Verify tenant isolation and preserve current direct redirect behavior until the custom page is intentionally implemented. Do not change another tenant, deploy, provision storage, or upload production assets unless separately requested.
