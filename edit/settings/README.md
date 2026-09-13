# Agent settings

- `fleet/machines.json`: machines, roots, roles, routes, and Vault participation.
- `fleet/workspaces.json`: repository registration and reconciliation.
- `skills/skill-sources.json`: GitHub and existing-checkout skill enrollment.
- `dependencies/selections.json`: approved workspace-built commands.
- `skills/config/`: changing per-skill facts and private settings.
- `public-skill-repo-export-exclusions.json`: user-selected files or skill groups omitted from the public skills repository.

Credential values remain in their machine-local custody systems. Settings here contain metadata and desired state only.
