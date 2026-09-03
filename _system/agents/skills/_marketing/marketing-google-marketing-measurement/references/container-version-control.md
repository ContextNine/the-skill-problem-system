# Container Version Control

Google explicitly supports exporting GTM containers as JSON for diffing, sharing, Git version control and later import.

## Snapshot a Container

1. In GTM, open the correct account and container.
2. Go to **Admin → Export Container**.
3. Select a published container version when capturing production truth; select a workspace only when deliberately capturing draft state.
4. Export all dependencies unless documenting a deliberate partial bundle.
5. Name the file `<public-container-id>_v<version>.json`.
6. Run `scripts/inspect-gtm-export.mjs <file>` and review the summary.
7. Record export time, version, account/container IDs, item counts, source, checksum and known gaps next to the snapshot.

Use `scripts/google-marketing.mjs hash --file <export>` for the checksum and `scripts/google-marketing.mjs snapshot` for API-readable live state.

Keep exact organization exports in the matching private config. A reusable asset should be a separately reviewed, sanitized baseline with replaceable destination IDs and domain assumptions.

## Import Safely

1. Create or select a dedicated workspace in the destination container.
2. Prefer **Merge** for reusable components.
3. Choose a conflict policy intentionally; renaming creates duplicates, while overwriting changes existing components.
4. Review **Detailed Changes**, especially deletions, IDs, consent settings, trigger references, domains and custom-template permissions.
5. Confirm the import only when the preview matches the intended change.
6. Use GTM Preview/Tag Assistant and a test environment.
7. Save a named container version with a useful description.
8. Publish only with explicit authorization after acceptance checks.

`Overwrite` removes the existing tags, triggers and variables before replacing them. Treat it as destructive even though GTM creates a version before import.

## API Direction

The Tag Manager API v2 supports accounts, containers, workspaces, tags, triggers, variables, templates and container versions. It requires a Google Cloud OAuth client and GTM-specific scopes. `gws` targets Workspace APIs and is not the right abstraction for this API.

The bundled operator keeps snapshot/diff read-only, `apply` dry-run by default, and `publish` as a separate exact-version command. Both mutations require `--execute` plus the printed confirmation string.

## Primary References

- Export/import: https://support.google.com/tagmanager/answer/6106997?hl=en
- Publishing and versions: https://support.google.com/tagmanager/answer/6107163?hl=en
- Tag Manager REST API: https://developers.google.com/tag-platform/tag-manager/api/reference/rest
- Authorization and scopes: https://developers.google.com/tag-platform/tag-manager/api/v2/authorization
