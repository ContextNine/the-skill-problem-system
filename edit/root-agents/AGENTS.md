# Agent Instructions

The Skill Problem System keeps agent skills as ordinary Git-backed files and projects them into the locations used by supported agents.

- Name skills with lowercase letters, numbers, and hyphens. The directory name and frontmatter `name` must match.
- Put implicit shared skills in `_system/agents/edit/skills/` and explicit-only skills in `_system/agents/edit/skills/`.
- Keep related skills under a `_lower-kebab` group folder.
- Put public defaults and schemas under `_system/agents/internal/defaults/` and `_system/agents/internal/schemas/`.
- Put user-specific configuration under `_system/agents/edit/settings/`. Put skill-specific private configuration under `_system/agents/edit/settings/skills/config/<skill>/private/`.
- Never store credential values in this repository.
- Read `_system/agents/edit/skills/_agents/agents-i-write-or-edit-a-skill/references/skill-authoring.md` before creating or reorganizing a skill.
- Validate changes with `fleet config validate`, then run `fleet sync --dry-run` before `fleet sync`.

Preserve provenance and license notices when importing a skill. Keep generated catalogs and machine state out of source control.
