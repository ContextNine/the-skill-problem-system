---
type: agent-reference
status: enabled
---

## Worker Mac onboarding and acceptance

Read [[shared-onboarding-and-acceptance|Shared Onboarding and Acceptance]] first. This route owns the Screen-Sharing-first macOS procedure, worker bootstrap script, GUI consent, unattended operating baseline, iCloud Vault boundary, and reboot acceptance.

Read the private `Machine Conventions/Worker Mac/Worker Mac.md` note for Matt-specific application and account choices. Keep changing personal choices there rather than duplicating them here.

### Layered bootstrap

An active native Screen Sharing connection from the registered primary Mac is the only user-prepared prerequisite. Once connected, the primary-host agent owns the rest of the bootstrap through Screen Sharing and then SSH. It may hand control back briefly at a macOS password, Touch ID, MFA, CAPTCHA, device-approval, or other prompt that cannot safely be delegated, but the user does not need to run setup commands or prepare SSH first.

[Migration Assistant](https://support.apple.com/en-us/102613) is optional. When it works, use it as a broad compatibility and data-recovery layer before this bootstrap; keep the source Mac unchanged and backed up until acceptance passes. When it does not work, continue as a clean setup. Migrated authentication, VPN identities, system extensions, background services, and applications remain unverified until this workflow accepts them.

This is the worker-Mac branch of `$infra-i-onboard-machine`. `$infra-i-manage-fleet-terminal-workspaces` owns Warp, cmux, terminal profiles, workmux, and T3 SSH terminal integration. `$infra-i-sync-code-workspaces` owns Code repositories and personal Codex and Claude configuration. Do not duplicate those procedures here.

### 1. Screen Sharing handoff and agent-owned first pass

The user connects from the registered primary with Apple's native Screen Sharing app and tells the primary-host agent the session is ready. That is the entire manual first pass. Do not require the user to establish SSH, install dependencies, choose fleet identity, or run commands.

The primary-host agent then uses Screen Sharing to:

1. Inspect the actual target account, macOS version, architecture, Computer Name, host name, LAN address, and existing applications. Use these facts to propose the unique fleet identity; do not invent values.
2. Install macOS updates and assign the reviewed unique Computer Name and host name. Do not leave a name copied from another Mac.
3. Turn off FileVault, wait for decryption to finish, then enable automatic login for the operator account through the macOS UI. Apple documents the security trade-off and the FileVault restriction in [Automatically log in to your Mac user account](https://support.apple.com/en-us/102316). Never request, store, type, transmit, or log the account password; hand the live prompt to the user when macOS requires it.
4. In System Settings → Privacy & Security → Advanced, ensure automatic logout after inactivity is off. Then open System Settings → Lock Screen and set **Require password after screen saver begins or display is turned off** to **Never**. Screen locking, automatic logout, and system sleep are three independent controls: changing any one does not configure or prove the others. Verify `/usr/sbin/sysadminctl -screenLock status` reports exactly that `screenLock is off`; `screenLock delay is 0 seconds` means an immediate password requirement and must not be accepted as disabled. The worker must retain its unlocked, logged-in session unless a person deliberately locks or logs it out.
5. In System Settings → General → Sharing, ensure Screen Sharing and Remote Login allow only the operator account. Do not enable Remote Management at the same time. Follow [Turn Mac screen sharing on or off](https://support.apple.com/guide/mac-help/turn-screen-sharing-on-or-off-mh11848/mac).
6. Through a target Terminal opened in Screen Sharing, add only the registered primary Mac's reviewed fleet public SSH key. Never copy a private SSH key or password to the worker.
7. Configure the unattended power baseline before installing dependencies:

```bash
sudo pmset -a sleep 0
sudo pmset -a womp 1 autorestart 1
pmset -g custom
```

System sleep must remain disabled on both battery and AC power so the worker stays reachable after it is unplugged or changes power source. Keep display sleep enabled; turning off the display must not suspend the Mac. Enable wake for network access and automatic restart after power loss. `pmset sleep 0` does not override clamshell sleep and cannot by itself prove closed-lid availability. Apple describes the corresponding controls in [Set sleep and wake settings](https://support.apple.com/guide/mac-help/mchlp1168/mac) and [Wake your Mac for network access](https://support.apple.com/guide/mac-help/mh27905/mac).

8. Install Xcode Command Line Tools and finish its GUI installer when missing. Install Homebrew from [brew.sh](https://brew.sh) when missing.
9. From the primary Mac, verify the reviewed LAN SSH route and retain the native Screen Sharing fallback. Continue the rest of the workflow over SSH whenever practical.

The agent resumes automatically after any necessary user interaction. A password or protected approval prompt is a brief authentication handoff, not a new checklist or a request for permission. Required role work—including the unattended power/startup baseline, macFUSE installation when present in the shared dependency set, and unique enrollment in the explicitly selected personal machine-access provider—must begin and continue without asking whether the user wants it performed. State the exact live prompt, hand control over only while macOS requires the user to type a password or approve a protected System Settings prompt, then continue automatically.

### 2. Register and seed from the primary

Invoke the topology skill from the primary Vault clone. The agent must verify the clone-local machine ID is the registry primary, create the private machine note, configure the reviewed LAN, selected `-mesh`, and canonical aliases through [[machine-access-selection|Machine Access Selection]], and add a complete but disabled macOS worker entry before provisioning. Set `vault_sync.enabled: true`, `checkout: icloud`, and `repo_path` to the target's iCloud Vault folder. Do not define `git_dir`. Keep top-level `enabled: false`. Commit and push the reviewed registry, machine note, and startup opt-in on the primary before finish so iCloud can deliver the reviewed files to the target.

Use [[bootstrap_worker_mac.py]] from the primary:

```bash
python3 "$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/bootstrap_worker_mac.py" status MACHINE_ID
python3 "$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/bootstrap_worker_mac.py" seed MACHINE_ID
python3 "$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/bootstrap_worker_mac.py" seed MACHINE_ID
```

The dry run is the default. Seed verifies the exact disabled macOS worker over its `-lan` alias, preserves qualifying migrated applications, and installs or validates Git, Git LFS, GitHub CLI, Bitwarden, Google Chrome, ChatGPT desktop, and Codex CLI once Command Line Tools and Homebrew exist. Seed does not edit Codex or Claude settings. After authentication, `$infra-i-sync-code-workspaces` applies the single [[agent-configuration-sync|Fleet Agent Configuration Sync]] contract, including the required worker-Mac policy overlay; final verification rejects any weaker state. Chrome, ChatGPT desktop, and Codex CLI are pre-authentication requirements, not deferred finish-phase extras. Through Screen Sharing, make Chrome the macOS default browser and verify that Launch Services assigns both `http` and `https` to `com.google.chrome`; a stale Chrome settings label is not verification.

Complete [[worker-mac-power-and-sleep|Worker Mac Power and Sleep]]. Installation, Power Protect on Apple silicon, login launch, the stored closed-display policy, a fresh indefinite session, native sleep-prevention evidence, and post-reboot inbound acceptance are separate gates.

### 3. Target-local authentication checkpoint

Use Screen Sharing to complete these steps on the worker Mac:

```bash
gh auth login --hostname github.com --git-protocol ssh --skip-ssh-key --web
gh config set git_protocol ssh --host github.com
gh auth status --hostname github.com
gh api user --jq .login
```

Then return to Primary machine and use the preview-first enrollment workflow in [[README-github-fleet-authentication|GitHub Fleet Authentication]]. The target generates and retains `~/.ssh/id_ed25519_github_<machine-id>`; Matt separately approves only its public fingerprint. Screen Sharing is permitted for this initial OAuth checkpoint, never for routine workspace sync.

Account and provider selection is always a user action. A macOS account name, autofilled address, browser session, Bitwarden entry, or saved-account suggestion is not proof of which identity should be used. The agent must stop before selecting, typing, or submitting an account and ask the user to perform the login unless the exact mapping is explicitly documented and still confirmed. Never click a saved suggestion speculatively.

Sign in to and unlock Bitwarden. Ask the user to sign Chrome into the intended Google profile, then make Chrome the default browser. For Codex, run `codex login --device-auth`, open the device page, then stop and ask the user to complete **Continue with Google** and choose the correct Google account. Verify `codex login status` afterward. Open ChatGPT and again ask the user to complete **Continue with Google**; do not assume that a saved OpenAI email or browser suggestion is the intended account. Complete MFA, device approval, CAPTCHA, macOS privacy prompts, and other sensitive actions yourself.

After fleet development sync changes Codex config, quit and reopen Codex desktop. Computer Use cannot approve the macOS privacy dialog that grants its own control, so stop at that exact dialog and tell the user to click **Allow**. If macOS requests it, the user must enable **Codex Computer Use** under System Settings → Privacy & Security → Accessibility and System Settings → Privacy & Security → Screen & System Audio Recording. In Codex Settings → Computer Use, the user must also enable **Locked use** and approve the Apple authorization plug-in or administrator prompt. Locked use is a separate mandatory gate for this unattended worker role; neither `screenLock is off` nor a successful unlocked-session Computer Use test proves that Codex can operate after native Screen Sharing disconnects. Restart Codex after all grants. Verify the helper against a harmless application outside Codex while unlocked, disconnect Screen Sharing, independently confirm macOS reports the console locked, and verify a new scoped Computer Use turn still succeeds. Follow [OpenAI Computer Use · Locked use](https://learn.chatgpt.com/docs/computer-use#locked-use). Neither installation nor a running helper process proves that the bridge, TCC permissions, authorization plug-in, and locked-use path work.

The bootstrap verifies OAuth API access, `gh` SSH protocol, dedicated GitHub SSH authentication, and the absence of plaintext `oauth_token`; Codex and ChatGPT sessions remain machine-local. A remote shell may omit the GUI launchd agent socket and Homebrew path even while the logged-in macOS session has both. The fleet-auth helper must first discover `com.openssh.ssh-agent` through the user's GUI launchd domain and use the registered noninteractive PATH. Therefore, do not conclude that OAuth is invalid or start a replacement login solely from an uncorrected SSH environment. Run the installed `vault-worker-auth-attest` helper in the worker's target-local Terminal or through a reviewed ephemeral per-user LaunchAgent only when Keychain access still cannot be proven after correcting that environment. The LaunchAgent route is CLI-only and must not open Screen Sharing. It records only machine ID, boolean results, and time, never an account, token, key, or secret. Dedicated Git SSH must still pass the exact noninteractive fleet-auth verification after login and reboot.

Tell the primary-host agent that GitHub OAuth, Codex, Chrome, ChatGPT, and Bitwarden are ready. This is the second deliberate pause. Do not manually clone the vault.

### 4. Full iCloud vault and deterministic finish

On the worker Mac, sign in to iCloud Drive and wait for the Vault folder to appear at the registered path. In Finder, right-click the Vault folder, choose **Keep Downloaded**, then choose **Download Now** whenever the folder is not fully materialized. **Keep Downloaded** retains local content; **Download Now** starts or retries the current materialization. Do not continue while Finder shows pending downloads or while this command finds a placeholder:

```bash
find "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault" -flags +dataless -print -quit
```

The synced `.git` file is owned by the primary's iCloud worktree and therefore appears on workers too. Its absolute target must not exist on a worker, so the pointer is deliberately dangling and Git cannot treat the worker Vault as a repository. Never create a fallback `<resolved Code root>/vault`. Bootstrap moves only the expected legacy worker target `~/.local/share/vault-git/Vault.git` recoverably to `~/.Trash`; an unexpected existing pointer target is a stop condition.

From the primary, preview and apply:

```bash
python3 "$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/bootstrap_worker_mac.py" finish MACHINE_ID
python3 "$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/bootstrap_worker_mac.py" finish MACHINE_ID
```

Bootstrap does not initialize, fetch, index, check out, reset, or configure Vault Git. It verifies full iCloud materialization, retires only the expected legacy Git target to Trash when present, writes mode-`0600` machine identity to `~/.config/vault/machine-id`, updates links and skills, writes the persistent worker refresh block, and unregisters any refresh LaunchAgent. GitHub authentication remains useful for ordinary code repositories but is not used to bootstrap the Vault on a worker.

Finish explicitly provisions the disabled worker with `vault worker-sync bootstrap MACHINE_ID --provision-disabled`, runs the shared macOS dependency installer from the iCloud vault, revalidates ChatGPT, Chrome, Bitwarden, and Codex CLI, and installs or validates Node/npm, Git, Homebrew tools, and the architecture-matching latest T3 Code Nightly. Correctly signed existing applications are preserved rather than overwritten. T3 requires the GitHub asset SHA-256, bundle ID `com.t3tools.t3code`, Apple assessment, and signing Team ID `ARK85ZXQ4Z`, with same-volume rollback on replacement failure.

Git LFS bodies are not available from GitHub for this private Vault. Worker media arrives only through iCloud. Do not copy the primary's `~/.local/share/vault-git/Vault.git/lfs`, run Vault Git or `git lfs pull`, create a worker LFS cache for the Vault, or place Git metadata in iCloud. Never prune the primary cache without another verified media backup.

Before finish, add the disabled machine's opt-in under the private [[Mac Startup]] config:

```json
{
  "enabled": true,
  "actions": {
    "open-applications": true,
    "remap-tilde-key": false
  },
  "applications": [
    "com.bitwarden.desktop"
  ],
  "legacy_launch_agents": []
}
```

Managed startup opens only Bitwarden. Keep its own vault-lock policy enabled. The selected machine-access provider owns its supported native startup mechanism. For other applications, leave “Reopen windows when logging back in” selected when restarting or logging out; see [Reopen apps and windows on Mac](https://support.apple.com/en-us/102318). ChatGPT, Chrome, and T3 are not forced login items.

### 5. Personal machine access and fleet integration

Follow [[machine-access-selection|Machine Access Selection]], then the selected [[wireguard-machine-access|WireGuard Machine Access]] or [[tailscale-machine-access|Tailscale Machine Access]] route. Treat migrated provider identities as unverified; never reuse another machine's identity. Authentication, account selection, and protected VPN approval remain user checkpoints.

After the explicit `MACHINE_ID-mesh` and canonical routes work, render source-aware SSH access across the enabled fleet. On the worker, require `ssh -G PRIMARY_ID` to show the primary target's selected provider host, the worker's fleet-shell identity, `batchmode yes`, and password plus keyboard-interactive authentication disabled. Start a fresh canonical reverse tunnel to `PRIMARY_ID`, prove the primary-loopback listener reaches the worker-loopback target, close the tunnel, and prove the listener disappears.

Then complete every applicable gate from [[shared-onboarding-and-acceptance|Shared Onboarding and Acceptance]]: route-specific and automatic SSH, native Screen Sharing registry entry, Warp and cmux workspaces, terminal profile, T3 Code SSH-launch environment, Codex/ChatGPT computer-use permissions, agent configuration, topology records, and intentionally excluded items. Provision and verify the terminal profile while the registry entry remains disabled with `sync_terminal_profiles.py --target MACHINE_ID --provision-disabled --apply` and then `--verify`; enable the registry only after the rest of acceptance passes.

### 6. Reboot acceptance and enablement

Restart while “Reopen windows when logging back in” is selected. Do not enable the registry entry until the Mac returns without local intervention and all checks pass:

```bash
python3 "$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/bootstrap_worker_mac.py" verify MACHINE_ID --json
```

Acceptance requires automatic login to the exact operator account with FileVault off; automatic logout disabled; `sysadminctl` reporting `screenLock is off`; the complete [[worker-mac-power-and-sleep|Worker Mac Power and Sleep]] gate; wake-on-network and restart-after-power-loss enabled; selected-provider native startup, reconnection, and direct/relay or handshake evidence; Bitwarden running; Chrome registered as the default HTTP/HTTPS browser; previous windows restored by macOS; source-aware `-lan`, `-mesh`, and canonical SSH aliases; a passwordless reverse tunnel to the canonical primary alias; Screen Sharing; Homebrew/Git/GitHub/Node/npm/Codex and signed application checks; target-local GitHub and Codex authentication; root Codex policy set to `never` approvals and `danger-full-access`; Computer Use bridge enabled with working Accessibility and Screen & System Audio Recording grants; **Locked use** enabled with its Apple authorization plug-in; a successful scoped Computer Use action after Screen Sharing disconnects while macOS independently reports the console locked; a fully downloaded iCloud Vault; correct `~/.config/vault/machine-id`; a dangling shared `.git` pointer; failed Vault Git resolution; no `<resolved Code root>/vault`; clean skill sync; an unloaded and worker-ineligible refresh schedule; and the generic Warp/cmux/T3 gates. A running app process, outbound-only traffic, a VPN Connected label, or an unlocked-session smoke test is never sufficient. Reboot, close the lid, wait past former thresholds, then prove a fresh inbound `MACHINE_ID-mesh` connection before the canonical alias and confirm no new system-sleep or provider-suspension event. Disconnect Screen Sharing, prove the locked-use path, then reconnect and confirm SSH and Screen Sharing still work. Record evidence and exclusions in the private machine note, then set `enabled: true`. If a post-enable check fails, disable the entry again and leave the exact next manual action visible.

After acceptance, follow [[Vault Git Sync#Worktree coordination|Worktree coordination]]. The worker edits its local iCloud Vault normally without waiting for outbound upload. The primary alone reviews, commits, and pushes changes visible in its worktree.
