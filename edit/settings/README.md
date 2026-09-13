# Agent settings

- `fleet/machines.json`: machines, roots, roles, routes, and Vault participation.
- `fleet/workspaces.json`: repository registration and reconciliation.
- `skills/skill-sources.json`: GitHub and existing-checkout skill enrollment.
- `dependencies/selections.json`: approved workspace-built commands.
- `skills/config/`: changing per-skill facts and private settings.
- `public-skill-repo-export-exclusions.json`: user-selected files or skill groups omitted from the public skills repository.

Credential values remain in their machine-local custody systems. Settings here contain metadata and desired state only.

## Public skill exclusions

Patterns are case-sensitive globs relative to `edit/`. Use `/**` to exclude a directory and everything below it. A plain file path excludes only that file.

```json
{
  "schema_version": 1,
  "exclude": [
    "skills/_group/**",
    "skills/_code/example-skill/**",
    "skills/_code/another-skill/references/private-notes.md"
  ]
}
```

The first pattern excludes a whole group, the second one skill, and the third one file. Negated patterns, absolute paths, and parent traversal are invalid. Privacy exclusions and the public allowlist always win. An exclusion fails if a retained skill still references the removed file.
