---
type: agent-reference
status: enabled
---

## GitHub Fleet Authentication

GitHub authentication has two independent channels:

- Git transport uses one dedicated Ed25519 authentication key per machine and explicit `git@github.com:OWNER/REPO.git` remotes.
- `gh` REST and GraphQL access uses OAuth stored in macOS Keychain or Linux Secret Service. An SSH key cannot authenticate GitHub API calls.

Fleet-shell SSH and outbound GitHub SSH are different trust directions. Never copy a private key between machines, reuse Primary machine's fleet-access key, create a signing key, or substitute a repository deploy key. Each machine generates `~/.ssh/id_ed25519_github_<machine-id>` locally; GitHub title is `ctx9-fleet:<machine-id>`. Passphrase protection with native SSH-agent custody is required by default.

Use the onboarding helper from Primary machine:

```bash
auth_script="$(vault root)/_system/agents/skills/_infrastructure/infra-i-onboard-machine/scripts/github_fleet_auth.py"
python3 "$auth_script" audit
python3 "$auth_script" provision --target MACHINE_ID
python3 "$auth_script" provision --target MACHINE_ID --apply --interactive
python3 "$auth_script" provision --target LINUX_MACHINE_ID --allow-passphrase-free
python3 "$auth_script" provision --target LINUX_MACHINE_ID --allow-passphrase-free --apply
python3 "$auth_script" enroll --target MACHINE_ID
python3 "$auth_script" verify --target MACHINE_ID
```

Preview is the default. `provision --apply --interactive` opens a target-local `ssh-keygen` passphrase prompt and never returns private material to Primary machine. On macOS, the helper discovers the logged-in user's native `com.openssh.ssh-agent` socket through the GUI launchd domain when a remote shell does not inherit `SSH_AUTH_SOCK`; it also includes the standard Homebrew paths for `gh`. This keeps CLI-only acceptance accurate without Screen Sharing. If the GUI agent genuinely is not running, use the documented target-local onboarding checkpoint rather than weakening key custody. Enrollment still runs only on Primary machine. `enroll` prints only the title and fingerprint; stop for Matt's explicit approval, then rerun with `--apply --approve-fingerprint SHA256:...`. The helper enrolls an authentication key through Primary machine's authenticated `gh` session. Existing matching fingerprints are idempotent. `revoke` also previews and requires exact `--approve-title`; it preserves target-local files.

Matt approved the unattended Linux exception on 2026-08-17. Registered Linux workers may use `--allow-passphrase-free` when native-agent custody cannot satisfy post-reboot noninteractive Git. The helper refuses Macs, refuses to replace an enrolled passphrased key, preserves an existing un-enrolled pair under `~/.ssh/ctx9-key-backups/<UTC>/`, generates the replacement on the Linux target, marks the managed SSH fragment, and verifies that the file actually has no passphrase without displaying private material. The exception trades protection against filesystem theft for reliable unattended access; keep the key machine-specific, mode `0600`, explicitly selected, and immediately revocable.

The managed SSH fragment selects only the dedicated key, uses `IdentitiesOnly`, and enforces strict host checking. The helper installs GitHub's published Ed25519 host key and records the currently published fingerprint `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`. Reconfirm it against [GitHub's SSH key fingerprints](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints) before changing the pinned value.

Configure OAuth independently:

```bash
gh auth login --hostname github.com --git-protocol ssh --skip-ssh-key --web
gh config set git_protocol ssh --host github.com
gh auth status --hostname github.com
gh api user --jq .login
! grep -q '^[[:space:]]*oauth_token:' "$HOME/.config/gh/hosts.yml"
```

Do not run `gh auth setup-git` for GitHub fleet repositories. Do not uninstall Git Credential Manager; it may still serve other HTTPS hosts. macOS must store OAuth in Keychain. Linux must provide an unlocked native Secret Service collection; plaintext `hosts.yml` OAuth blocks acceptance.

If a Mac has a valid plaintext token and an incomplete or stale `gh:github.com` Keychain pair, stage `infra-i-onboard-machine/scripts/macos_gh_keychain.py` on that Mac. Run it in the logged-in GUI bootstrap domain, either from a target-local Terminal or a reviewed ephemeral per-user LaunchAgent created through SSH. The helper keeps the token in target-local memory, replaces only the authenticated user's per-user record and `gh` active-slot record, proves API access with a temporary token-free `hosts.yml`, and removes plaintext only after that proof. On failure it restores the original mode-`0600` config. Do not print the token, pass it through SSH, start a new browser login solely to repair this storage state, or use Screen Sharing for routine repair.

When Keychain reads remain intentionally unavailable to the SSH audit session, run the installed `vault-worker-auth-attest` helper through the same target-local or ephemeral-LaunchAgent GUI context. Fleet verification may accept its mode-`0600`, machine-ID-matched, secret-free booleans for `gh` API health; dedicated GitHub SSH must still pass directly in the noninteractive controller context, and any plaintext OAuth field still fails acceptance.

For an already-authenticated Linux worker whose only failure is plaintext `hosts.yml`, do not repeat browser OAuth or open Screen Sharing solely to migrate storage. Stage `infra-i-onboard-machine/scripts/linux_secret_service.py` on the target, then invoke it through a separate standalone `ssh -t` command. It uses a hidden terminal prompt and the running Secret Service D-Bus interface to create or unlock Login, repair the historical accidental-newline case, and prove a disposable store/read/clear sentinel. Never pipe or heredoc an interactive SSH invocation, pass a password through `printf`, or replace the reviewed script with an encoded inline payload.

After Secret Service passes, re-store the existing token through `gh auth login --with-token` entirely on that target. Keep shell tracing disabled, never print or transfer the token, and verify `gh api user` plus the absence of `oauth_token:` afterward. Restart the managed Secret Service daemon deliberately and repeat the noninteractive API proof; a collection that works only until the daemon restarts is not unattended acceptance. If the collection password is unknown, inventory only collection/item labels and attributes, never secret values; stop the service, preserve the complete keyring directory with a checksum manifest under a private timestamped native backup path, activate an empty mode-`0700` directory, restart the managed service, and use the same staged script to create the replacement collection. Never delete the preserved backup during repair.

Routine workspace sync and repair are SSH/CLI-only and never open Screen Sharing, noVNC, Browser, Computer Use, or another GUI authentication fallback. Initial onboarding may pause at its documented target-local browser or credential-store checkpoint for OAuth. Public-key enrollment, OAuth account choice, SSO authorization, credential-store unlock, passphrase-free exceptions, and revocation always require separate human approval.

After login and again after reboot, require:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -T git@github.com
gh api user --jq .login
gh config get git_protocol --host github.com
```

Also run noninteractive `git ls-remote` against one private personal repository, one organization repository, and one public third-party repository. Passphrase-protected keys require native-agent visibility. An approved Linux exception instead requires both the managed exception marker and a verified passphrase-free key.

For rotation, provision and approve a newly named key, verify every required repository and reboot context, migrate the managed identity, then separately approve revocation of the old GitHub key. Preserve OAuth, generic SSH keys, prior sanitized remote URLs, and working transport until acceptance passes. For a lost or compromised machine, revoke its exact titled key first; never delete another machine's key by inference.
