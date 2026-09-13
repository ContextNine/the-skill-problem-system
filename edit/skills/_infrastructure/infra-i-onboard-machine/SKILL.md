---
name: infra-i-onboard-machine
description: Onboards, rebuilds, replaces, recovers, or accepts a Mac or Linux machine as a complete fleet member. Use when the user asks to set up a new primary Mac, add a worker Mac, add a Linux worker, rebuild or replace a machine, enroll it in fleet access, or finish machine acceptance.
---

# Infra · Onboard Machine

Read `$infra-i-code-folder-and-computer-topology`, its role model, private config README, registries, and the selected machine convention before operating.

Collect and validate the machine's absolute home plus user-selected Code and Vault roots during registration. Store Code and Vault roots in `fleet/machines.json`, store workspace paths relative to Code root, and verify them through `fleet config validate` before any sync. Vault participation is an explicit registry choice, not an operating-system inference. Standalone agent-package installation, generated global instructions, Claude alias and discovery aliases are separate opt-ins; do not make any of them a prerequisite for a working Vault.

Read [[machine-access-selection|Machine Access Selection]], then exactly one provider route: [[wireguard-machine-access|WireGuard Machine Access]] or [[tailscale-machine-access|Tailscale Machine Access]]. Neither provider is the default. Keep the registry's canonical SSH alias as the durable identity; use `-lan` and `-mesh` only for diagnosis.

Read [[fleet-shell-mesh|Fleet Shell Mesh]] when provisioning or verifying machine-to-machine SSH. Enabled personal machines use full-mesh regular OpenSSH over Tailscale, one unique dedicated fleet-shell identity per source machine, exact host-key pinning, and all-to-all public-key authorization. Keep disabled machines excluded and keep GitHub keys separate.

For Tailscale, use `scripts/setup_tailscale_access.py` for preview-first official installation, non-secret desired-state application, sanitized status, and the exact unavoidable authentication or macOS approval checkpoint. Do not replace it with improvised install commands.

Read [[README-github-fleet-authentication|GitHub Fleet Authentication]]. Use `scripts/github_fleet_auth.py` for dedicated per-machine GitHub SSH keys. Stage `scripts/linux_secret_service.py` for terminal-only Linux Secret Service creation, unlock, or accidental-newline repair. Stage `scripts/macos_gh_keychain.py` when an existing valid Mac OAuth session falls back to plaintext because its exact `gh` Keychain records are incomplete or stale. Keep OAuth/API login and SSH Git transport as separate acceptance gates.

Read [[_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/references/machine-local-secrets|Machine-local Secrets]], then [[machine-local-secrets-and-enrollment|Machine-local Secrets and Enrollment]]. Treat `_system/agents/edit/settings/fleet/machine-secrets.json` as the non-secret ownership and procedure registry, and `_system/agents/internal/generated/state/machine-secrets.lock.json` as sanitized confirmed state only. Enroll the per-machine ctx9 GitLab group-read credential before any workspace installer needs private packages. Use each credential's owning script; do not improvise copies or turn provider/service secrets into fleet-machine secrets.

For independent CodeFolderSync backup recovery identities, read [[codefoldersync-backup-age-recovery|CodeFolderSync Backup Age Recovery]] and use `scripts/codefoldersync_backup_age.py`. Existing identity presence is unverified state, not permission to replace it.

Worker Mac setup and acceptance must follow [[worker-mac-power-and-sleep|Worker Mac Power and Sleep]] and prove a new inbound connection over the explicit selected-provider `-mesh` alias while the lid is closed. Do not accept `pmset sleep 0`, a running Amphetamine process, outbound-only traffic, or a VPN Connected label as equivalent evidence. Never add a custom sleep service without explicit user approval after native Amphetamine/Power Protect failure evidence.

After that approval, use `scripts/manage_worker_mac_sleep_service.py` for preview-first installation, verification, or removal of the one managed `caffeinate -s` LaunchAgent. Do not improvise a second sleep service.

1. Read [[shared-onboarding-and-acceptance|Shared Onboarding and Acceptance]] and keep every applicable gate visible until verified or explicitly excluded.
2. Route by role: [[primary-mac-onboarding-and-acceptance|Primary Mac]], [[worker-mac-onboarding-and-acceptance|Worker Mac]], or [[linux-worker-onboarding-and-acceptance|Linux Worker]].
3. For optional full Vault access on a Linux worker whose schema-v7 registry mode is `remote-sshfs`, read [[linux-remote-vault-access|Linux Remote Vault Access]] after fleet-shell mesh acceptance and before final enablement. Do not improvise a clone, sparse checkout, broader home mount, or separate skill.
4. Keep the registry entry disabled until the selected role document's reboot acceptance passes.
5. Use `$infra-i-sync-code-workspaces` during onboarding for Code repositories and primary-owned Codex and Claude configuration. Do not recreate that sync here.
6. Use `$infra-i-manage-fleet-terminal-workspaces` for terminal packages, profiles, Warp, cmux, tmux, workmux, and terminal acceptance.
7. Use `$infra-i-manage-claude-provider-routes` for every Claude provider launcher, installer, API-key route, CLIProxyAPI route, and provider acceptance. Do not keep launcher copies or provider SOPs here.
8. Use [[sops-key-enrollment-and-rotation|SOPS Key Enrollment and Rotation]] only when an owning repository requires shared SOPS access.
9. On Linux workers, install user-approved optional daemons or watchdogs only through [[linux-worker-onboarding-and-acceptance#Optional daemons and watchdogs|Linux Worker Optional Daemons And Watchdogs]]. Keep the registered set explicit, preview first, and verify the exact target after apply.

Use `scripts/render_ssh_access.py` through `vault machine access render`; it renders each enabled source machine with its own fleet-shell identity and every target's selected provider. Use `vault machine access configure` and `switch` for previewed provider changes with fleet-wide rendering and rollback. Store non-secret provider desired state in the Git-backed private registry and keep credentials machine-local.

When an already trusted OpenSSH server gains a new provider hostname, verify the server's SHA-256 host-key fingerprint locally, then use `scripts/trust_known_host_alias.py` on the connecting machine to copy the exact existing trusted key to the new hostname. Preview first, apply, verify, and require `StrictHostKeyChecking=yes`; never substitute `ssh-keyscan`, `accept-new`, or disabled host verification for identity proof.

Use `scripts/fleet_shell_access.py` for protected target-local fleet-shell key provisioning and source-specific managed `authorized_keys` enrollment. Public-key enrollment requires an approved fingerprint; private keys and passphrases never leave their source machine.

Preview every supported mutation first. Never transmit machine-local credentials. Stop at the exact manual checkpoint for identity choice, GUI approval, authentication, physical access, or separately authorized destructive work, then resume the same procedure after the user completes it.
