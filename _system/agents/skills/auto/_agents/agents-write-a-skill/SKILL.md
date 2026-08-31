---
name: agents-write-a-skill
description: Creates or updates agent skills to match the Vault's authoring standards. Use when the user asks to create, write, rename, reorganize, thin, or improve a skill or its supporting references, scripts, assets, or discovery description.
---

# Agents · Write a Skill

Before editing, read `_system/agents/README.md`, `_system/agents/_package/docs/skills.md`, and `_system/local/README.md`.

## Workflow

1. Define the user-facing capability and the concrete ways a user would ask for it.
2. Read [[skill-authoring-method|Skill Authoring Method]] for description, structure, progressive-disclosure, and validation standards.
3. Every new Vault-owned skill must be created under `_system/agents`; never put a Vault-owned skill in the Vault root's `.agents/skills`. Choose exactly one source tree:
   - implicit capability: `_system/agents/skills/auto/<_group>/<skill>/SKILL.md`
   - explicit/manual capability: `_system/agents/skills/manual/<_group>/<skill>/SKILL.md`
4. Choose the matching existing `_lower-kebab` category group and category-prefixed skill name from the canonical Skill SOP. For example, a manual creative capability belongs under `manual-skills/_creative/creative-<capability>/`. Preserve established names unless the user requests a rename or the name is invalid.
5. Treat `_system/agents/skills/catalog` as a generated symlink-only catalog, never a source location. Repository-local `.agents/skills` applies only when the user explicitly asks to author a skill inside a separate owning code repository, not for the Vault itself.
6. Keep `SKILL.md` as a thin routing and execution contract. Split distinct platforms, approaches, or long procedures into directly linked references when that improves clarity.
7. Put deterministic utilities in `scripts/`, reusable files in `assets/`, and changing personal facts in `_system/agents/_package/instance/skills/config/<skill-name>/`.
8. For repository-owned skills or global projections, read [[repo-skill-projections|Repository Skill Projections]].
9. Test applicable scripts, then run `ctx9-agents sync --dry-run` and `ctx9-agents sync` for shared or projected skills.

Follow explicit user structure requests. Otherwise use judgment: prefer fewer, clearer files, but do not keep multiple substantial workflows in one `SKILL.md` merely to avoid a reference.
