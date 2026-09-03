---
name: agents-i-write-a-skill
description: Creates or updates agent skills to match the Vault's authoring standards. Use when the user asks to create, write, rename, reorganize, thin, or improve a skill or its supporting references, scripts, assets, or discovery description.
---

# Agents · Write a Skill

Before editing, read `_system/agents/README.md`, `_system/agents/_package/docs/skills.md`, and `_system/local/README.md`.

## Workflow

1. Define the user-facing capability and the concrete ways a user would ask for it.
2. Read [[skill-authoring-method|Skill Authoring Method]] for description, structure, progressive-disclosure, and validation standards.
3. Create every Vault-owned skill under `_system/agents/skills/<_group>/<skill>/SKILL.md`, never in the Vault root's `.agents/skills`. Use `<category>-i-<capability>` for implicit skills and `<category>-<capability>` for manual skills; make the marker agree with `agents/openai.yaml`.
4. Choose the matching existing `_lower-kebab` category group and category-prefixed skill name from the canonical Skill SOP. Preserve established names unless the user requests a rename or the name is invalid.
5. Treat `_system/agents/skills/catalog` as a generated symlink-only catalog, never a source location. Repository-local `.agents/skills` applies only when the user explicitly asks to author a skill inside a separate owning code repository, not for the Vault itself.
6. Keep `SKILL.md` as a thin routing and execution contract. Split distinct platforms, approaches, or long procedures into directly linked references when that improves clarity.
7. Put deterministic utilities in `scripts/`, reusable files in `assets/`, and changing personal facts in `_system/agents/_package/instance/skills/config/<skill-name>/`.
8. For GH installs, repository-owned skills, global links, overlays, and snapshots, read [[repo-skill-projections|Repository Skills and Composition]].
9. Test applicable scripts, then run `ctx9-agents sync --dry-run` and `ctx9-agents sync` for shared or enrolled skills.

Follow explicit user structure requests. Otherwise use judgment: prefer fewer, clearer files, but do not keep multiple substantial workflows in one `SKILL.md` merely to avoid a reference.
