# Impression adapter

Read the repository `AGENTS.md`, `.docs/analytics-and-seo.md`, public marketing style guide, email docs, and testing docs before implementation.

Current DB-backed freebie boundaries:

- `apps/next/src/config/freebies/`: offer config and `confirmationDestinationUrl`.
- `apps/next/src/lib/freebies/freebie-signup.ts`: Next signup use case.
- `apps/shared/src/data/freebies/freebie-leads.types.ts`: shared command/result contracts.
- `apps/node/src/domain/freebie-leads/`: persistence and confirmation service.
- `apps/next/src/app/api/freebie/[slug]/confirm/route.ts`: redirect boundary.

Keep PostgreSQL as the consent and confirmation source of truth. A custom offer destination belongs at `/freebie/<slug>/download`; its repository-native config owns `downloadUrl`, copy, video, proof, analytics, and upsell destination. Existing direct destinations may remain direct until a custom page is designed.

Run the focused signup/service/confirmation integration tests and affected package typechecks. Verify the redirect destination is unchanged by terminology-only refactors. Do not perform schema migration, deployment, bucket provisioning, or public asset upload unless separately requested.
