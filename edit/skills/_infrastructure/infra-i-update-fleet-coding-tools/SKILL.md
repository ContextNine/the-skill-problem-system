---
name: infra-i-update-fleet-coding-tools
description: Updates installed T3 Code nightly CLI/server or macOS desktop, Codex CLI, Claude Code, and OpenCode across topology-registry target machines without installing missing tools. Use when updating coding-agent tools across the machine fleet or named target machines.
---

# Infra · Update Fleet Coding Tools

## Shared command

This skill is the coding-tool specialist used by [Update Fleet Dependencies](../infra-i-update-fleet-dependencies/SKILL.md). Execute through the shared implementation:

```bash
fleet update --coding-tools --dry-run
fleet update --coding-tools
```

The command owns the immutable cross-machine plan, default apply, sync, final verification, and factual lock. The rules below remain authoritative for its coding-tool adapter and for resolving any reported manual checkpoint.

## Dependency and target resolution

Read [Code Folder and Computer Topology](../infra-i-code-folder-and-computer-topology/SKILL.md) and every prerequisite it requires before connecting to or changing a machine.

- Resolve and validate `fleet/machines.json` with `fleet config`; never hardcode the private Vault source path. If it is absent or invalid, keep fleet updates inactive and show setup guidance from the topology skill.
- Resolve the current machine from clone-local `vault.machine-id` on Git checkouts or `~/.config/vault/machine-id` on a Gitless iCloud worker; never infer it from hostname.
- When the user names machines, operate only on those enabled registry entries.
- Otherwise, target enabled machines whose `vault_sync.enabled` is `true`. Use `transport: local` locally and the registry's `ssh_alias` for SSH targets. Do not hardcode machine IDs, aliases, homes, or paths.
- Process and verify one target at a time so a failure on one machine cannot obscure another machine's result.

## Installed-only gate

On every target, use the target user's login-shell environment. Run `command -v` separately for `codex`, `claude`, and `opencode`. For T3, count a resolved `t3` command, an existing `~/.npm/_npx/*/node_modules/t3/package.json`, or a macOS app whose bundle identifier is `com.t3tools.t3code` as installed; inspect only existing paths and do not fetch merely to detect it.

- A provider command that does not resolve, or T3 with neither installed-state signal, is absent: mark it `skipped (not installed)` and do nothing else for that tool on that machine.
- Do not install an absent tool, create a launcher or symlink, modify `PATH`, authenticate, migrate an installer, change configuration, or clear caches.
- Capture the resolved executable or app path and current version before updating. Identify its installer or package-manager provenance without changing the machine.
- Preserve the existing install channel and prefix. Never replace an unknown-provenance executable with a different installation.

## Update installed tools

### T3 Code

T3 Code follows nightly builds.

1. If the request supplies an exact T3 version, use it. Otherwise resolve `npm view t3 dist-tags.nightly` once per run and use that exact version for every targeted T3 CLI/server and desktop installation so paired machines match.
2. Validate that the resolved value is nonempty and contains `-nightly.`; stop T3's update on that target if validation fails.
3. For an existing global npm installation, update the same prefix with `npm install -g t3@<resolved-version>`. Use the existing package manager if provenance shows pnpm, Yarn, or Bun instead.
4. For an npx-only installation, refresh and verify the exact nightly without launching the server: `npx --yes t3@<resolved-version> --version`.
5. Use privilege elevation only when the existing global installation is root-owned and the invocation's authorization permits it; otherwise report `blocked (existing install requires elevation)`.
6. For an installed macOS nightly app, follow [Native Artifact Updates](references/native-artifact-updates.md). Use its configured GitHub nightly channel and the same exact version resolved above.
7. If an active T3 server was started by an existing manager such as systemd, launchd, or T3 desktop's managed SSH launcher, restart it only through that confirmed existing control path and verify it is running/listening. Do not enable a disabled service, create a manager, or guess how an unmanaged process should restart.
8. Verify a global installation with `t3 --version`; verify an npx-only installation with the exact-version command above; verify a desktop installation from `CFBundleShortVersionString`, its signature, and bundle identifier.

### Codex CLI

- Prefer `codex update` when `codex help update` confirms the installed CLI supports its self-updater.
- Treat a user-owned `~/.local/bin/codex` resolving through `$CODEX_HOME/packages/standalone/current` as the official standalone channel. If its self-updater is unavailable, rerun `curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh`; do not reconstruct or replace its managed release layout manually.
- For other confirmed provenance, Homebrew cask uses `brew upgrade --cask codex`; global npm uses the same prefix with `npm install -g @openai/codex@latest`.
- A root-owned `/usr/local/bin/codex` with `/etc/codex-machine-image-version` is a legacy image channel, not the current desired state. Use [Native Artifact Updates](references/native-artifact-updates.md) only for recovery when explicit migration to the official standalone channel is outside the request.
- If provenance is unsupported or unknown, leave it unchanged and report the blocker instead of reinstalling it.
- Verify with `codex --version` and `command -v codex`.

### Claude Code

- Run `claude update` for an installed `claude` command.
- Verify with `claude --version` and `command -v claude`.

### OpenCode

- Run `opencode upgrade` for an installed `opencode` command. If the command requires an explicit method, pass the confirmed existing install method rather than guessing.
- Verify with `opencode --version` and `command -v opencode`.

## Verification and report

- Treat a nonzero updater exit, missing post-update executable, unexpected path change, or unreadable version as a failure for that tool; continue safely with the remaining tools and targets.
- Do not claim success from download output alone. Compare before and after versions; `already current` is successful when the updater exits cleanly and the executable still verifies.
- Report a compact matrix with machine, tool, before, after, status, and update method. Include every absent tool as an explicit skip.
- Do not edit registry or machine notes for routine version changes. Record only durable newly confirmed machine facts, such as a changed installer provenance, in the registry-linked private machine note.
