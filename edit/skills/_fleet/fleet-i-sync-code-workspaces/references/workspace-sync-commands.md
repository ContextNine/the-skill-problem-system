---
type: agent-reference
status: enabled
---

## Workspace sync commands

Run from the skill directory:

```bash
python3 scripts/sync_code_workspaces.py discover
python3 scripts/sync_code_workspaces.py discover --path "$(fleet config get fleet.machines.MACHINE_ID.roots.code)/group"
python3 scripts/sync_code_workspaces.py reconcile --target linux-worker
python3 scripts/sync_code_workspaces.py reconcile --target linux-worker --apply
python3 scripts/sync_code_workspaces.py reconcile --target NEW_MACHINE --provision-disabled --apply
python3 scripts/sync_code_workspaces.py bootstrap --target linux-worker --apply
python3 scripts/sync_code_workspaces.py refresh --target linux-worker
python3 scripts/sync_code_workspaces.py doctor --target linux-worker
python3 scripts/sync_code_workspaces.py migrate-github-remotes --target linux-worker
python3 scripts/sync_code_workspaces.py migrate-github-remotes --target linux-worker --apply
python3 scripts/sync_agent_configuration.py --target linux-worker --verify
tail -n 20 "$(fleet config get fleet.machines.MACHINE_ID.roots.code)/.workspace-sync/history.jsonl"
```

- `discover`: resolve the selected catalog profile or recursively scan each repeated `--path`; never contact targets.
- `reconcile`: preferred repeat and onboarding command; sync agent configuration, move or clone missing repositories, fetch and fast-forward clean non-ahead branches, then reconcile Primary machine's installed plugins.
- `bootstrap`: first-run behavior that syncs agent configuration, clones missing repositories or safely reuses one unique matching checkout, then reconciles plugins.
- `refresh`: sync agent configuration, fetch matching repositories, fast-forward only clean non-ahead branches, then reconcile plugins.
- `doctor`: verify agent configuration, Git and Codex readiness, repository state, plugin/marketplace state, `.codex`/`AGENTS.md`, and project paths without mutation.
- `migrate-github-remotes`: require canonical SSH URLs in the catalog, preflight the source and every selected target, then change only same-identity remote transport. Apply verifies each write, restores the old URL on failure, and records source/target history.

Without `--target`, target every other enabled machine. Without `--profile`, use the catalog's default profile. Repeat `--entry`, `--path`, or `--target` as needed. During reviewed onboarding, `--provision-disabled` requires exactly one explicit disabled target and refuses enabled targets.

Apply uses a fleet-wide preview and authentication phase before any target mutation. It checks repository and Git-marketplace access, target Codex plugin JSON support, parseable target configuration, and registered local marketplace paths. Each target repeats remote access and repository `git ls-remote` checks immediately before applying. Registered `terminal_profile.remote_path` supplies the intended noninteractive command path.

### Review gates

- Review discovery before first bootstrap. Target content comes from canonical remotes, not local uncommitted source files.
- Source repositories that are dirty or locally ahead require explicit remote-only confirmation before bootstrap apply.
- A moved exact source checkout is adopted only when its canonical remote resolves to one unambiguous path and `--adopt-source-layout` is supplied.
- Target relocation requires an absent destination and exactly one same-remote checkout. Dirty relocation additionally requires `--allow-dirty-relocation`.
- Credential-bearing or local remotes, path escapes, ambiguous matches, nested repositories, linked worktrees, and destination conflicts stop unchanged.
- Existing dirty, ahead, divergent, detached, remote-mismatched, non-Git, or symlink-escaped targets remain unchanged.
- HTTPS and SSH URLs for the same repository are transport drift, not identity drift. Normal reconciliation reports and maintains desired transport; repo-specific `core.sshCommand` blocks automatic migration for manual review.
- Partial clones use `--filter=blob:none`; Git LFS smudging stays disabled and submodules stay uninitialized.

Applied `bootstrap`, `reconcile`, and `refresh` runs record correlated source and target history plus machine-local fleet plugin ownership under `<resolved Code root>/.workspace-sync/`. Preview and doctor remain read-only. After first setup, save each reported repository root as a local or SSH project in ChatGPT when cross-host task handoff is required.
