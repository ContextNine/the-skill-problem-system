---
type: agent-reference
status: enabled
---

## Linux worker onboarding and acceptance

Read [Shared Onboarding and Acceptance](shared-onboarding-and-acceptance.md) first. Use this route from the registered primary when enrolling a new or rebuilt Linux development worker.

Prerequisites:

- [Primary Machine Remote Access Prerequisites](primary-mac-remote-access-prerequisites.md) passes.
- `$infra-i-code-folder-and-computer-topology` supplies current fleet and network facts.
- Resolve `codex-machine-image` through topology repository config and read its owning setup docs. Resolve `k3s-infrastructure` only when the selected WireGuard route uses its private enrollment adapter.
- Linux Worker Image owns Linux command profiles; the image repository's `image.lock` owns boot-critical versions.
- `$infra-i-sync-code-workspaces` owns Code repositories and personal Codex and Claude configuration.
- `$infra-i-manage-fleet-terminal-workspaces` owns terminal profiles and final Warp/cmux layout.

Current server image supports Ubuntu Server 26.04 AMD64 only. Stop on ARM or an unknown target disk. Disk erasure requires the user's explicit authorization and exact target verification.

## 1. Record run variables

Choose before mutation:

```text
FRIENDLY_NAME=<human name, for example Linux worker>
WORKER_ID=<private registry machine ID, for example linux-worker>
SSH_ALIAS=<lower-kebab alias, for example linux-worker>
TARGET_DISK=<verified internal disk>
BONJOUR_HOST=<discovered codex-....local>
LAN_IP=<reserved home address>
MESH_HOST=<selected WireGuard address or Tailscale MagicDNS FQDN>
```

Select `wireguard` or `tailscale` through [Machine Access Selection](machine-access-selection.md). Do not reuse an old machine alias or provider identity until the old device is deliberately retired.

## 2. Install operating system

1. Connect wired DHCP when possible. Insert approved USB.
2. Boot USB through UEFI selector or Intel Mac Option menu.
3. Keep username `ctx9`. Enter local console password on identity screen.
4. On storage screen, verify `TARGET_DISK`, then confirm wipe.
5. Wait for installer power-off. Remove USB. Boot internal disk.
6. If installed offline, configure locally:

```bash
sudo codex-wifi-setup
```

First boot generates the machine ID and hostname. When WireGuard is selected and the image's enrollment adapter is enabled, it also generates the target-local WireGuard identity and enrollment request; `codex-machine-enroll.timer` retries until success and deletes the installed enrollment token. When Tailscale is selected, keep WireGuard enrollment disabled and follow [Tailscale Machine Access](tailscale-machine-access.md) after base networking and SSH work.

## 3. Discover and reach machine

On Primary machine:

```bash
dns-sd -B _ssh._tcp local.
ssh -i ~/.ssh/codex_fleet_ed25519 ctx9@codex-<machine-id-prefix>.local
```

Stop if host key, username, or target identity differs from expected new machine.

On remote:

```bash
hostnamectl
cat /etc/codex-machine-image-version
systemctl status codex-machine-enroll.timer --no-pager || true
sudo systemctl status codex-machine-enroll.service --no-pager || true
ip -4 address show
ip route
resolvectl query kubernetes.default.svc.cluster.local
```

If selected WireGuard enrollment still runs, inspect its service journal and fix network before continuing:

```bash
sudo journalctl -u codex-machine-enroll.service -b --no-pager
sudo systemctl start codex-machine-enroll.service
```

Acceptance: `wg0` has recent handshake, `10.13.13.1` responds, cluster DNS resolves, enrollment marker exists, token no longer exists.

```bash
ping -c 2 10.13.13.1
sudo test -e /var/lib/codex-machine-image/enrolled
sudo test ! -e /var/lib/codex-machine-image/enrollment-token
```

## 4. Set friendly name and stabilize LAN address

Keep generated static hostname. Set pretty name only:

```bash
sudo hostnamectl set-hostname "FRIENDLY_NAME" --pretty
hostnamectl
```

Read current Ethernet/Wi-Fi MAC and LAN address:

```bash
ip -brief link
ip -4 route get 1.1.1.1
```

Create home-router DHCP reservation for chosen `LAN_IP`. Alias reliability depends on stable lease. Reconnect and confirm reserved address before writing Primary machine alias.

## 5. Install dependency profiles

Image owns `image_core`; do not replace its pinned Codex, Node, or T3 versions ad hoc. Install `remote_development` and normal `vault_operator` profile.

`btop` in this profile is a Linux-machine requirement. Do not infer a macOS requirement from this runbook; use built-in `top` or Activity Monitor when macOS package support is poor.

### System packages and GitHub CLI

GitHub maintains separate APT repository; do not rely on Ubuntu community `gh` package.

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential btop ca-certificates curl fd-find fzf git git-lfs gnupg jq \
  gnome-keyring libsecret-tools pinentry-gnome3 pkg-config python3 python3-dbus python3-venv \
  rclone ripgrep rsync seahorse tmux unzip wget xz-utils zip zstd

sudo install -d -m 0755 /etc/apt/keyrings
tmp_keyring=$(mktemp)
wget -nv -O "$tmp_keyring" https://cli.github.com/packages/githubcli-archive-keyring.gpg
sudo install -m 0644 "$tmp_keyring" /etc/apt/keyrings/githubcli-archive-keyring.gpg
rm -f "$tmp_keyring"
sudo install -d -m 0755 /etc/apt/sources.list.d
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' "$(dpkg --print-architecture)" \
  | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
sudo apt-get update
sudo apt-get install -y gh

mkdir -p "$HOME/.local/bin"
ln -sfn "$(command -v fdfind)" "$HOME/.local/bin/fd"
git lfs install
```

### User PATH and vault-operator tools

Use `~/.local/bin` plus Bun user path for interactive and non-interactive SSH:

```bash
profile_line='export BUN_INSTALL="$HOME/.bun"; export PATH="$HOME/.local/bin:$BUN_INSTALL/bin:$PATH"'
grep -qxF "$profile_line" "$HOME/.profile" || printf '%s\n' "$profile_line" >> "$HOME/.profile"
grep -qxF "$profile_line" "$HOME/.bashrc" || printf '%s\n' "$profile_line" >> "$HOME/.bashrc"
eval "$profile_line"

curl -fsSL https://bun.com/install | bash
curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
curl --http1.1 -fsSL https://claude.ai/install.sh | bash -s latest
curl -fsSL https://code.kimi.com/kimi-code/install.sh | KIMI_NO_MODIFY_PATH=1 bash
ln -sfn "$HOME/.kimi-code/bin/kimi" "$HOME/.local/bin/kimi"
npm install -g --prefix "$HOME/.local" opencode-ai@latest
npm install -g --prefix "$HOME/.local" @googleworkspace/cli

sudo apt-get install -y ca-certificates curl gnupg
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/cloud.google.gpg
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main' \
  | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null
sudo apt-get update
sudo apt-get install -y google-cloud-cli
```

Claude native install follows `latest` and updates automatically. Run `claude update` for an immediate manual update. `--http1.1` avoids observed HTTP/2 write failures without changing Anthropic installer contents or checksum verification.

Install canonical provider launchers after native Claude Code on every active development machine. Configure and authenticate providers separately through `$code-i-use-claude-code-proxy-or-openrouter` and Claude Provider Routes:

```bash
launcher_installer="$(vault root)/_system/agents/edit/skills/_code/code-i-use-claude-code-proxy-or-openrouter/scripts/install-claude-provider-launchers.sh"
"$launcher_installer" SSH_ALIAS
```

Open new SSH session, then verify login shell and T3-style non-interactive shell:

```bash
for command_name in codex claude claude-codex claude-codex-high claude-codex-xhigh claude-kimi claude-kimi-proxy claude-provider claude-provider-auth claude-openrouter claude-featherless kimi opencode gh git git-lfs node npm t3 jq btop rg fd fzf curl wg bun uv gws gcloud rclone; do
  command -v "$command_name" || printf 'MISSING: %s\n' "$command_name"
done
```

From Primary machine:

```bash
ssh ctx9@BONJOUR_HOST 'sh -lc "command -v codex claude claude-codex claude-codex-high claude-codex-xhigh claude-kimi claude-kimi-proxy claude-provider claude-provider-auth claude-openrouter claude-featherless kimi opencode gh node t3 btop rg bun uv gws gcloud"'
```

Stop on any missing command. Install `project_optional` tools only when owning repository docs require them.

## 6. Configure secure GitHub OAuth and Git

Fleet SSH authenticates Primary machine into the remote shell. GitHub authentication is separate. Read GitHub Fleet Authentication: `gh` API calls use account OAuth in Secret Service, while Git uses a dedicated target-local Ed25519 authentication key and explicit SSH remotes. Never create a repository deploy key as fallback or copy any private key onto the worker.

Passwordless tty auto-login does not unlock a password-protected keyring. Keep Secret Service on the existing user D-Bus and unlock it through a target-local terminal after each reboot. Preserve the collection password outside scripts and shell history.

```bash
git config --global user.name "Fleet User"
git config --global user.email "YOUR_EMAIL"
git config --global init.defaultBranch master

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemctl --user status gnome-keyring-daemon.socket --no-pager || true
```

Stage the reviewed helper without credentials, then invoke it in a separate command whose stdin remains the real terminal:

```bash
secret_service_script="$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/linux_secret_service.py"
ssh SSH_ALIAS 'install -d -m 700 "$HOME/.local/share"'
scp "$secret_service_script" SSH_ALIAS:.local/share/ctx9-linux-secret-service.py
ssh SSH_ALIAS 'chmod 700 "$HOME/.local/share/ctx9-linux-secret-service.py"'
ssh -t SSH_ALIAS 'python3 "$HOME/.local/share/ctx9-linux-secret-service.py"'
```

The helper creates Login when absent, otherwise unlocks it, and performs a nonsecret store/read/clear proof. Never combine the interactive SSH command with a pipe, heredoc, or here-string; never pass the password through `printf`; never replace the reviewed script with encoded inline Python. Stop if the hidden prompt is unavailable, the password is rejected, or Secret Service verification fails. Do not allow `gh` plaintext fallback.

Then run:

```bash
gh auth login --hostname github.com --git-protocol ssh --skip-ssh-key --web
gh config set git_protocol ssh --host github.com
gh auth status --hostname github.com
gh api user --jq .login
! grep -q '^[[:space:]]*oauth_token:' "$HOME/.config/gh/hosts.yml"
```

Complete device flow in trusted Primary machine browser. Pause immediately before GitHub authorization and confirm account/scope. If `gh` says it stored credentials in plain text, log out, remove plaintext credential, fix Secret Service through the terminal helper, and restart login.

Return to Primary machine and use the preview-first fleet-auth helper to generate the worker's dedicated key locally, approve its public fingerprint, and verify native agent custody. Then verify SSH access with an owning organization repository plus an unrelated accessible repository:

```bash
git ls-remote git@github.com:OWNER/ACCESSIBLE_REPO.git HEAD
gh repo list --limit 2 --json nameWithOwner >/dev/null
```

Use `$infra-i-sync-code-workspaces` `migrate-github-remotes` after every selected machine passes authentication. For a manually reviewed exception, use canonical SSH and test fetch plus non-mutating push negotiation:

```bash
git -C /path/to/repo remote set-url origin git@github.com:OWNER/REPO.git
git -C /path/to/repo fetch origin
git -C /path/to/repo push --dry-run origin HEAD
```

Do not remove generic keys, credential helpers, or old account records during onboarding. Rotation and revocation are separate reviewed operations in GitHub Fleet Authentication. Keep Primary machine-to-machine fleet access on Primary machine and the worker's `authorized_keys`; it serves the opposite SSH direction.

Continue provider authentication:

```bash

codex login status
codex login --device-auth
codex login status
```

Run login command only when preceding status fails. Image may contain build-time Codex auth, but expired or revoked state is normal; status check remains mandatory.

Conditional auth:

| Tool | Re-auth command | Run when |
|---|---|---|
| Claude Code | `claude auth login` | Claude Code use is needed; credentials remain machine-local |
| Kimi Code CLI | `kimi login` | Official Kimi Code CLI use is needed; OAuth credentials remain machine-local |
| OpenCode | `opencode auth login` | OpenCode provider access is needed; credentials remain machine-local |
| GWS | `gws auth setup`, then `gws auth login --services calendar,drive` | Vault Google Workspace workflows run remotely |
| gcloud | `gcloud auth login --no-launch-browser` | Direct GCP commands run remotely |
| rclone | `rclone config` | Remote-storage jobs run remotely |
| npm | `npm login` | Private registry or publishing needed |
| Docker | `docker login <registry>` | Docker installed and private registry needed |
| SOPS/Age | restore or enroll machine-specific decryption identity through approved secret workflow | Encrypted repo config must be decrypted |
| Repo environment | follow owning repo plus `_system/local/env/README.md`; restore through encrypted/approved env workflow | Project requires local environment values |

Git author identity is configuration, not authentication. Never prove readiness from presence of config files; run status/API checks.

T3 remote environment uses SSH authentication and remote Codex provider state; no extra T3 provider login replaces `codex login status`. cmux uploads authenticated daemon/relay components during SSH bootstrap; remote machine needs no separate cmux account login.

## 7. Disable direct T3 server

Normal lifecycle is T3 desktop-managed SSH. Disable image service after enrollment:

```bash
sudo systemctl disable --now t3-code.service
systemctl is-enabled t3-code.service || true
systemctl is-active t3-code.service || true
```

Keep unit file for image diagnostics. Do not expose port `3773` when SSH-launch mode is used.

## 8. Render source-aware fleet SSH aliases

Store the confirmed LAN host and provider route through `vault machine access configure`, then use the owned renderer from [Machine Access Selection](machine-access-selection.md). Run it from the registered primary; the default covers the primary and every enabled worker:

```bash
vault machine access render --dry-run
vault machine access render
```

Verify:

```bash
ssh -G SSH_ALIAS | rg '^(hostname|user|identityfile) '
ssh SSH_ALIAS-lan 'hostname; printf "route=lan\n"'
ssh SSH_ALIAS-mesh 'hostname; printf "route=mesh\n"'
ssh SSH_ALIAS 'hostname'
ssh SSH_ALIAS 'ssh -G PRIMARY_ID | rg "^(hostname|user|identityfile|batchmode|passwordauthentication|kbdinteractiveauthentication) "'
```

Home test must resolve the target worker's canonical alias to `LAN_IP`. Away-from-home test must resolve that target to `MESH_HOST`. On the Linux worker, the canonical primary alias must resolve to the primary target's selected provider, regardless of the worker's own selected provider. Explicit `-lan` and `-mesh` aliases must always work on their respective networks.

Open a fresh passwordless reverse tunnel from the Linux worker to `PRIMARY_ID`, using an unused primary-loopback test port and a harmless worker-loopback listener. Prove the primary listener reaches the worker target, close the tunnel, and prove the primary listener disappears. `-R` does not choose WireGuard or Tailscale; the canonical primary alias does.

## 9. Reconcile Code workspaces, agent configuration, and repo-owned skills

Linux workers do not receive a Vault clone, sparse checkout, or Vault Git metadata. A code-only worker has no Vault path. An explicitly registered `remote-sshfs` worker may later mount a complete iCloud worktree from its registered Mac host through [Linux Remote Vault Access](linux-remote-vault-access.md). After target-local GitHub authentication, run from the primary while the target remains disabled:

```bash
WORKSPACE_SKILL_DIR="$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-sync-code-workspaces"
python3 "$WORKSPACE_SKILL_DIR/scripts/sync_code_workspaces.py" reconcile --target WORKER_ID --provision-disabled
python3 "$WORKSPACE_SKILL_DIR/scripts/sync_code_workspaces.py" reconcile --target WORKER_ID --provision-disabled --apply
```

This command also previews or applies every managed personal Codex and Claude file. The file set, secret boundary, home-path rebasing, backup behavior, and configuration-only repair command live only in Fleet Agent Configuration Sync.

Verify repository-owned skills inside each reconciled code repository. Skill and instruction distribution never depends on the optional Vault mount.

Reconcile clones missing catalog entries, relocates unique matching checkouts, and fetches/fast-forwards clean non-ahead existing branches. Strict skill dry-run must report every configured repo-owned source present and zero planned changes. Any dirty, ahead, divergent, inaccessible, or missing required repository blocks acceptance without changing that checkout.

### Optional full remote Vault capability

After the full-mesh SSH gate passes, inspect the machine's schema-v7 Vault mode. When it is `remote-sshfs`, complete [Linux Remote Vault Access](linux-remote-vault-access.md) before final instruction sync and enablement. When it is `none`, retain the code-only hard stop. Never infer this capability from Linux, SSH reachability, a directory named Vault, or the presence of the `$vault-i` skill.

## 10. Create cmux workspace

First deploy and verify target terminal profile using cmux and tmux Terminal Workspaces. New/rebuilt machines are not complete until `tmux`, `btop`, `starship`, `workmux`, managed configs, and pinned plugins verify.

On Primary machine, add machine profile to canonical terminal-workspace controllers, then run Warp and cmux controller dry-run/apply/verify. cmux downloads verified architecture-matching `cmuxd-remote`, uploads it under remote `~/.cmux`, starts persistent slot daemon, and creates named remote PTY. Remote does not need standalone cmux app.

Verify remote shell:

```bash
echo "$CMUX_WORKSPACE_ID"
echo "$CMUX_SURFACE_ID"
command -v cmux
cmux --help >/dev/null
```

On Primary machine, test manual recovery:

```bash
cmux workspace disconnect
cmux workspace reconnect
```

Run cmux Command Palette `Reconnect machine tmux` after restored plain remote shell. Reconnect LaunchAgent and Keyboard Maestro activation macros must remain absent.

After every enabled fleet machine verifies, run managed cmux layout controller from canonical terminal-workspace reference. It normalizes three pinned machine workspaces and one `main` surface each.

## 11. Add T3 Code environment

In T3 Code Nightly on Primary machine:

1. Open **Settings → Connections**.
2. Under **Remote Environments**, choose **Add environment**.
3. Select **SSH**.
4. SSH target: `SSH_ALIAS`.
5. Current builds derive the environment label from the SSH target and do not ask for a separate name.
6. Match the remote user-scoped `~/.local/bin/t3` version to the desktop version before the first add; otherwise T3 falls back to its pinned `npx` runner.
7. Connect, open remote home/project, then create a test Codex thread.

T3 chooses LAN or the selected mesh provider only when its SSH environment launches or re-ensures connection. Existing live tunnels do not migrate routes. Close/reconnect after changing networks or switching provider.

T3 desktop `0.0.32-nightly.20260805.1006` bounds each forwarded HTTP readiness probe to one second. Before blaming SSH or the alias, measure the selected route: if a fresh request through an SSH local forward takes more than one second, add the environment on the lower-latency LAN or wait for a T3 build with a larger probe budget. Keep the remote backend loopback-only; never work around this gate by exposing port `3773` or enabling the direct service. Full diagnosis and safe runtime cleanup are in [Primary machine Remote Access Prerequisites](primary-mac-remote-access-prerequisites.md#t3-readiness-latency-gate).

## 12. Reboot acceptance test

```bash
ssh SSH_ALIAS 'sudo systemctl reboot'
```

After host returns:

```bash
ssh SSH_ALIAS 'bash -s' <<'REMOTE'
set -eu
hostnamectl --static
for command_name in codex claude claude-codex claude-codex-high claude-codex-xhigh claude-kimi claude-kimi-proxy claude-provider claude-provider-auth claude-openrouter claude-featherless kimi opencode gh git node npm t3 jq btop rg curl bun uv gws gcloud; do command -v "$command_name"; done
codex login status
gh auth status --hostname github.com
systemctl is-active ssh.service avahi-daemon.service
! systemctl is-active --quiet t3-code.service
REMOTE
```

Run the selected provider reference's reboot/status checks separately; require `wg-quick@wg0` only for WireGuard or `tailscaled` only for Tailscale.

Then:

1. Select cmux remote workspace and confirm shell reattaches or fresh shell opens after manual reconnect.
2. Reconnect T3 environment and start Codex thread.
3. Test `SSH_ALIAS-lan`, `SSH_ALIAS-mesh`, and automatic alias, then repeat the canonical reverse-forward proof from the rebooted worker to `PRIMARY_ID`.
4. Confirm no background direct T3 listener: `ssh SSH_ALIAS 'ss -lnt | rg ":3773" || true'`.
5. For an enrolled `remote-sshfs` client, repeat the mount, exact-source, full-tree, Gitless-pointer, read-write, status, and automatic reconnect checks in [Linux Remote Vault Access](linux-remote-vault-access.md). For a code-only worker, confirm no Vault root or mount exists.

## Optional daemons and watchdogs

Optional Linux worker background services are explicit opt-ins, not default onboarding gates. The registered set currently contains one watchdog:

- `playwright-cli`: wraps the existing user-scoped Playwright CLI to refresh exact session activity, then uses a systemd user timer every ten minutes to close only sessions idle for at least one hour. It never runs routine `close-all` or `kill-all`, and it does not target unrelated Chrome profiles.

Preview, install, and verify from the registered primary:

```bash
watchdog_installer="$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/linux_optional_watchdogs.py"
python3 "$watchdog_installer" --target WORKER_ID --watchdog playwright-cli
python3 "$watchdog_installer" --target WORKER_ID --watchdog playwright-cli --apply
python3 "$watchdog_installer" --target WORKER_ID --watchdog playwright-cli --verify
```

Add `--provision-disabled` only during reviewed onboarding of an exact disabled Linux worker. The controller requires Python, systemd user services with lingering, and the existing user-owned `@playwright/cli` installation. It preserves the original CLI symlink target for rollback, refuses an unrelated wrapper, deploys only the selected watchdog, enables its timer, runs an immediate sweep, and verifies deployed hashes plus CLI launch.

Acceptance:

```bash
systemctl --user is-enabled playwright-cli-watchdog.timer
systemctl --user is-active playwright-cli-watchdog.timer
playwright-cli --version
```

Normal agent cleanup still closes the exact named session before task completion. The watchdog is only the crash/interruption safety net. Inspect cleanup events with `journalctl --user -u playwright-cli-watchdog.service`; do not weaken the idle threshold or use global Playwright cleanup while concurrent agent sessions may exist.

## 13. Record topology

Update Machine Requirements and Topology with:

- friendly name and role;
- Bonjour/static hostname;
- LAN reservation and observation date;
- selected machine-access provider and stable mesh host;
- OS and architecture;
- SSH alias, user, key;
- Codex version and auth status;
- T3 environment label/status;
- physical location and notes.

Run:

```bash
fleet sync --dry-run
fleet sync
```

Register the machine disabled in the private registry, run the explicit onboarding Code-workspace reconciliation, and require Code workspace doctor to verify both repositories and agent configuration before enablement.

## WireGuard administration

This section applies only when WireGuard is the selected personal provider or remains a separate Kubernetes route.

Public enrollment surface exposes enrollment and health only. Run peer administration from owning infrastructure repository:

```bash
cd "<configured k3s-infrastructure path>/_wireguard-enrollment"
./list-peers.sh
./revoke-peer.sh <machine-id>
./reconcile-peers.sh
```

Every machine generates unique WireGuard private key. Same machine ID and public key may recover same assignment; conflicting reuse must stop. After retirement, revoke peer and disable or remove `wg0`; never reassign private key.

Enrollment-token rotation invalidates uninstalled older images. Rotate through k3s env workflow, redeploy enrollment service, refresh private image staging, rebuild/validate ISO, then destroy superseded ISO copies. Follow owning k3s-infrastructure and codex-machine-image READMEs; never place enrollment token in this Vault reference.

## Failure and rollback

- Wrong target disk: stop before storage confirmation.
- WireGuard enrollment failure: keep token intact; fix network and restart enrollment service. Do not hand-edit the assigned address.
- Reused machine/key conflict `409`: revoke retired peer or repair registry; never clone private key.
- Wrong SSH host key: stop and identify host. Remove known-host entry only after confirming reinstall/replacement.
- Bad dependency install: restore package source, rerun profile idempotently, then pass command gate.
- T3 SSH failure: verify `ssh SSH_ALIAS 'sh -lc "command -v node codex t3"'`, align the remote user-scoped T3 version with the desktop, and apply the readiness latency gate in [Primary machine Remote Access Prerequisites](primary-mac-remote-access-prerequisites.md#t3-readiness-latency-gate) before changing aliases or remote services.
- LAN route failure: verify DHCP reservation and `SSH_ALIAS-lan`; the canonical alias should still fall back to the selected `-mesh` route.
- Secret Service failure: stop GitHub rollout. Never accept `gh` plaintext credential fallback. Confirm user D-Bus socket, keyring daemon, DISPLAY, collection password, and noVNC unlock.
- Retire machine: revoke the selected provider identity, remove its service and T3 environment, then update aliases and topology. Retire a separate Kubernetes WireGuard peer only when that route is also being removed.
