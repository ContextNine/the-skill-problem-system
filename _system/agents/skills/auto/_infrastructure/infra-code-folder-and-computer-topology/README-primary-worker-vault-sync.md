## Primary and Worker Vault Coordination

### Model

- Fleet primary: owns desired fleet configuration and deployment.
- Vault Git owner: the one enabled `primary-external-git` Mac named by `vault_git.owner_machine_id`. It alone commits, pushes, runs Git preflight, refresh, release, agents sync, and Git-backed media maintenance.
- iCloud worktree host: an enabled Mac with a complete local iCloud Vault and optional `remote_access.host_enabled`.
- Remote Vault client: an enabled Linux SSH worker in `remote-sshfs` mode. It mounts the host's exact complete Vault path read-write but has no Vault Git.
- Code-only worker: a machine in Vault mode `none`.

The primary's external Git metadata stays at `~/.local/share/vault-git/Vault.git`. The shared `.git` pointer is deliberately unresolved on every Gitless iCloud worker and remote client. No worker may create or retain `<resolved Code root>/vault`, a clone, sparse checkout, Git cache, or Git proxy.

The private registry is `_system/agents/_package/instance/fleet/machines.json`, schema v7. It owns the Git and refresh owner IDs, explicit per-machine Vault mode and root, host/client relationship, writable policy, canonical SSH routes, and fleet roles. Primary identity lives in local Git config as `vault.machine-id`; Gitless Mac workers and remote clients use mode-`0600` `~/.config/vault/machine-id`.

### Git rules

- Only the registered Vault Git owner runs Vault Git commands.
- Completed primary work stages and commits the complete tracked and untracked non-ignored worktree, fetches, integrates newer `origin/master` safely, and pushes.
- Background automation never commits, pushes, stashes, resets, rebases, creates merge commits, or fans changes between machines.
- A remote client's ordinary Code repositories retain normal Git. Its mounted Vault does not resolve as a Git worktree, so `codex-repo-sync` safely has no Vault repository to coordinate.

### Gitless iCloud Mac bootstrap

Run from the primary:

```sh
vault worker-sync bootstrap WORKER_ID
vault worker-sync bootstrap WORKER_ID --provision-disabled
```

Bootstrap accepts only an iCloud Gitless Mac. It requires a fully materialized Vault, rejects dataless files, guarantees the shared pointer target is absent, archives only the exact known legacy worker Git directory, writes machine identity, installs the persistent refresh block, and unregisters refresh scheduling. It never initializes or contacts Vault Git.

Verify:

```sh
test -f "$(vault root)/.git"
! git -C "$(vault root)" rev-parse --git-dir
test ! -e "$HOME/Code/vault"
vault refresh-schedule status
```

### Remote Linux capability

Remote access is optional and explicit. Follow [[linux-remote-vault-access|Linux Remote Vault Access]] through `$infra-onboard-machine`. The reviewed controller derives the exact source and client roots from schema v7, deploys the helper outside the mount, creates a user-only correctness-first SSHFS unit, and enables it only after full acceptance.

On a remote client:

```sh
vault access status
vault access begin --task-id TASK
# perform requested Vault edits
vault access finish
```

Status exposes SSH/mount safety, exact source and read-write state, macOS File Provider and iCloud container diagnostics, current lease, receipt, and the four independent state observations. A missing, wrong-source, read-only, conflicted, dataless, paused, or stale-downloaded mount is a hard stop. Pending outbound upload is not. The client finishes after host fsync and lease release and never waits for `icloud-uploaded`, `peer-observed`, or `git-pushed`.

### Writer and handoff rules

The Vault is single-writer across all Macs and remote clients. Managed mutations acquire the authoritative lease outside iCloud on the configured Mac host. Close Obsidian and unmanaged writers before a leased edit. A live lease is never stolen; an expired abandoned lease requires proof and a recorded recovery reason.

The four diagnostic states remain separate:

1. `filesystem-saved`: SSHFS close and host-side fsync completed.
2. `icloud-uploaded`: changed paths and receipt are uploaded/current, conflict-free, and the host container is caught up.
3. `peer-observed`: the Git-owner Mac materialized the named receipt and verified hashes, symlinks, and deletions.
4. `git-pushed`: the complete-worktree commit is present on the configured remote branch.

The primary does not wait for these states. Optional receipt diagnostics are available:

```sh
vault access wait --receipt SESSION_ID
vault git-preflight
```

The primary follows root `AGENTS.md` for the complete-worktree media manifest, commit, integration, and push against the worktree currently visible to it. `vault access ack-git` is optional bookkeeping after that commit is visible on the configured remote branch.
