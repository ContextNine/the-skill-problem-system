# Claude Code Proxies

Private fleet SOP for routing Claude Code through non-Anthropic model providers while leaving direct `claude` unchanged. Install command parity on every active Claude Code development machine; provider credentials remain separate and machine-local.

## Routes

```text
claude-codex -> localhost:8317 -> CLIProxyAPI -> Codex OAuth -> GPT-5.6 Sol
claude-kimi  -> localhost:8317 -> CLIProxyAPI -> Kimi OAuth -> included plan quota -> Kimi K3
claude       -> normal Claude Code configuration
```

Both provider launchers pass `--dangerously-skip-permissions` and explicitly force `--permission-mode bypassPermissions`. Explicit mode prevents Claude Code from falling back to or displaying `manual` permission mode. Model-generated commands can read, modify, or delete anything available to current machine user. Run only inside trusted directories and repositories.

## Commands

```bash
claude-codex
claude-codex-high
claude-codex-xhigh
claude-codex --effort medium
claude-codex --effort high
claude-codex --effort xhigh

claude-kimi
claude-kimi --normal
claude-kimi --effort low
claude-kimi --effort high
claude-kimi --effort max
claude-kimi --1m
```

Each launcher prints route before Claude Code starts. Example:

```text
Claude route: provider=Codex model=gpt-5.6-sol(high) effort=high base=http://127.0.0.1:8317
Claude route: provider=Kimi-OAuth model=kimi-k3(max) effort=max base=http://127.0.0.1:8317 context=262144
```

Remaining arguments pass to Claude Code unchanged:

```bash
claude-codex-high -p --max-turns 1 "Explain this repository"
claude-kimi --normal -p --max-turns 1 "Explain this repository"
```

## Shared rules

- Required commands on Primary machine, Linux worker, Worker Mac, and future active Claude Code development machines: `claude-codex`, `claude-codex-high`, `claude-codex-xhigh`, and `claude-kimi`.
- Canonical launchers and installer live in `../scripts/`. Run installer without arguments for Primary machine or with SSH alias for another machine after native Claude Code installation.

From Primary machine:

```bash
launcher_installer="$(vault root)/_system/agents/skills/auto/_infrastructure/infra-onboard-machine/scripts/install-claude-provider-launchers.sh"
"$launcher_installer"
"$launcher_installer" linux-worker
"$launcher_installer" worker-mac
```
- Provider variables exist only in launcher child process. Parent shell remains unchanged.
- Direct `claude` remains unchanged.
- Clear competing Anthropic API, OAuth, Bedrock, Vertex, and Foundry variables before launch.
- Keep provider credentials machine-local, mode `0600`; never copy values into vault, logs, tickets, or chat.
- Do not add paid fallback, account rotation, limit bypass, or silent model downgrade.
- Verify route with Claude Code `/status` after authentication.

## Codex through CLIProxyAPI

### Verified state

Observed 2026-07-19:

- Primary machine and Linux worker: Claude Code `2.1.215`; all four provider commands installed from canonical launchers.
- Both machines initially used CLIProxyAPI `7.2.88`; listener restricted to `127.0.0.1:8317`.
- Linux worker: user systemd service active; Codex OAuth present; `gpt-5.6-sol` medium/high/xhigh verified; included subscription usage remained active after validation.
- Primary machine: user launchd service active; Codex OAuth pending; `/v1/models` remains empty until login.
- Primary machine: Kimi OAuth present; `kimi-k3(max)` live Claude Code request verified with expected response.
- Linux worker: Kimi OAuth present; `kimi-k3(max)` live Claude Code request verified with expected response.

Observed 2026-08-06:

- Linux worker remains on CLIProxyAPI `7.2.88`; its systemd user service, loopback-only listener, Kimi OAuth route, canonical launcher digest, and live `kimi-k3(max)` Claude Code request passed.
- Worker Mac uses checksum-verified CLIProxyAPI `7.2.112`, Claude Code `2.1.223`, and Kimi Code CLI `0.33.0`; its LaunchAgent, loopback-only listener, fresh machine-local Kimi OAuth route, canonical launcher digest, model listing, and live `kimi-k3(max)` Claude Code request passed.
- The launcher installer accepts both Linux `/tmp/tmp.*` and macOS `/var/folders/.../T/tmp.*` remote staging directories while retaining its unexpected-path refusal.

### Paths

- Versioned binary: `~/cliproxyapi/<version>/cli-proxy-api`
- Stable release link: `~/cliproxyapi/current`
- Config: `~/cliproxyapi/config.yaml`, mode `0600`
- Local client credential: `~/cliproxyapi/client-token`, mode `0600`
- OAuth directory: `~/.cli-proxy-api`, mode `0700`; credential files mode `0600`
- Launcher: `~/.local/bin/claude-codex`
- Launcher shortcuts: `~/.local/bin/claude-codex-{high,xhigh}`
- System command links: `/usr/local/bin/claude-codex`, `/usr/local/bin/claude-codex-high`, `/usr/local/bin/claude-codex-xhigh`
- Linux user unit: `~/.config/systemd/user/cliproxyapi.service`
- macOS LaunchAgent: `~/Library/LaunchAgents/com.router-for-me.cliproxyapi.plist`

### Health checks

```bash
systemctl --user is-enabled cliproxyapi.service
systemctl --user is-active cliproxyapi.service
ss -lnt 'sport = :8317'
journalctl --user -u cliproxyapi.service --since today --no-pager
```

On macOS:

```bash
launchctl print "gui/$(id -u)/com.router-for-me.cliproxyapi"
lsof -nP -iTCP:8317 -sTCP:LISTEN
```

Expected listener: only `127.0.0.1:8317`. Treat LAN, WireGuard, or wildcard binding as failure; stop service before repair.

Confirm model availability without printing credential:

```bash
curl -fsS \
  -H "Authorization: Bearer $(<"$HOME/cliproxyapi/client-token")" \
  http://127.0.0.1:8317/v1/models \
  | jq -e 'any(.data[].id; . == "gpt-5.6-sol")'
```

### OAuth login or refresh

CLIProxyAPI Codex OAuth remains separate from Codex CLI auth.

For Linux worker, open tunnel from Primary machine:

```bash
ssh -o ExitOnForwardFailure=yes -L 1455:127.0.0.1:1455 linux-worker
```

In tunneled Linux worker shell:

```bash
systemctl --user stop cliproxyapi.service
~/cliproxyapi/current/cli-proxy-api \
  -config ~/cliproxyapi/config.yaml \
  --codex-login \
  --no-browser
```

Open printed URL on Primary machine, complete OpenAI login, then restart service. Confirm OAuth file existence and mode only; do not read contents.

For Primary machine itself, no SSH tunnel is needed:

```bash
launchctl bootout "gui/$(id -u)/com.router-for-me.cliproxyapi"
~/cliproxyapi/current/cli-proxy-api \
  -config ~/cliproxyapi/config.yaml \
  --codex-login
launchctl bootstrap "gui/$(id -u)" \
  ~/Library/LaunchAgents/com.router-for-me.cliproxyapi.plist
```

Complete browser login using same ChatGPT account. Then run authenticated `/v1/models` health check and require `gpt-5.6-sol` before using `claude-codex`.

### Upgrade and rollback

For upgrade, verify exact release checksum for target OS and architecture, install beside existing version, move `current` symlink, restart, and rerun listener/model/protocol/tool-use tests. Never overwrite config, token, OAuth, or direct Claude/Codex configuration.

On OAuth, model, or translation failure:

```bash
systemctl --user disable --now cliproxyapi.service
```

On macOS use `launchctl bootout "gui/$(id -u)/com.router-for-me.cliproxyapi"`.

Preserve private files for diagnosis. Remove installation or OAuth records only after explicit deletion approval.

## Kimi Code through CLIProxyAPI

Fleet default uses CLIProxyAPI Kimi OAuth. CLIProxyAPI translates Claude messages and tool calls, refreshes Kimi OAuth, and exposes proxy model `kimi-k3`. This route is experimental but passed a live Primary machine Claude Code request on 2026-07-19.

Official documentation:

- https://www.kimi.com/code/docs/en/third-party-tools/other-coding-agents
- https://www.kimi.com/code/docs/en/kimi-code/models.html

### Official Kimi Code CLI

Official `kimi` CLI is separate from Claude Code routing. Install it on every active development machine with official checksum-verifying installer, keep its files under `~/.kimi-code`, and expose command through `~/.local/bin/kimi` or an equivalent stable PATH location:

```bash
curl -fsSL https://code.kimi.com/kimi-code/install.sh | \
  KIMI_NO_MODIFY_PATH=1 bash
ln -sfn "$HOME/.kimi-code/bin/kimi" "$HOME/.local/bin/kimi"
kimi --version
kimi login
```

`kimi login` uses Kimi Code OAuth device flow and stores official-client credentials under `~/.kimi-code`. CLIProxyAPI uses its own separate Kimi OAuth record under `~/.cli-proxy-api`; authenticate both on each machine.

### Model and effort

- Proxy model ID: `kimi-k3`; CLIProxyAPI normalizes upstream model to `k3`.
- `claude-kimi` defaults to Claude effort `max`, mapped by Kimi to K3 `max` thinking.
- `claude-kimi --normal` uses Claude effort `high`, mapped to K3 `high` thinking.
- `--effort low|high|max` selects explicit K3 effort.
- Default context is safe 256K: proxy model `kimi-k3(<effort>)`, context `262144`.
- `--1m` uses proxy model form `kimi-k3[1m](<effort>)` and context `1048576`; use only with Allegretto-or-higher 1M entitlement.
- Disabling thinking can route away from K3. Keep thinking enabled.

### Authentication

Stop local proxy service, run CLIProxyAPI Kimi device login, approve printed URL, then restart service.

On macOS:

```bash
launchctl bootout "gui/$(id -u)/com.router-for-me.cliproxyapi"
~/cliproxyapi/current/cli-proxy-api \
  -config ~/cliproxyapi/config.yaml \
  --kimi-login
launchctl bootstrap "gui/$(id -u)" \
  ~/Library/LaunchAgents/com.router-for-me.cliproxyapi.plist
```

On Linux/headless SSH:

```bash
systemctl --user stop cliproxyapi.service
~/cliproxyapi/current/cli-proxy-api \
  -config ~/cliproxyapi/config.yaml \
  --kimi-login \
  --no-browser
systemctl --user start cliproxyapi.service
```

Confirm credential file exists and mode only; never read it. Then require proxy model:

```bash
curl -fsS \
  -H "Authorization: Bearer $(<"$HOME/cliproxyapi/client-token")" \
  http://127.0.0.1:8317/v1/models \
  | jq -e 'any(.data[].id; . == "kimi-k3")'
```

Launcher exports only for child Claude process:

- `ANTHROPIC_BASE_URL=http://127.0.0.1:8317`
- `ANTHROPIC_AUTH_TOKEN` from private CLIProxyAPI client-token file
- `kimi-k3(<effort>)` model variables for all Claude model slots and subagents
- 256K or explicitly selected 1M context variables

After launch, run `/status`. Expected Base URL: `http://127.0.0.1:8317`. Route banner must show `provider=Kimi-OAuth` and `model=kimi-k3(...)`.

Live smoke test:

```bash
claude-kimi -p --max-turns 1 \
  'Reply with exactly: CLAUDE_KIMI_COMMAND_OK'
```

Expected response: `CLAUDE_KIMI_COMMAND_OK`.

### Official direct API-key alternative

Kimi officially supports direct Claude Code routing through `https://api.kimi.com/coding/` using Kimi Code membership API key from https://www.kimi.com/code/console. That key consumes included plan quota, not Kimi Open Platform pay-as-you-go billing. Fleet launcher does not use this route while tested CLIProxyAPI OAuth works. Do not use `api.moonshot.cn` or change route without review.

### Failure and OAuth refresh

- Missing `kimi-k3`: rerun CLIProxyAPI `--kimi-login`, restart service, and repeat model query.
- Authentication or entitlement error: verify Kimi Code benefit, OAuth device status, and 256K versus 1M entitlement.
- Preserve OAuth records for diagnosis. Delete or replace only after explicit confirmation.
- Never copy OAuth records into shell profiles, Claude settings, vault, tickets, or chat.
