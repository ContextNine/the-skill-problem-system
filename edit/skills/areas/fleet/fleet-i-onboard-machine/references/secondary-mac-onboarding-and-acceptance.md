---
type: agent-reference
status: enabled
---

## Secondary Mac onboarding and acceptance

A secondary Mac is an additional Mac the user works on physically, with fleet access when it is awake. Register it as `role: worker`, `platform: macos`, with `template_variants: [macos, workermac]`. Keep the existing primary and Vault Git owner. “Register a secondary Mac” selects this convention without another question about sleep or locking.

Read `./shared-onboarding-and-acceptance.md` and `./private/Machine Conventions/Secondary Mac/Secondary Mac.md`, relative to the topology config directory identified by `$fleet-i-code-folder-and-computer-topology`. Record the convention in the new machine's private note so rebuilds and later maintenance retain it. Do not add a new registry role or undocumented schema fields.

### First response and user preparation

Give the user these steps before attempting access to a fresh Mac:

1. Finish Apple's initial macOS setup, create the intended local account, and connect the Mac to the same network as the primary.
2. Enable Screen Sharing under System Settings → General → Sharing, allowing only the intended account. Leave Remote Management off.
3. From the primary, open Apple's Screen Sharing app and connect to the new Mac. Tell the primary-host agent when the session is ready.
4. Stay available to select accounts, enter passwords, complete MFA, and approve protected macOS prompts during installation.

Explain that Codex, Tailscale, WireGuard, Homebrew, SSH keys, and fleet commands need not be installed beforehand. The agent starts through native Screen Sharing, establishes trusted SSH, then uses SSH for remote commands. If the Macs cannot share a network, establish a reviewed access route first; do not assume an unconfigured VPN is reachable.

### Operating policy

- Keep FileVault enabled. If it is off, help the user enable it through macOS and its protected prompts. Recovery credentials remain in the approved machine-local custody workflow.
- Keep automatic login off and require a password after locking or display sleep. Preserve ordinary user-selected locking and timeout settings; do not set the password requirement to Never.
- Keep normal system and display sleep on battery and AC. Allow normal lid-close sleep. Do not run the unattended `pmset sleep 0` baseline, install a sleep-prevention service, or configure Amphetamine to maintain an indefinite session or prevent lid-close sleep.
- A sleeping Mac is expected to be unreachable. GUI work may require the user to unlock the session; a locked screen alone does not imply SSH has stopped. Ask for a wake or unlock when needed rather than repairing an expected offline state.
- Reboot acceptance permits the user to unlock FileVault and log in physically. Unattended return after restart, closed-lid reachability, and Computer Use Locked use are excluded unless separately requested.
- Run local coding apps normally. Registered Code repositories keep independent Git checkouts. The iCloud Vault remains fully downloaded and Gitless on this Mac; only the registered Vault Git owner commits and pushes Vault changes.

### Agent-owned onboarding

Reuse the installation, authentication, iCloud, and access procedures in `./worker-mac-onboarding-and-acceptance.md` subject to the policy above. Read its first-pass steps selectively: inspect the target, assign a unique reviewed name, enable account-scoped Screen Sharing and Remote Login, enroll the primary's public SSH key, install Command Line Tools and Homebrew, and verify LAN SSH. Skip its FileVault-off, automatic-login, unlocked-session, and unattended-power instructions.

1. Register the unique machine, actual home, selected Code and Vault roots, canonical SSH alias, terminal profile, and private note from the primary. Keep `enabled: false` until acceptance. For Vault participation use schema-v7 `vault.enabled: true`, `vault.checkout_mode: icloud-gitless`, and `roots.vault`; never define worker Vault Git metadata.
2. Preview and apply the existing bootstrap script's `seed` phase after SSH and Homebrew are ready. Use `../scripts/bootstrap_worker_mac.py` from this reference directory; mutations require `--apply`. Follow its target-local account and dedicated GitHub SSH enrollment checkpoints without copying credentials or sessions.
3. Follow `./machine-access-selection.md` and the selected provider route. Use the private Secondary Mac convention for personal provider and cluster-access choices. Complete `./fleet-shell-mesh.md` while the Mac is awake.
4. Sign in to iCloud Drive, select Keep Downloaded and Download Now for the full Vault, and verify materialization. Preview and apply the bootstrap `finish` phase for Gitless Vault setup, dependencies, Fleet runtime, and reviewed Bitwarden startup. This phase installs software; it does not grant unattended acceptance.
5. Use `$fleet-i-sync-code-workspaces` for repositories and managed Codex/Claude configuration and `$fleet-i-manage-terminal-workspaces` for terminal setup. Complete applicable shared authentication, coding-app, startup, and skill gates. Computer Use permissions apply when that capability is selected; Locked use is optional for this convention.

The current `bootstrap_worker_mac.py verify` and `target-verify` aggregate checks enforce FileVault off, automatic login, disabled locking, and sleep prevention. Do not use their pass/fail result for secondary-Mac acceptance or change the Mac to satisfy them. Use the checks below and record evidence in the private machine note. The unattended verifier remains specific to unattended workers.

### Secondary Mac acceptance

1. Verify `fdesetup status` reports FileVault on, automatic login is off, password locking is enabled, and `pmset -g custom` plus the macOS UI retain normal sleep. Check `pmset -g assertions` for persistent sleep prevention introduced by onboarding.
2. Reboot, have the user unlock FileVault and log in, then verify installed tools, target-local authentication, selected-provider reconnection, strict SSH through canonical and diagnostic aliases, Screen Sharing, the fleet-shell matrix, and the shared reverse-forward proof while awake.
3. Verify workspace doctor, terminal setup, skills and managed agent configuration, approved startup, and the full local iCloud Vault. Confirm the shared `.git` pointer does not resolve, no separate Vault checkout exists, and the worker refresh schedule remains blocked.
4. Have the user lock the screen and confirm a password is required. Have them close the lid or use normal sleep, then wake and unlock the Mac. Confirm normal sleep occurred and fleet access reconnects afterward; do not require access during sleep.
5. Record passed gates and the deliberate exclusions for unattended reboot, sleep-time availability, and Locked use. Enable the entry only after applicable checks pass. A later expected sleep state is not a reason to disable the machine or change its power policy.
