# Agent Instructions

The Skill Problem System keeps agent skills as ordinary Git-backed files and projects them into the locations used by supported agents.

- Name skills with lowercase letters, numbers, and hyphens. The directory name and frontmatter `name` must match.
- Put implicit shared skills in `_system/agents/skills/` and explicit-only skills in `_system/agents/skills/`.
- Keep related skills under a `_lower-kebab` group folder.
- Put public defaults and schemas under `_system/agents/_package/defaults/` and `_system/agents/_package/schemas/`.
- Put user-specific configuration under `_system/agents/_package/instance/`. Put skill-specific private configuration under `_system/agents/_package/instance/skills/config/<skill>/private/`.
- Never store credential values in this repository.
- Read `_system/agents/_package/docs/skills.md` before creating or reorganizing a skill.
- Validate changes with `ctx9-agents config validate`, then run `ctx9-agents sync --dry-run` before `ctx9-agents sync`.

Preserve provenance and license notices when importing a skill. Keep generated catalogs and machine state out of source control.
