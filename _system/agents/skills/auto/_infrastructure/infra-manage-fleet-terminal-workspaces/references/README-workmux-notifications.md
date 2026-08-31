---
type: agent-reference
status: disabled
---
# Workmux Agent Notifications

Durable completion notifications for top-level Codex and Claude turns running inside managed tmux sessions are retired and disabled by default.

The retained-queue design caused old completion events to arrive in a burst when Warp opened after being absent. Fleet sync therefore defaults to `disabled`; do not re-enable notifications unless the user explicitly requests them.

## Retired architecture

```text
Codex `notify` / Claude `Stop` hook
  -> ~/.local/bin/workmux-notify enqueue
    -> atomic local outbox event
      -> Primary machine LaunchAgent every 15 seconds
        -> local read or WireGuard SSH export
          -> choose one available frontend
            -> Warp-branded macOS notification when Warp runs
            -> exact cmux workspace/main surface when Warp is absent
            -> delivered-ID ledger
              -> source acknowledgment and deletion
```

Primary machine pulls remote queues through each machine's explicit `-mesh` diagnostic alias. The selected provider may be WireGuard or Tailscale; notification configuration never derives a provider-specific alias. Primary machine exposes no listener. Poller selects frontend before contacting sources. Warp wins when its main process runs; clicking notification activates Warp. If Warp is absent, cmux receives exact surface notification when available. If neither frontend is available, source queues remain untouched. Delivery is at least once; process failure between frontend acceptance and ledger write may create duplicate, never intentional loss.

Codex uses its `notify` completion command because it also covers noninteractive `codex exec`; Primary machine notifier chains existing Computer Use callback after queueing. Claude uses only top-level `Stop`; `SubagentStop` remains untouched. Event files contain agent, machine, project basename, UTC time, and tmux session/window metadata. Assistant response text and full working-directory paths are not stored.

## Managed files

Canonical sources:

- `assets/terminal-workspaces/workmux-notify`
- `scripts/sync_agent_notifications.py`
- `scripts/test_workmux_notify.py`
- `scripts/test_sync_agent_notifications.py`

Files deployed while enabled:

- `~/.local/bin/workmux-notify`
- `~/.config/workmux/notifications.json`
- managed `notify` command merged into `~/.codex/config.toml`
- obsolete workmux Codex `Stop` entry removed from `~/.codex/hooks.json`; unrelated cmux/user hooks preserved
- managed `Stop` entry merged into `~/.claude/settings.json`
- Primary machine only: `~/Library/LaunchAgents/com.ctx9.workmux-notifications.plist`
- Primary machine Homebrew dependency: `terminal-notifier`

Every replaced file gets an adjacent UTC timestamp backup. Disable keeps the helper and a no-op config for already-running sessions, removes managed Codex/Claude hooks, archives queued state, and archives Primary machine's LaunchAgent plist. Existing unrelated hooks and Primary machine's separate Codex Computer Use callback remain intact.

## Disable or verify

Run from Primary machine. Default mode changes nothing.

```bash
SKILL_DIR="$(vault root)/_system/agents/skills/auto/_infrastructure/infra-manage-fleet-terminal-workspaces"

python3 "$SKILL_DIR/scripts/sync_agent_notifications.py" --state disabled
python3 "$SKILL_DIR/scripts/sync_agent_notifications.py" --state disabled --target linux-worker --apply
python3 "$SKILL_DIR/scripts/sync_agent_notifications.py" --state disabled --target linux-worker --verify
python3 "$SKILL_DIR/scripts/sync_agent_notifications.py" --state disabled --target secondary-mac --apply
python3 "$SKILL_DIR/scripts/sync_agent_notifications.py" --state disabled --target secondary-mac --verify
python3 "$SKILL_DIR/scripts/sync_agent_notifications.py" --state disabled --target primary --apply
python3 "$SKILL_DIR/scripts/sync_agent_notifications.py" --state disabled --target primary --verify
```

Disable remotes before Primary machine when they are reachable. Disabled config makes the installed helper a no-op for already-running agent processes, removes managed Codex and Claude hooks for new processes, archives queued event state, and unloads plus archives Primary machine's LaunchAgent plist. Unreachable remotes cannot produce desktop notifications after the Primary machine poller is disabled, but disable their local hooks when they return to avoid unused queue growth.

Explicit re-enablement remains available only for a future user-directed rollback:

```bash
python3 "$SKILL_DIR/scripts/sync_agent_notifications.py" --state enabled --target MACHINE --apply
```

## Historical operation and verification

```bash
workmux-notify status
workmux-notify export
launchctl print "gui/$(id -u)/com.ctx9.workmux-notifications"

ssh linux-worker-mesh '~/.local/bin/workmux-notify status'
ssh secondary-mac-mesh '~/.local/bin/workmux-notify status'
```

Synthetic source event:

```bash
printf '{"cwd":"/tmp/workmux-test"}\n' \
  | ssh linux-worker-mesh '~/.local/bin/workmux-notify enqueue --agent codex --event stop'
```

With Warp running, Primary machine poller sends one Warp-branded desktop notification and acknowledges remote file. With Warp closed and cmux running, same event routes to matching cmux `main` surface. With both closed, event remains queued.

Notification format:

- title: `Codex · Linux worker`
- subtitle: `Completed in workmux-test`
- body: `tmux 2:codex`, or `Turn complete` outside tmux

Verified 2026-07-22: Linux worker synthetic event delivered and acknowledged through Warp sink. After Warp quit, Secondary Mac synthetic event delivered and acknowledged through cmux fallback sink.

## Historical failure behavior

- Warp notification failure: source queue remains unchanged for next poll.
- Warp absent plus missing cmux socket: poll exits without contacting remotes.
- Warp absent plus missing cmux workspace or `main` surface: source queue remains unchanged.
- Selected mesh-route SSH failure: remote queue remains unchanged.
- Malformed local event: moved to mode-`0700` quarantine directory.
- Unknown remote machine ID or invalid schema: poll fails closed without acknowledgment.

The old system retained queues whenever neither frontend was available. That behavior is the reason it remains disabled. Timestamped hook/config backups and the archived LaunchAgent plist are retained for inspection; re-enable only through the explicit state command above.

To unload a stray legacy LaunchAgent manually:

```bash
launchctl bootout "gui/$(id -u)/com.ctx9.workmux-notifications"
```

Disabled rollout archives queued event state rather than deleting it. Do not restore that state during a future re-enable unless the user explicitly wants old completion events delivered.
