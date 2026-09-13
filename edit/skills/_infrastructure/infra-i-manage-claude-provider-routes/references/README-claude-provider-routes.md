# Claude Provider Routes

Private fleet SOP for routing Claude Code through alternate model providers while leaving direct `claude` unchanged. This skill is the single canonical owner for launcher source, installation, authentication, provider behavior, and acceptance.

## Routes

```text
claude-codex -> localhost:8317 -> CLIProxyAPI -> Codex OAuth -> GPT-5.6 Sol
claude-kimi -> Kimi Platform Anthropic endpoint -> API key -> Kimi K3
claude-kimi-proxy -> localhost:8317 -> CLIProxyAPI -> Kimi OAuth -> included plan quota -> Kimi K3
claude-openrouter <slug> -> OpenRouter Anthropic endpoint -> selected model
claude-featherless <slug> -> isolated loopback CLIProxyAPI -> Featherless OpenAI endpoint -> selected model
claude       -> normal Claude Code configuration
```

Provider launchers pass `--dangerously-skip-permissions` and explicitly force `--permission-mode bypassPermissions`. Explicit mode prevents Claude Code from falling back to or displaying `manual` permission mode. Model-generated commands can read, modify, or delete anything available to current machine user. Run only inside trusted directories and repositories.

## Commands

```bash
claude-codex
claude-codex-high
claude-codex-xhigh
claude-codex --effort medium
claude-codex --effort high
claude-codex --effort xhigh

claude-kimi
claude-kimi -p "Explain this repository"

claude-kimi-proxy
claude-kimi-proxy --normal
claude-kimi-proxy --effort low
claude-kimi-proxy --effort high
claude-kimi-proxy --effort max
claude-kimi-proxy --1m

claude-openrouter moonshotai/kimi-k3
claude-openrouter moonshotai/kimi-k3 -p "Explain this repository"

claude-featherless empero-ai/Qwythos-9B-Claude-Mythos-5-1M
claude-featherless empero-ai/Qwythos-9B-Claude-Mythos-5-1M -p "Explain this repository"

claude-provider openrouter moonshotai/kimi-k3
claude-provider featherless empero-ai/Qwythos-9B-Claude-Mythos-5-1M
```

Each launcher prints route before Claude Code starts. Example:

```text
Claude route: provider=Codex model=gpt-5.6-sol(high) effort=high base=http://127.0.0.1:8317
Claude route: provider=Kimi-Platform model=kimi-k3[1m] haiku=kimi-k2.7-code effort=max base=https://api.moonshot.ai/anthropic context=1000000
Claude route: provider=Kimi-OAuth-Proxy model=kimi-k3(max) effort=max base=http://127.0.0.1:8317 context=262144
Claude route: provider=OpenRouter model=moonshotai/kimi-k3 base=https://openrouter.ai/api
Claude route: provider=Featherless model=empero-ai/Qwythos-9B-Claude-Mythos-5-1M base=http://127.0.0.1:<ephemeral-port> upstream=https://api.featherless.ai/v1
```

Remaining arguments pass to Claude Code unchanged:

```bash
claude-codex-high -p --max-turns 1 "Explain this repository"
claude-kimi -p --max-turns 1 "Explain this repository"
claude-kimi-proxy --normal -p --max-turns 1 "Explain this repository"
claude-openrouter moonshotai/kimi-k3 -p --max-turns 1 "Explain this repository"
```

## Ownership and paths

| Concern | Canonical location |
| --- | --- |
| Skill, scripts, tests, and this SOP | `_system/agents/edit/skills/_infrastructure/infra-i-manage-claude-provider-routes/` |
| Installed commands | `~/.local/bin/claude-*` |
| Isolated OpenRouter and Featherless Claude state | `~/.config/ctx9/claude-provider-routes/claude/<provider>/` |
| Kimi Platform, OpenRouter, and Featherless credentials on macOS | Keychain services `ctx9-claude-provider-<provider>` |
| Kimi Platform, OpenRouter, and Featherless credentials on Linux | Secret Service attributes `ctx9-provider=claude-route`, `ctx9-route=<provider>` |
| Shared Codex and Kimi proxy runtime | `~/cliproxyapi/` and `~/.cli-proxy-api/` |
| Featherless per-session translator | `$TMPDIR/ctx9-claude-featherless.*`, removed when the launcher exits |
| Sanitized fleet acceptance facts | topology machine notes and `machine-secrets.lock.json` |

Onboarding links here and installs these scripts. It does not keep another launcher copy or provider SOP. Topology notes record dated facts only.

## Shared rules

- Required command parity on selected Claude Code development machines: `claude-codex`, `claude-codex-high`, `claude-codex-xhigh`, `claude-kimi`, `claude-kimi-proxy`, `claude-provider`, `claude-provider-auth`, `claude-openrouter`, and `claude-featherless`. Provider credential enrollment remains optional until that route is selected.
- Canonical launchers and installer live in `../scripts/`. Run installer without arguments for Primary machine or with SSH alias for another machine after native Claude Code installation.

From Primary machine:

```bash
launcher_installer="$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-manage-claude-provider-routes/scripts/install-claude-provider-launchers.sh"
"$launcher_installer"
"$launcher_installer" linux-worker
"$launcher_installer" worker-mac
```
- Provider variables exist only in launcher child process. Parent shell remains unchanged.
- Direct `claude` remains unchanged.
- Clear competing Anthropic API, OAuth, Bedrock, Vertex, and Foundry variables before launch.
- Keep provider credentials machine-local in the declared native store; never copy values into vault, logs, tickets, shell profiles, process arguments, or chat.
- Do not add paid fallback, account rotation, limit bypass, or silent model downgrade.
- Verify route with Claude Code `/status` after authentication.

## Kimi Platform direct route

`claude-kimi` uses Kimi Platform's Anthropic-compatible endpoint directly. It does not use CLIProxyAPI. The launcher reads a Kimi Platform API key from the machine's native credential store, clears competing Claude provider variables, exports Kimi's documented environment only to the child process, and starts the normal Claude Code executable. Running `claude` later uses the normal Anthropic configuration.

The direct launcher follows Kimi's documented model mapping: `kimi-k3[1m]` for the main, Opus, Sonnet, Fable, and subagent slots; `kimi-k2.7-code` for Haiku; one-million-token auto-compaction; and maximum effort.

Official guide: https://platform.kimi.ai/docs/guide/claude-code-kimi

Create the API key at https://platform.kimi.ai, then enroll and verify it without printing the value:

```bash
claude-provider-auth kimi
claude-provider-auth kimi --status
claude-kimi
```

The API key belongs to Kimi Platform and uses Platform billing. It is not the Kimi Code membership key from `kimi.com/code/console`, nor the OAuth record used by `claude-kimi-proxy`.

After launch, run `/status`. Expected Base URL: `https://api.moonshot.ai/anthropic`. The model should show `kimi-k3[1m]`. A bounded smoke test is:

```bash
claude-kimi -p --max-turns 1 \
  'Reply with exactly: CLAUDE_KIMI_DIRECT_OK'
```

Expected response: `CLAUDE_KIMI_DIRECT_OK`.

## OpenRouter

OpenRouter publishes an Anthropic-compatible Claude Code endpoint, so this route does not use the local proxy. The launcher sets `ANTHROPIC_BASE_URL=https://openrouter.ai/api`, sends the protected key through `ANTHROPIC_AUTH_TOKEN`, explicitly empties `ANTHROPIC_API_KEY`, and maps every Claude role to the supplied model slug.

OpenRouter warns that Claude Code is only guaranteed with Anthropic first-party models. Other slugs can work, including `moonshotai/kimi-k3`, but tool use, thinking controls, context handling, and prompt compatibility depend on that model and provider route.

Official guide: https://openrouter.ai/docs/guides/coding-agents/claude-code-integration

Enroll and verify without printing the key:

```bash
claude-provider-auth openrouter
claude-provider-auth openrouter --status
claude-openrouter moonshotai/kimi-k3
```

`CLAUDE_CONFIG_DIR` isolates provider credentials and session state from normal `claude`. The launcher links the existing global `CLAUDE.md`, settings, keybindings, skills, and plugins into the isolated directory when those sources exist.

## Featherless

Featherless exposes `https://api.featherless.ai/v1` as an OpenAI-compatible API. Claude Code speaks Anthropic Messages, so a direct base URL override is not sufficient. `claude-featherless` starts the approved CLIProxyAPI binary with a private temporary configuration, one selected model, a random loopback port, and no management API. It stops the translator and removes the temporary configuration when Claude exits.

Official API guide: https://featherless.ai/docs/quickstart-guide

Enroll and verify without printing the key:

```bash
claude-provider-auth featherless
claude-provider-auth featherless --status
claude-featherless empero-ai/Qwythos-9B-Claude-Mythos-5-1M
```

The model slug is passed unchanged. The effective context is the lower of the live Featherless deployment limit and the account plan limit. Do not infer a 1M deployed context from a model name. Check Featherless model and plan metadata when context errors occur.

Featherless requires the already-approved CLIProxyAPI binary at `~/cliproxyapi/current/cli-proxy-api`, plus `curl`, `jq`, and Python 3. Missing dependencies are a stop condition, not permission to install them.

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

Observed 2026-08-31:

- Canonical ownership moved from machine onboarding into `$infra-i-manage-claude-provider-routes` without changing the installed Codex or Kimi launcher behavior.
- Mattbook installed `claude-provider`, `claude-provider-auth`, `claude-openrouter`, and `claude-featherless` under `~/.local/bin`; installed digests match canonical source.
- Focused tests passed for OpenRouter environment isolation, missing-credential refusal, Featherless loopback translation startup, exact model-slug forwarding, argument forwarding, credential status, and installer symlinks.
- OpenRouter and Featherless credentials are not enrolled on Mattbook, so live provider requests remain pending explicit target-local enrollment.

### Paths

- Versioned binary: `~/cliproxyapi/<version>/cli-proxy-api`
- Stable release link: `~/cliproxyapi/current`
- Config: `~/cliproxyapi/config.yaml`, mode `0600`
- Local client credential: `~/cliproxyapi/client-token`, mode `0600`
- OAuth directory: `~/.cli-proxy-api`, mode `0700`; credential files mode `0600`
- Launcher: `~/.local/bin/claude-codex`
- Launcher shortcuts: `~/.local/bin/claude-codex-{high,xhigh}`
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

`claude-kimi-proxy` preserves the older CLIProxyAPI Kimi OAuth route. CLIProxyAPI translates Claude messages and tool calls, refreshes Kimi OAuth, and exposes proxy model `kimi-k3`. This route is experimental but passed a live Primary machine Claude Code request on 2026-07-19.

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
- `claude-kimi-proxy` defaults to Claude effort `max`, mapped by Kimi to K3 `max` thinking.
- `claude-kimi-proxy --normal` uses Claude effort `high`, mapped to K3 `high` thinking.
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

After launch, run `/status`. Expected Base URL: `http://127.0.0.1:8317`. Route banner must show `provider=Kimi-OAuth-Proxy` and `model=kimi-k3(...)`.

Live smoke test:

```bash
claude-kimi-proxy -p --max-turns 1 \
  'Reply with exactly: CLAUDE_KIMI_PROXY_OK'
```

Expected response: `CLAUDE_KIMI_PROXY_OK`.

### Failure and OAuth refresh

- Missing `kimi-k3`: rerun CLIProxyAPI `--kimi-login`, restart service, and repeat model query.
- Authentication or entitlement error: verify Kimi Code benefit, OAuth device status, and 256K versus 1M entitlement.
- Preserve OAuth records for diagnosis. Delete or replace only after explicit confirmation.
- Never copy OAuth records into shell profiles, Claude settings, vault, tickets, or chat.
