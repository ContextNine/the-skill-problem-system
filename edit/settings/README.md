# Agent settings

- `fleet/machines.json`: machines, roots, roles, routes, and Vault participation.
- `fleet/workspaces.json`: repository registration and reconciliation.
- `skills/skill-sources.json`: GitHub and existing-checkout skill enrollment.
- `skills/skill-metadata.json`: 0–5 ratings and folder-derived areas/collections. Read [README-skill-ratings](skills/README-skill-ratings.md) for `fleet skills list`, `rate`.
- `dependencies/selections.json`: approved workspace-built commands.
- `skills/config/`: changing per-skill facts and private settings.
- `public-skill-repo-export-exclusions.json`: full exclusions and partial hiding for the public skills repository.

Credential values remain in their machine-local custody systems. Settings here contain metadata and desired state only.

## Public skill privacy

Every locally maintained area or collection is public by default and requires no registration. Use `exclude` only for private content. Its patterns are case-sensitive globs relative to `edit/`; `/**` excludes a directory and everything below it, while a plain file path excludes one file.

Use `partial_hiding` for an exact skill or folder that should remain visible by name but expose no content. The exporter replaces it with `<name>-REDACTED`. Git cannot store a literally empty directory, so the redacted folder contains only a zero-byte `.gitkeep`.

```json
{
  "schema_version": 2,
  "exclude": [
    "skills/areas/example/**",
    "skills/areas/code/example-skill/**",
    "skills/areas/code/another-skill/references/private-notes.md"
  ],
  "partial_hiding": [
    "skills/areas/personal",
    "skills/areas/code/internal-skill"
  ]
}
```

The first exclusion hides a whole area, the second hides one skill, and the third hides one file. The partial-hiding entries become `skills/areas/personal-REDACTED/` and `skills/areas/code/internal-skill-REDACTED/`. Partial-hiding paths are exact directories, not globs. Overlapping paths, negated patterns, absolute paths, and parent traversal are invalid. Export fails if a retained skill still references removed content.

Public development previews use `fleet/preview.json`. The `$fleet-i-public-dev-preview` skill owns setup and verification.
