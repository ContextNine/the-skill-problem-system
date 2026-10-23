Fleet owns machine access and configuration. Its installed runtime and settings work independently of a Vault.

```bash
fleet machine list
fleet machine status MACHINE_ID
fleet machine ssh MACHINE_ID -- uname -a
fleet machine vnc MACHINE_ID
fleet machine vnc MACHINE_ID --status
fleet machine vnc MACHINE_ID --stop
fleet machine setup
fleet machine identify MACHINE_ID
fleet machine access inspect MACHINE_ID --provider tailscale
fleet machine access render --dry-run
fleet machine startup status --json
fleet machine startup install --dry-run
fleet machine startup install
fleet workspaces discover
fleet workspaces doctor --target MACHINE_ID
fleet terminal profiles --target MACHINE_ID --verify
fleet terminal cmux --verify
fleet terminal warp --verify
```

Machine registry edits and provider rendering/switching require the registered primary and its editable Fleet source. They apply by default; use `--dry-run` for a preview. SSH, VNC, listing and reachability use the installed registry on workers and do not require Vault access. Fleet identity lives in `~/.agents/state/machine-id`. Identifying a Vault participant also writes its Vault-owned identity.

Use `$fleet-i-onboard-machine` before registration or provider changes. After changing desired state, run `fleet sync --config --instructions --skills --dry-run`, review, then apply without `--dry-run` to distribute it. VNC sockets and tunnel metadata live in `~/.cache/fleet-machine/`.

Startup manages this Mac's enabled login actions from Fleet settings. Its packaged runner is copied into the existing per-user login runtime, so login never depends on the Vault or editable source being available. `--provision-disabled` is reserved for reviewed onboarding.

Use `$fleet-i-sync-code-workspaces` for workspace controls. `fleet sync --workspaces` remains the normal reconciliation entry point; `fleet workspaces` exposes discovery, doctor, bootstrap, refresh, reconciliation and GitHub transport migration through the same controller. These controllers preview by default; add `--apply` for mutations.

Use `$fleet-i-manage-terminal-workspaces` for terminal controls. `fleet terminal profiles` manages tmux, btop, Starship and workmux; `cmux` and `warp` manage the primary's layouts. Controllers run on the primary and preview by default; use `--apply` or `--verify` after reviewing targets.

Vault access/mount health, Gitless Vault worker bootstrap, Obsidian profiles, refresh, media and content remain under `vault`. Managed snippets also remain Vault-owned. The unsupported historical backup-sync system has no Vault command or setup suggestion.
