# Agent Instructions

The Skill Problem System keeps agent skills as ordinary Git-backed files and projects them into the locations used by supported agents.

- Name skills with lowercase letters, numbers, and hyphens. The directory name and frontmatter `name` must match.
- Put authored skills under this package's `edit/skills/` directory.
- Keep related skills under a `_lower-kebab` group folder.
- Put public defaults and schemas under this package's `internal/defaults/` and `internal/schemas/`.
- Put user-specific configuration under `edit/settings/`. Put skill-specific private configuration under `edit/settings/skills/config/<skill>/private/`.
- Never store credential values in this repository.
- Read the `agents-i-write-or-edit-a-skill` skill before creating or reorganizing a skill.
- Validate changes with `fleet config validate`, then run `fleet sync --dry-run` before `fleet sync`.

Preserve provenance and license notices when importing a skill. Keep generated catalogs and machine state out of source control.
