# Edit agent configuration

This is the user-editable source for agent skills and fleet configuration.

- `agent-instructions/`: shared instructions, flat machine templates, and its local `README.md` editing guide.
- `skills/`: read [README-skill-ratings](settings/skills/README-skill-ratings.md) and its local `README.md` for folder-derived `areas/`, locally maintained `collections/`, GitHub imports, dormant, and public-only skill sources.
- `settings/`: machine registry, workspaces, skill-source choices, integrations, dependency selections, and public export exclusions.

Edit here, run `fleet sync --dry-run`, review the destinations, then run `fleet sync`. Do not edit installed or generated files as source.

The Vault root `AGENTS.md` remains this Vault project's instruction file. `agent-instructions/AGENT-INSTRUCTIONS.md` is the global instruction base shared across machines.
