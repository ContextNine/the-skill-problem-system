## Primary and Worker Vault Coordination

### Model

- Fleet primary: owns desired fleet configuration and deployment.
- Vault Git owner: the one enabled `primary-external-git` Mac named by `vault_git.owner_machine_id`. It alone commits, pushes, runs Git preflight, refresh, release, agents sync, and Git-backed media maintenance.
- iCloud worktree host: an enabled Mac with a complete local iCloud Vault and optional `remote_access.host_enabled`.
- Remote Vault client: an enabled Linux SSH worker in `remote-sshfs` mode. It mounts its configured host's exact complete Vault path read-write but has no Vault Git.
- Code-only worker: a machine in Vault mode `none`.

The primary's external Git metadata stays at `~/.local/share/vault-git/Vault.git`. The shared `.git` pointer is deliberately unresolved on every Gitless iCloud worker and remote client. No worker may create or retain `<resolved Code root>/vault`, a clone, sparse checkout, Git cache, or Git proxy.

### Editing and synchronization

Macs edit their local iCloud Vault normally. Their changes travel through iCloud without a task-level start, finish, handoff, or wait step.

A registered Linux remote client edits the configured Mac host's worktree directly through SSHFS. Before reading or editing, it runs:

```sh
vault access status
```

It continues only when the command exits successfully and reports `"ok": true`. Status confirms the exact source, read-write mount, host identity, complete current download, and conflict-free iCloud state. A failed status is a hard stop. It is never permission to create a fallback clone or copied Vault.

Linux edits are filesystem writes on the configured Mac host. The host's iCloud client then distributes them to the other Macs. No machine waits for another machine or for outbound iCloud upload before finishing ordinary file work.

### Git rules

- Only the registered Vault Git owner runs Vault Git commands.
- Completed primary work stages and commits the complete tracked and untracked non-ignored worktree, fetches, integrates newer `origin/master` safely, and pushes.
- Background automation never commits, pushes, stashes, resets, rebases, creates merge commits, or copies changes between machines.
- A remote client's ordinary Code repositories retain normal Git. Its mounted Vault does not resolve as a Git worktree.

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

### Linux remote capability

Remote access is optional and explicit. Follow [[linux-remote-vault-access|Linux Remote Vault Access]] through `$infra-i-onboard-machine`. The controller derives the exact source and client roots from the fleet registry, deploys the helper outside the mount, creates a user-only SSHFS unit, and enables it only after acceptance.

`vault access status` reports SSH and mount safety, the exact source and read-write state, and the Mac host's File Provider and iCloud health. Missing, wrong-source, read-only, conflicted, dataless, paused, or stale-downloaded state fails closed. Pending outbound upload does not block access.
