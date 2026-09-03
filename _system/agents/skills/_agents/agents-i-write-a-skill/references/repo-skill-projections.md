## Repository skills and composition

- Put a repository-owned skill in that repo's `.agents/skills/<repo-name>-<capability>`. It remains local unless explicitly enrolled in `_system/agents/_package/instance/skills/skill-sources.json`.
- `workspaces.json` registers and reconciles repositories. It does not enroll their skills.
- Enrolled checkouts use literal `~/` paths and either `all_skills: true` or source-only `skills` entries.
- Without a prefix, sync creates a direct link when source and global invocation policy agree. A policy-only difference creates a linked overlay. A configured prefix creates a snapshot because names, H1s, or `$skill` references must be rewritten.
- Public third-party skills belong under `_system/agents/skills/github/<repo-name>/skills` and are installed and updated with `gh skill` so publisher metadata remains authoritative.
- Refer to another capability as `$skill-name`, never by absolute skill directory. A named dependency may be composed even when manual-only; manual policy prevents unsolicited top-level selection.
- Relative paths between skills are appropriate only when both files share one canonical source tree and move together.
- Generated overlays, snapshots, and catalog links are outputs. Update the canonical Vault, GH, or checkout source, then run `ctx9-agents sync --dry-run` and `ctx9-agents sync`.
