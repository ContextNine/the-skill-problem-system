---
type: agent-reference
status: enabled
---

## Linux remote Vault access

This is the optional Linux capability route owned by `$infra-i-onboard-machine`. It mounts one registered Mac's complete, materialized iCloud Vault at the Linux worker's registered Vault root through SSHFS. It does not create a clone, sparse checkout, copied publication tree, Git proxy, or Git coordinator.

Use it only when the schema-v7 machine registry selects `vault.checkout_mode: remote-sshfs`. A Linux machine in mode `none` remains a Code-only worker and follows [[README-vault-host-boundary|Vault Host Boundary]].

### Invariants

- The registry derives the source alias and source path from the selected macOS host. Do not duplicate or hard-code them in scripts.
- Mount only the exact Vault directory. Never mount the host home, iCloud parent, Git directory, credential directories, or another broad path.
- The mount contains the entire Vault, including `_library`, `_system`, context folders, hidden files, and media.
- The shared `.git` pointer remains unchanged and deliberately unresolved on the host and client. Only the registered `vault_git.owner_machine_id` runs Vault Git.
- The SSHFS mount can be read-write, but managed writes require the shared host-side lease.
- Filesystem save, host iCloud upload, primary peer observation, and Git push are distinct diagnostic states. Only filesystem durability and lease release gate a remote edit session.
- Skill and instruction distribution is independent of the mount and continues through `ctx9-agents sync` from the primary.

### Registry contract

The iCloud host is an enabled macOS machine with a full local Vault and:

```json
"vault": {
  "enabled": true,
  "checkout_mode": "icloud-gitless",
  "required": true,
  "remote_access": {"host_enabled": true}
}
```

The Linux client is an enabled SSH worker with a Vault root outside its Code root and:

```json
"roots": {"code": "~/Code", "vault": "~/Vault"},
"vault": {
  "enabled": true,
  "checkout_mode": "remote-sshfs",
  "required": true,
  "remote_access": {
    "source_machine_id": "MAC_HOST_ID",
    "writable": true
  }
}
```

For a newly registered Linux worker, the deterministic lower-level registration route accepts `--vault-root ~/Vault --vault-source MAC_HOST_ID`. Keep the machine disabled until complete onboarding and reboot acceptance. Validate desired state before deployment:

```bash
ctx9-agents config validate
vault machine status CLIENT_ID
```

Validation rejects direct Linux Vaults, Code-root targets such as `~/Code/vault`, disabled or self sources, non-Mac sources, sources without `host_enabled`, overlapping roots, and Git-owner mismatches.

### Dependency gate

`sshfs` is a selected typed dependency with `remote-vault-clients` eligibility. It is installed only on registered `remote-sshfs` machines. The user must approve the first dependency update; routine sync only converges declared state.

From the registered primary:

```bash
ctx9-agents update --dependencies --target CLIENT_ID
ctx9-agents sync --dependencies --target CLIENT_ID --verify
```

If APT needs a password, use the dependency workflow's reviewed action in a separate real-terminal SSH command. Do not pipe a password, improvise an `apt` command, or broaden the dependency to every Linux worker.

### Preview, apply, verify, and remove

The reviewed controller is generic and reads topology from the registry:

```bash
controller="$(vault root)/_system/agents/skills/_infrastructure/infra-i-onboard-machine/scripts/remote_vault_access.py"
python3 "$controller" controller CLIENT_ID
python3 "$controller" controller CLIENT_ID --apply
python3 "$controller" controller CLIENT_ID --verify
```

Preview reports the derived mount and source roots plus SSH, identity, materialization, Gitless-pointer, client-to-host mesh, and SSHFS gates. Apply stages the reviewed helper on each target, installs the host helper and client atomically with adjacent backups, creates owner-only state, starts the exact-path mount, performs structural acceptance, and enables the systemd user unit only after acceptance passes.

Remove is explicit:

```bash
python3 "$controller" controller CLIENT_ID --remove
```

Removal refuses an active writer session or lease and performs only a graceful unmount. It removes only marker-owned client/host files and preserves adjacent backups, state, receipts, and Vault bodies for review.

### Installed client

The Linux launcher and configuration remain usable while the mount is absent:

```text
~/.local/bin/vault
~/.local/share/vault-access/remote_vault_access.py
~/.config/vault/machine-id
~/.config/vault/remote-access.json
~/.config/systemd/user/vault-remote.service
~/.local/state/vault-remote/
```

The host helper and authoritative state live outside iCloud:

```text
~/.local/share/vault-access/remote_vault_access.py
~/.config/vault/remote-access-host.json
~/.local/state/vault-remote/
```

No credentials, iCloud tokens, Vault bodies, or Git state belong in those state directories. The unit uses foreground SSHFS, reconnect, bounded SSH keepalive and connection timeouts, no writeback cache, short metadata timeouts, user ownership mapping, no `allow_other`, and no forced busy unmount.

### Normal read and write workflow

Before reads:

```bash
vault root
vault access status
vault access doctor
```

Status must prove SSH, exact `fuse.sshfs` source, read-write mode, the root sentinel, host identity, Keep Downloaded, recursively downloaded, no dataless items, no conflicts, no pause, current downloaded version, and current lease state. Upload and container caught-up state remain visible diagnostics but never block access or completion. Unknown safety-critical File Provider output is unhealthy.

Before writes, close Obsidian and every unmanaged Vault writer on other machines, then:

```bash
vault access begin --task-id TASK_OR_THREAD_ID
```

The host atomically acquires the one writer lease, records a lightweight snapshot, and the client starts a heartbeat. Managed content-write commands fail without an active matching lease. Unmanaged editors can bypass this boundary, so the human single-writer rule still matters.

After writes:

```bash
vault access finish
```

Finish computes changed and deleted paths, hashes changed regular files, fsyncs changed files and parent directories on the Mac host, writes an ignored diagnostic receipt beneath `_system/local/state/remote-vault-receipts/`, releases the lease, and returns immediately. It never waits for named paths, receipt upload, or container caught-up state. The Linux task may report its filesystem edit finished, but never `git-pushed`.

Optional receipt diagnostics on the registered Git-owner Mac:

```bash
vault access wait --receipt SESSION_ID
vault git-preflight
```

Receipt observation can wait for materialization, verify file hashes, symlink targets, and deletions, check conflicts and dataless state, then record `peer-observed`. It is never a prerequisite. Complete the normal root `AGENTS.md` Vault-wide commit and push against the worktree currently visible to the Git owner. After the commit is present on the configured remote branch, optional bookkeeping can record the last state:

```bash
vault access ack-git --receipt SESSION_ID --commit COMMIT_SHA
```

### Acceptance

Before enablement and again after reboot, prove:

1. Client-to-host SSH and SFTP use the registered stable alias.
2. `findmnt` reports the exact expected source, `fuse.sshfs`, and `rw` without `allow_other`.
3. `AGENTS.md`, `_library`, `_system`, context folders, hidden paths, filenames with spaces and Unicode, symlinks, and representative large media are readable.
4. `.git` exists as the shared pointer but `git -C "$(vault root)" rev-parse --git-dir` fails.
5. A leased write probe survives finish and host fsync while the lease releases without waiting for upload; optional later inspection may verify iCloud and Git-owner observation.
6. `ctx9 doctor codex-repo-sync --json` remains healthy in Code repositories and performs no Vault Git work in the mount.
7. `systemctl --user is-enabled vault-remote.service` passes only after first acceptance.
8. Restart the client and host, then prove unattended inbound SSH, automatic mount recovery, fresh host identity, read-write health, and a second receipt boundary.

### Recovery

- Missing or unhealthy mount: run `vault access doctor`, inspect `journalctl --user -u vault-remote.service`, repair SSH/source/iCloud health, then retry. Never create a fallback clone.
- Busy unmount: close handles and retry graceful unmount. Never use lazy or forced unmount.
- Active lease: identify the owner and session. Never steal a live lease.
- Expired abandoned lease: prove the writer is no longer operating, then record the reason with `vault access recover --reason "..."`. Recovery refuses a live lease.
- Unknown safety-critical File Provider output: retain the session and lease, repair the exact Mac/iCloud condition, and finish again. Pending or unknown outbound upload alone does not retain the lease or block completion.
- Conflict or dataless item: stop, materialize and compare deliberately on the Mac host; do not delete, reset, or choose a winner automatically.
- Source replacement or alias change: update the registry, re-render full-mesh SSH, rerun preview/apply/verify, and repeat reboot acceptance.

The iCloud host must continue passing [[worker-mac-power-and-sleep|Worker Mac Power and Sleep]]. Remote Vault availability depends on a fresh unattended inbound connection, not only a running process or outbound network activity.
