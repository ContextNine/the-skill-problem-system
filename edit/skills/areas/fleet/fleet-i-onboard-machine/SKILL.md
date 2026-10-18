---
name: fleet-i-onboard-machine
description: Use when the user asks to set up a new primary Mac, register or add a secondary Mac or everyday laptop, add a worker Mac or Linux worker, rebuild or replace a machine, enroll it in fleet access, or finish machine acceptance. Also used when asking about machine local secret locations.
---

# Fleet · Onboard Machine

Config paths beginning with `./fleet/`, `./skills/`, or `./dependencies/` are relative to the directory returned by `fleet config path`.

Paths beginning with `./internal/` are relative to the package returned by `fleet source path`.

Read `$fleet-i-code-folder-and-computer-topology`, its role model, private config README, registries, and the selected machine convention before operating.

“Register a secondary Mac,” “add a second Mac,” and an additional Mac used physically as an everyday laptop select `./references/secondary-mac-onboarding-and-acceptance.md`. A secondary Mac retains registry role `worker` and the existing primary's ownership. It keeps FileVault, password locking, automatic login off, and normal sleep. Give the user the initial setup and Screen Sharing steps from that reference before provisioning; do not apply unattended-worker defaults or ask them to reconfirm these established preferences.

Collect and validate the machine's absolute home plus user-selected Code and Vault roots during registration. Store Code and Vault roots in `fleet/machines.json`, store workspace paths relative to Code root, and verify them through `fleet config validate` before any sync. Vault participation is an explicit registry choice, not an operating-system inference. Standalone agent-package installation, generated global instructions, Claude alias and discovery aliases are separate opt-ins; do not make any of them a prerequisite for a working Vault.

Read `./references/machine-access-selection.md`, then exactly one provider route: `./references/wireguard-machine-access.md` or `./references/tailscale-machine-access.md`. Neither provider is the default. Keep the registry's canonical SSH alias as the durable identity; use `-lan` and `-mesh` only for diagnosis.

Read `./references/fleet-shell-mesh.md` when provisioning or verifying machine-to-machine SSH. Enabled personal machines use full-mesh regular OpenSSH over Tailscale, one unique dedicated fleet-shell identity per source machine, exact host-key pinning, and all-to-all public-key authorization. Keep disabled machines excluded and keep GitHub keys separate.

For Tailscale, use `./scripts/setup_tailscale_access.py` for preview-first official installation, non-secret desired-state application, sanitized status, and the exact unavoidable authentication or macOS approval checkpoint. Do not replace it with improvised install commands.

Read `$fleet-i-code-folder-and-computer-topology` (GitHub Fleet Authentication). Use `./scripts/github_fleet_auth.py` for dedicated per-machine GitHub SSH keys. Stage `./scripts/linux_secret_service.py` for terminal-only Linux Secret Service creation, unlock, or accidental-newline repair. Stage `./scripts/macos_gh_keychain.py` when an existing valid Mac OAuth session falls back to plaintext because its exact `gh` Keychain records are incomplete or stale. Keep OAuth/API login and SSH Git transport as separate acceptance gates.

Read `./references/google-workspace-cli-authentication.md` before installing, authenticating, reauthorizing, or repairing `gws` on any machine. Its complete everyday service grant is the single source of truth. Never substitute a narrower login in a role-specific onboarding document.

Read `./references/machine-local-secrets.md`, then `./references/machine-local-secrets-and-enrollment.md`. Treat `./fleet/machine-secrets.json` as the non-secret ownership and procedure registry, and `./internal/generated/state/machine-secrets.lock.json` as sanitized confirmed state only. Enroll the per-machine ctx9 GitLab group-read credential before any workspace installer needs private packages. Use each credential's owning script; do not improvise copies or turn provider/service secrets into fleet-machine secrets.

For independent CodeFolderSync backup recovery identities, read `./references/codefoldersync-backup-age-recovery.md` and use `./scripts/codefoldersync_backup_age.py`. Existing identity presence is unverified state, not permission to replace it.

Unattended worker Mac setup and acceptance must follow `./references/worker-mac-power-and-sleep.md` and prove a new inbound connection over the explicit selected-provider `-mesh` alias while the lid is closed. Secondary Macs instead follow their normal sleep and manual-unlock acceptance; closed-lid availability is excluded. Do not accept `pmset sleep 0`, a running Amphetamine process, outbound-only traffic, or a VPN Connected label as equivalent evidence for an unattended worker. Never add a custom sleep service without explicit user approval after native Amphetamine/Power Protect failure evidence.

After that approval, use `./scripts/manage_worker_mac_sleep_service.py` for preview-first installation, verification, or removal of the one managed `caffeinate -s` LaunchAgent. Do not improvise a second sleep service.

1. Read `./references/shared-onboarding-and-acceptance.md` and keep every applicable gate visible until verified or explicitly excluded.
2. Route by role and convention: `./references/primary-mac-onboarding-and-acceptance.md`, `./references/secondary-mac-onboarding-and-acceptance.md`, `./references/worker-mac-onboarding-and-acceptance.md` for unattended Mac workers, or `./references/linux-worker-onboarding-and-acceptance.md`.
3. For optional full Vault access on a Linux worker whose schema-v7 registry mode is `remote-sshfs`, read `./references/linux-remote-vault-access.md` after fleet-shell mesh acceptance and before final enablement. Do not improvise a clone, sparse checkout, broader home mount, or separate skill.
4. Keep the registry entry disabled until the selected role document's reboot acceptance passes.
5. Use `$fleet-i-sync-code-workspaces` during onboarding for Code repositories and primary-owned Codex and Claude configuration. Do not recreate that sync here.
6. Use `$fleet-i-manage-terminal-workspaces` for terminal packages, profiles, Warp, cmux, tmux, workmux, and terminal acceptance.
7. Use `$code-i-use-claude-code-proxy-or-openrouter` for every Claude provider launcher, installer, API-key route, CLIProxyAPI route, and provider acceptance. Do not keep launcher copies or provider SOPs here.
8. Use `./references/sops-key-enrollment-and-rotation.md` only when an owning repository requires shared SOPS access.
9. On Linux workers, install user-approved optional daemons or watchdogs only through [Linux Worker Optional Daemons And Watchdogs](references/linux-worker-onboarding-and-acceptance.md#optional-daemons-and-watchdogs). Keep the registered set explicit, preview first, and verify the exact target after apply.

Use `./scripts/render_ssh_access.py` through `fleet machine access render`; it renders each enabled source machine with its own fleet-shell identity and every target's selected provider. Use `fleet machine access configure` and `switch` for previewed provider changes with fleet-wide rendering and rollback. Store non-secret provider desired state in the Git-backed private registry and keep credentials machine-local.

When an already trusted OpenSSH server gains a new provider hostname, verify the server's SHA-256 host-key fingerprint locally, then use `./scripts/trust_known_host_alias.py` on the connecting machine to copy the exact existing trusted key to the new hostname. Preview first, apply, verify, and require `StrictHostKeyChecking=yes`; never substitute `ssh-keyscan`, `accept-new`, or disabled host verification for identity proof.

Use `./scripts/fleet_shell_access.py` for protected target-local fleet-shell key provisioning and source-specific managed `authorized_keys` enrollment. Public-key enrollment requires an approved fingerprint; private keys and passphrases never leave their source machine.

Preview every supported mutation first. Never transmit machine-local credentials. Stop at the exact manual checkpoint for identity choice, GUI approval, authentication, physical access, or separately authorized destructive work, then resume the same procedure after the user completes it.
