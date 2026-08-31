## Repository skills and composition

- Put a repository-owned skill in that repo's `.agents/skills/l-<capability>` first. It is local by default and must not be globally projected merely because the repository is registered.
- When a selected user-owned repository skill needs global discovery, add its repo-relative source and `auto` or `manual` mode to that repository's `skill_projections` list in the private topology registry.
- `ctx9-agents sync` derives `<repo-id>-<capability>`, materializes the tracked projection under `_system/agents/skills/projected/<repo-id>/<projected-name>/`, and rewrites local `$l-sibling` references to projected names. The `auto` or `manual` mode remains in registry and projection metadata rather than a folder. Keep projected names at most 64 characters and collision-free.
- Refer to another capability as `$skill-name`. Do not embed an absolute skill directory. Use `vault root` only when a workflow genuinely needs a filesystem path to the Vault.
- Relative paths between skill sources are allowed only when both skills are Vault-owned and move together. Repository skills and projected copies must use skill names for composition.
- A manual skill is an explicit-only dependency: tell the user which `$skill-name` to invoke rather than silently composing it. A dependency that must be automatically composed belongs in auto skills.
- Materialized local-repo projections are generated copies, not sources. Update the owning repository skill, then run `ctx9-agents sync --dry-run` and `ctx9-agents sync`.
