---
type: agent-reference
status: enabled
---

## Linux remote Vault access

This is the optional Linux capability route owned by `$fleet-i-onboard-machine`. It mounts one registered Mac's complete, materialized iCloud Vault at the Linux worker's registered Vault root through SSHFS. It does not create a clone, sparse checkout, copied publication tree, Git proxy, or Git coordinator.

Use it only when the schema-v7 machine registry selects `vault.checkout_mode: remote-sshfs`. A Linux machine in mode `none` remains a Code-only worker and follows Vault Host Boundary.

### Invariants

- The registry derives the source alias and source path from the selected macOS host. Do not duplicate or hard-code them in scripts.
- Mount only the exact Vault directory. Never mount the host home, iCloud parent, Git directory, credential directories, or another broad path.
- The mount contains the entire Vault, including `_library`, `_system`, teamspace folders, hidden files, and media.
- The shared `.git` pointer remains unchanged and deliberately unresolved on the host and client. Only the registered `vault_git.owner_machine_id` runs Vault Git.
- The SSHFS mount is read-write when the registry enables it. Linux edits land directly in the configured Mac host's worktree.
- The Linux client must pass `vault access status` before reading or editing. Pending outbound iCloud upload does not block access.
- Skill and instruction distribution is independent of the mount and continues through `fleet sync` from the primary.

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
fleet config validate
vault machine status CLIENT_ID
```

Validation rejects direct Linux Vaults, Code-root targets such as `~/Code/vault`, disabled or self sources, non-Mac sources, sources without `host_enabled`, overlapping roots, and Git-owner mismatches.

### Dependency gate

`sshfs` is a selected typed dependency with `remote-vault-clients` eligibility. It is installed only on registered `remote-sshfs` machines. The user must approve the first dependency update; routine sync only converges declared state.

From the registered primary:

```bash
fleet update --dependencies --target CLIENT_ID
fleet sync --dependencies --target CLIENT_ID --verify
```

If APT needs a password, use the dependency workflow's reviewed action in a separate real-terminal SSH command. Do not pipe a password, improvise an `apt` command, or broaden the dependency to every Linux worker.

### Preview, apply, verify, and remove

The reviewed controller is generic and reads topology from the registry:

```bash
controller="$(vault root)/_system/agents/edit/skills/_fleet/fleet-i-onboard-machine/scripts/remote_vault_access.py"
python3 "$controller" controller CLIENT_ID
python3 "$controller" controller CLIENT_ID --apply
python3 "$controller" controller CLIENT_ID --verify
```

Preview reports the derived mount and source roots plus SSH, identity, materialization, Gitless-pointer, client-to-host mesh, and SSHFS gates. Apply stages the reviewed helper on each target, installs the host helper and client atomically with adjacent backups, starts the exact-path mount, performs structural acceptance, and enables the systemd user unit only after acceptance passes.

Remove is explicit:

```bash
python3 "$controller" controller CLIENT_ID --remove
```

Removal performs only a graceful unmount. It removes marker-owned client and host files while preserving adjacent backups and Vault bodies.

### Installed client

The Linux launcher and configuration remain usable while the mount is absent:

```text
~/.local/bin/vault
~/.local/share/vault-access/remote_vault_access.py
~/.config/vault/machine-id
~/.config/vault/remote-access.json
~/.config/systemd/user/vault-remote.service
```

The host helper and configuration live outside iCloud:

```text
~/.local/share/vault-access/remote_vault_access.py
~/.config/vault/remote-access-host.json
```

No credentials, iCloud tokens, Vault bodies, or Git state belong in those configuration paths. The unit uses foreground SSHFS, reconnect, bounded SSH keepalive and connection timeouts, no writeback cache, short metadata timeouts, user ownership mapping, no `allow_other`, and no forced busy unmount.

### Normal read and write workflow

Before reading or editing:

```bash
vault access status
```

Continue only when status exits successfully and reports `"ok": true`. Status must prove SSH, exact `fuse.sshfs` source, read-write mode, the root sentinel, host identity, Keep Downloaded, recursively downloaded, no dataless items, no conflicts, no pause, and the current downloaded version. Pending outbound upload and container caught-up state remain visible but do not block access. Unknown safety-critical File Provider output is unhealthy.

After a successful status check, read and edit ordinary Vault files directly. There is no start, finish, handoff, or wait command. The configured Mac host receives SSHFS writes immediately and iCloud distributes them asynchronously. The Linux task may report its filesystem edit complete, but only the registered Git owner may commit or report `git-pushed`.

### Acceptance

Before enablement and again after reboot, prove:

1. Client-to-host SSH and SFTP use the registered stable alias.
2. `findmnt` reports the exact expected source, `fuse.sshfs`, and `rw` without `allow_other`.
3. `AGENTS.md`, `_library`, `_system`, teamspace folders, hidden paths, filenames with spaces and Unicode, symlinks, and representative large media are readable.
4. `.git` exists as the shared pointer but `git -C "$(vault root)" rev-parse --git-dir` fails.
5. A harmless write, read, and delete probe succeeds through the mounted worktree without waiting for iCloud upload.
6. Code-repository tooling performs no Vault Git work in the mount.
7. `systemctl --user is-enabled vault-remote.service` passes only after first acceptance.
8. Restart the client and host, then prove unattended inbound SSH, automatic mount recovery, fresh host identity, and read-write health.

### Recovery

- Missing or unhealthy mount: run `vault access doctor`, inspect `journalctl --user -u vault-remote.service`, repair SSH/source/iCloud health, then retry. Never create a fallback clone.
- Busy unmount: close handles and retry graceful unmount. Never use lazy or forced unmount.
- Unknown safety-critical File Provider output: repair the exact Mac or iCloud condition, then rerun `vault access status`. Pending outbound upload alone does not block access.
- Conflict or dataless item: stop, materialize and compare deliberately on the Mac host; do not delete, reset, or choose a winner automatically.
- Source replacement or alias change: update the registry, re-render full-mesh SSH, rerun preview/apply/verify, and repeat reboot acceptance.

The iCloud host must continue passing [Worker Mac Power and Sleep](worker-mac-power-and-sleep.md). Remote Vault availability depends on a fresh unattended inbound connection, not only a running process or outbound network activity.
