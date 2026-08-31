# Reuse and Migration

## Reuse in another application

1. Create a new GA4 property/stream and one GTM container for the destination domain.
2. Copy `assets/gtm/reusable-baseline.template.json` and replace every declared placeholder.
3. Adapt only the small consent provider and typed event helper from `assets/impression-next-source-snapshot/`; application source remains authoritative.
4. Set the target repo's GTM public ID through its environment workflow.
5. Import into a dedicated workspace with Merge, review Detailed Changes, and verify before publish.
6. Register only custom definitions named in the event contract and mark only real business outcomes as key events.
7. Add an instance manifest, raw export, normalized snapshot, ownership checklist, and verification report to the destination repository.

## Moving an existing setup

- Renaming GA4/GTM resources preserves identifiers and history.
- A GA4 property can be moved between Analytics accounts when Google prerequisites and permissions are satisfied; record what remains in the source account.
- GTM does not provide an equivalent identity-preserving cross-account move. Export/import into a new container changes the public `GTM-…` ID and requires an application/environment rollout.
- Never delete the old property/container until the new ID has been deployed, verified, and rollback evidence retained.

Primary migration references:

- https://support.google.com/analytics/answer/9305872?hl=en
- https://support.google.com/tagmanager/answer/6106997?hl=en
