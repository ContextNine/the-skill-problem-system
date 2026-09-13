# Edit agent configuration

This is the user-editable source for agent skills and fleet configuration.

- `root-agents/`: global `AGENTS.md` and its colocated fleet templates.
- `skills/`: authored, imported, dormant, and public-only skill sources.
- `settings/`: machine registry, workspaces, skill-source choices, integrations, dependency selections, and public export exclusions.

Edit here, run `fleet sync --dry-run`, review the destinations, then run `fleet sync`. Do not edit installed or generated files as source.

The Vault root `AGENTS.md` remains this Vault project's instruction file. `root-agents/AGENTS.md` is the global instruction base shared across machines.
