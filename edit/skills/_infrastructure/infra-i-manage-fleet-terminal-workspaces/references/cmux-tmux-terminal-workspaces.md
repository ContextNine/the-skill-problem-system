# Warp, cmux, and tmux Terminal Workspaces

Canonical architecture, deployment, operation, and recovery reference for Primary machine Warp-primary and cmux-fallback clients backed by persistent per-machine tmux sessions.

Conceptual execution chain with explicit machine boundaries: [[README-warp-cmux-execution-chain|Warp, cmux, and Workmux Execution Chain]].

## Contents

- [[#Architecture]]
- [[#cmux, Ghostty, TTY, and exec]]
- [[#Terminology]]
- [[#Keyboard model]]
- [[#Machine profiles]]
- [[#Managed files]]
- [[#Agent completion notifications]]
- [[#Deploy terminal profiles]]
- [[#Configure cmux layout]]
- [[#Configure Warp layout]]
- [[#Daily operation]]
- [[#Persistence model and limits]]
- [[#Verification]]
- [[#Rollback]]
- [[#Client reconnect policy]]

## Architecture

```text
Primary machine Warp (primary) or cmux (fallback)
  -> local tab or automatic SSH alias
    -> forced remote PTY
      -> workmux <machine-id>
        -> host-named tmux session
          -> 0:btop
          -> 1:shell
          -> later process-named windows: npm, codex, claude, ...
```

Warp is daily client. `Machine Workspaces` opens one controller-owned `main` tab for every enabled registry terminal profile. Primary machine attaches local `primary` tmux; remote tabs use the managed helper that runs absolute `/usr/bin/ssh` through automatic aliases, forces a TTY, executes exact remote `workmux`, retries transport exit `255`, and stops after clean tmux detach. Optional project shells are user-owned Warp Tab Configs opened from `+`; controller never reads or changes `~/.warp/tab_configs/`. This intentionally favors durable tmux over Warpify command Blocks inside tmux tabs.

cmux remains fallback. Use normal `cmux ssh`; do not use beta `cmux ssh-tmux`. Initial workspace creation uses absolute `workmux` plus `RequestTTY=force`. cmux `0.64.20` restores SSH workspace descriptors after relaunch but does not reliably replay remote commands. `workmux-cmux-attach` is a one-shot manual helper available through cmux Command Palette. No reconnect LaunchAgent or activation watcher runs.

## cmux, Ghostty, TTY, and exec

cmux is native Swift/AppKit macOS application built on Ghostty's terminal-rendering library, `libghostty`. It also reads Ghostty configuration for terminal themes, fonts, and colors. Standalone Ghostty app is not wrapping or hosting cmux: cmux owns window, sidebar, workspaces, surfaces, splits, notifications, SSH lifecycle, and browser; Ghostty engine renders terminal cells and interprets terminal control sequences inside cmux.

TTY means teletype terminal. Modern TTY is logical character terminal with input, output, dimensions, control characters such as `Ctrl+C`, and terminal behavior expected by interactive programs. PTY means pseudo-terminal: operating-system master/slave TTY pair used by terminal emulators, SSH, and tmux instead of physical teletype. cmux/libghostty faces local PTY; remote SSH allocates another PTY; tmux creates PTYs for panes. Explicit SSH remote commands normally may receive pipes instead, so managed remote workspace sets `RequestTTY=force`; tmux client then receives terminal it requires.

```text
keyboard/display
  cmux UI + libghostty renderer
    <-> cmux/SSH transport
      <-> remote PTY
        <-> tmux client
             |
             | Unix socket
             v
           persistent tmux server
             <-> pane PTY <-> shell | btop | Codex | npm | Claude
```

`workmux` is custom shell launcher built for this fleet setup, not third-party package. Canonical source is `assets/terminal-workspaces/workmux`; `sync_terminal_profiles.py` renders machine's default session name and deploys it as `~/.local/bin/workmux` on each host.

Warp and initial cmux remote creation launch `workmux` directly. Workmux briefly runs under shell interpreter, validates/repairs session, then runs `exec tmux attach-session`. Shell `exec` replaces current workmux shell process with tmux client. tmux server remains separate persistent host process. When Warp, cmux, or SSH disconnects, attached tmux client disappears; tmux server, pane PTYs, and programs keep running. Next Warp retry, Warp launch-config action, or cmux manual reconnect creates a new client for same session.

## Terminology

- **cmux window**: macOS app window. Current fleet layout uses one.
- **cmux workspace**: top-level sidebar item. Exactly one remains for each enabled registry terminal profile.
- **Pinned workspace**: workspace kept at top of sidebar. Pin is cmux metadata, unrelated to process persistence.
- **Surface**: tab inside cmux workspace/pane. One surface named `main` remains in each fleet workspace. `Cmd+T` creates another surface.
- **Pane**: visible split region. `Cmd+D` splits right; `Cmd+Shift+D` splits down.
- **cmux surface tab bar**: tabs across top of terminal area.
- **Warp launch configuration**: controller-owned registry-derived machine layout under `~/.warp/launch_configurations/`. Legacy format remains intentional because it opens the ordered tab group atomically.
- **Warp Tab Config**: user-owned reusable individual tab under `~/.warp/tab_configs/`; save existing optional tab with **Save as new config** and reopen it from `+`.
- **Warp remote tab**: classic interactive tmux client. Warp vertical tabs, titles, colors, workflows, and navigation remain; inner remote commands do not become Warp Blocks.
- **Ghostty/libghostty**: terminal rendering/configuration engine inside cmux; not workspace/session manager.
- **TTY / PTY**: logical terminal and pseudo-terminal device pair carrying interactive terminal input/output.
- **workmux**: fleet-owned bootstrap shell script that restores/repairs and attaches host tmux session.
- **tmux session**: terminal server state surviving client/SSH disconnect. Sessions are `primary`, `linux-worker`, and `secondary-mac`.
- **tmux window**: numbered full-screen terminal within tmux session. Bottom center lists these.
- **tmux pane**: split within tmux window. Managed initial layout does not add tmux splits.
- **tmux status line**: orange bar at bottom of screenshot. Left shows session and active Git branch, center shows windows, right shows CPU and memory.
- **shell prompt**: input prefix before command. Starship renders one compact line: machine name, current directory, optional Git branch/status, short SAST date/time, then `>`. Date/time uses `DD/MM HH:MM` and redraws with each new prompt. This is “colored prompts”; it changes prompt text, not all terminal output.
- **btop**: interactive resource monitor in tmux window `0`.

## Keyboard model

cmux shortcuts act outside tmux:

| Shortcut | Action |
| --- | --- |
| `Cmd+T` | Create surface/tab in current workspace. |
| `Cmd+D` | Split cmux pane right. |
| `Cmd+Shift+D` | Split cmux pane down. |
| `Cmd+Shift+P` | Open command palette and search current bindings. |
| `Cmd+Shift+,` | Reload cmux and Ghostty configuration. |

tmux keeps default prefix `Ctrl+b`. Press prefix, release, then key:

| Shortcut | Action |
| --- | --- |
| `Ctrl+b c` | Create tmux window; automatic name follows foreground process. |
| `Ctrl+b 0` / `Ctrl+b 1` | Select btop/shell window. |
| `Ctrl+b n` / `Ctrl+b p` | Next/previous tmux window. |
| `Ctrl+b ,` | Rename current window manually. |
| `Ctrl+b r` | Reload managed tmux config. |
| `Ctrl+b Ctrl+s` | Save tmux-resurrect snapshot now. |
| `Ctrl+b Ctrl+r` | Restore latest tmux-resurrect snapshot. |
| `Ctrl+b d` | Detach client; session continues. |

## Machine profiles

| Machine | ID/session | Transport | Accent |
| --- | --- | --- | --- |
| Primary machine | `primary` | Local | `#AD1457` magenta |
| Linux worker | `linux-worker` | Normal cmux SSH alias `linux-worker` | `#196F3D` green |
| Secondary Mac | `secondary-mac` | Normal cmux SSH alias `secondary-mac` | `#0E6B8C` aqua |
| Worker Mac | `worker-mac` | Normal cmux SSH alias `worker-mac` | `#6A1B9A` purple |

Shared tmux status colors: background `#101010`, accent `#FFAF5F`, muted text `#6F6F6F`. Prompt uses machine accent, dimmed-white SAST date/time, and no Nerd Font glyphs.

Verified 2026-07-19: Primary machine `tmux 3.7b`, `btop 1.4.7`, Starship `1.26.0`; Linux worker `tmux 3.6`, `btop 1.4.6`, Starship `1.22.1`; Secondary Mac `tmux 3.7b`, prebuilt `btop 1.3.2`, prebuilt Starship `1.26.0`.

Verified 2026-07-23: Primary machine and Linux worker prompts render matching `DD/MM HH:MM` SAST timestamps before `>`; deployed configs match canonical hashes. Secondary Mac canonical render contains same module; live deployment deferred while machine is offline.

Verified 2026-07-22: Warp launch URI opened both managed remote tabs; client-side SSH termination created new SSH processes within five seconds; clean detach exited without retry; full Warp quit/relaunch reattached unchanged sessions. Session IDs remained Primary machine `1784474079`, Linux worker `1784474165`, and Secondary Mac `1784726791`.

Final cmux contract:

- exactly one pinned workspace per enabled terminal profile, in registry order;
- exactly one terminal surface named `main` in each;
- compact sidebar shows one title-only line per workspace and hides notification messages, descriptions, branch/directory metadata, logs, and ports;
- sidebar font 12 pt; surface-tab font 11 pt.
- every SSH workspace uses a forced-PTY absolute workmux command initially and carries the `durable workmux` marker authorizing manual helper repair.

## Managed files

Canonical sources live beside this reference:

- `assets/terminal-workspaces/tmux.conf`
- `assets/terminal-workspaces/starship.toml.template`
- `assets/terminal-workspaces/workmux`
- `assets/terminal-workspaces/workmux-btop-control`
- `assets/terminal-workspaces/workmux-cmux-attach`
- `assets/terminal-workspaces/workmux-warp-attach`
- `assets/terminal-workspaces/workmux-warp-startup`
- `assets/terminal-workspaces/workmux-git-branch`
- `scripts/sync_terminal_profiles.py`
- `scripts/configure_cmux_machine_workspaces.py`
- `scripts/configure_warp_machine_workspaces.py`

Deployed on each machine:

- `~/.tmux.conf`
- `~/.config/starship.toml`
- `~/.local/bin/workmux`
- Primary machine `~/.local/bin/workmux-cmux-attach`
- Primary machine `~/.local/bin/workmux-warp-attach`
- Primary machine `~/.local/bin/workmux-warp-startup`
- `~/.local/bin/workmux-btop-control`
- `~/.local/bin/workmux-git-branch`
- Primary machine `~/.warp/launch_configurations/machine_workspaces.yaml`
- marker-managed Starship block in `.bashrc` on Linux worker or `.zshrc` on Macs;
- pinned plugins below `~/.local/share/workmux/plugins/`.

## Agent completion notifications

Agent completion notifications are retired and disabled. The former per-machine durable queues intentionally accumulated while Warp and cmux were absent, then flooded Warp when it opened. The retained implementation, disabled-state rollout, and explicit re-enable path remain documented in [[README-workmux-notifications|Workmux Agent Notifications]].

Plugin commits:

- tmux-resurrect: `cff343cf9e81983d3da0c8562b01616f12e8d548`
- tmux-continuum: `0698e8f4b17d6454c71bf5212895ec055c578da0`
- tmux-cpu: `bcb110d754ab2417de824c464730c412a3eb2769`

Package ownership:

- macOS and Linux: `_system/agents/internal/defaults/dependencies.json` owns `tmux`, `btop`, `starship`, and macOS `terminal-notifier`. Secondary Mac remains disabled; its historical prebuilt details are observation-only.
- Historical Linux package observations remain in [[linux-worker-image|Linux Worker Image]].
- Secondary Mac uses `/usr/local/bin/brew` explicitly. Managed links expose Homebrew commands through `~/.local/bin` because its SSH PATH omits `/usr/local/bin`.

## Deploy terminal profiles

Run from Primary machine:

```bash
SKILL_DIR="$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-manage-fleet-terminal-workspaces"

# All enabled fleet targets; no changes.
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py"

# Pilot and verify in order.
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py" --target NEW_MACHINE --provision-disabled --apply
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py" --target NEW_MACHINE --provision-disabled --verify
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py" --target linux-worker --apply
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py" --target linux-worker --verify
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py" --target secondary-mac --apply
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py" --target secondary-mac --verify
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py" --target primary --apply
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py" --target primary --verify
```

Script reads enabled fleet entries with terminal profiles from the private machine registry. Default mode is dry-run. `--target` repeats and accepts ID or display name. A new-machine workflow may add `--provision-disabled` only with explicit targets so terminal acceptance can finish before registry enablement; normal calls continue rejecting disabled machines. Changed files receive adjacent UTC timestamp backups before atomic replacement.

APT or detected machine-specific Homebrew installs missing packages. Secondary Mac uses checksum-pinned prebuilt btop and Starship artifacts; it never builds LLVM for this profile. Stop rollout if artifact checksum, binary launch, package, or config verification fails. Do not continue to shell or cmux cleanup after failure.

## Configure cmux layout

Run only after all three terminal profiles verify:

```bash
python3 "$SKILL_DIR/scripts/configure_cmux_machine_workspaces.py"
python3 "$SKILL_DIR/scripts/configure_cmux_machine_workspaces.py" --apply
python3 "$SKILL_DIR/scripts/configure_cmux_machine_workspaces.py" --verify

# New-machine acceptance while another enabled fleet member is offline.
python3 "$SKILL_DIR/scripts/configure_cmux_machine_workspaces.py" --target NEW_MACHINE --apply
python3 "$SKILL_DIR/scripts/configure_cmux_machine_workspaces.py" --target NEW_MACHINE --verify
```

Dry-run prints retained/closed surfaces and workspace actions. Apply backs up `~/.config/cmux/cmux.json`, installs marker-managed compact sidebar and saved Command Palette entries, deploys manual reconnect helper, boots out and archives obsolete reconnect LaunchAgent plist, sets font sizes, validates config, and reloads it. `--target` still preserves and orders the complete registered layout but reconnects, mutates, and checks terminal health only for the exact enabled target; use it when an unrelated retained fleet member is offline during onboarding.

Primary machine retained local surface becomes `main` and runs `exec workmux primary`. New remote workspaces use durable commands rendered from their registry profile:

```bash
cmux ssh <ssh-alias> --name "<display-name>" --ssh-option RequestTTY=force -- <remote-home>/.local/bin/workmux <machine-id>
cmux ssh <ssh-alias> --name "<display-name>" --ssh-option RequestTTY=force -- /usr/bin/env PATH=<remote-path> <remote-home>/.local/bin/workmux <machine-id>
```

Legacy remote workspaces without a `durable workmux` description marker migrate transactionally. Controller creates a replacement workspace under a temporary migration title, waits until the replacement surface visibly contains the session name, `0:btop`, `1:shell`, CPU, and MEM, verifies the pane process, then closes the old idle/managed surface and renames the replacement. Failed replacement leaves the old workspace open. Active unknown full-screen programs block migration. The marker authorizes one-shot helper repair. Controller closes obsolete `Machines`, pins/colors/describes all registered machine workspaces, orders them, then checks the final tree.

## Configure Warp layout

```bash
SKILL_DIR="$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-manage-fleet-terminal-workspaces"

python3 "$SKILL_DIR/scripts/configure_warp_machine_workspaces.py"
python3 "$SKILL_DIR/scripts/configure_warp_machine_workspaces.py" --apply
python3 "$SKILL_DIR/scripts/configure_warp_machine_workspaces.py" --verify
```

Controller preserves `main_workspace_launch_config.yaml`, every user-owned Warp Tab Config, and unrelated Warp/shell settings; requires vertical tabs enabled; disables stale session restoration; deploys registry-derived `Machine Workspaces`; installs `workmux-warp-attach` plus the one-shot startup trigger; and archives obsolete per-machine launchers. It validates Warp's limited color enum before writing the launch file. Primary machine main is active and runs absolute local `workmux primary`. Open manually from Warp `+` menu or:

```bash
open 'warp://launch/Machine%20Workspaces'
```

Remote helper uses automatic aliases so each new attempt selects LAN when reachable and the registry-selected mesh provider otherwise. Exit `255` retries in five seconds. Clean tmux detach returns zero and stops helper. Non-transport workmux failure exits visibly instead of looping.

Warp itself has no native default-launch-configuration setting. The marker-managed `.zshrc` block starts `workmux-warp-startup` only for Warp shells. The trigger identifies the parent Warp process, claims that exact process once, waits for restored helpers, and opens the launch URI only when the canonical helpers are absent. It then derives every enabled remote profile from the runtime registry, polls for all corresponding helpers for up to 20 seconds, and sends HUP only to the originating startup shell while that shell remains idle, so Warp closes the default blank window and leaves one canonical window without interrupting a foreground command. Every managed launch pane starts in its registry-ID marker directory, preventing URI recursion. Old Home, Workspace, and Impression marker directories are removed only when empty. No LaunchAgent, polling daemon, or app activation watcher runs.

Warp now recommends Tab Configs for reusable individual tabs. Keep legacy launch configuration only for atomic ordered three-machine startup. Save any extra tab through its context menu with **Save as new config**; reopen it manually from `+`. Optional Tab Configs do not auto-open and remain outside controller ownership.

Official Warp references: `https://docs.warp.dev/terminal/windows/tab-configs` and `https://docs.warp.dev/terminal/sessions/launch-configurations`.

Unexpected workspace names stop destructive cleanup. Rename/remove intentionally, then rerun.

## Daily operation

Starting Warp automatically opens `Machine Workspaces` once with one `main` tab per enabled terminal profile. Active Primary machine main attaches local tmux; remote tabs attach their corresponding tmux sessions and retry transport failures while tabs stay open. The startup helper derives the complete enabled remote set from the runtime registry before closing the originating blank shell. Open optional user-owned Tab Configs from `+`. Use `Ctrl+b d` for intentional clean detach. Warp session restoration stays disabled so stale windows cannot compete with the canonical startup layout.

In cmux, initial creation attaches directly. After cmux relaunch or workspace reconnect leaves plain remote shell, run Command Palette entry `Reconnect machine tmux`. One-shot helper ignores unmarked workspaces and active unknown screens, repairs only managed idle/disconnected `main` surfaces, then exits.

When target session is absent, `workmux` takes per-session restore lock and performs one explicit tmux-resurrect restore through temporary bootstrap session. If no saved target session exists, it creates `0:btop` and `1:shell`, leaves `shell` selected, and pins those two names. On existing sessions it preserves selected window and creates only missing base windows. If named `0:btop` runs shell after stale restore, workmux safely respawns that pane with absolute btop path. Unexpected window `0` names stop repair instead of overwriting work. Later windows remain untouched and use tmux automatic foreground-process naming.

Managed btop runs at a one-second refresh interval. tmux hooks replace it with an idle `sleep` process while window `0:btop` has no active tmux client, then start fresh btop when selected again. This reduces hidden-window CPU use and avoids long-lived macOS btop Runner-thread stalls. tmux can detect its own selected window, not whether outer Warp tab is visible.

Use one tmux window per long-lived activity. Example: `Ctrl+b c`, then run `codex`; window becomes `codex`. Disconnecting SSH or closing/reopening cmux client does not stop tmux server or its child processes.

Starship appears at ordinary shell prompts as `Machine directory git status DD/MM HH:MM >`. Git status symbols include `!` for modified tracked files and `?` for untracked files. Timestamp is fixed to UTC+2/SAST for fleet consistency and updates when next prompt renders, not continuously while idle. btop, Codex, Claude, npm, full-screen TUIs, and program output control their own text and colors.

## Persistence model and limits

Three levels differ:

1. tmux server survives client and SSH disconnect while host remains running.
2. tmux-continuum saves session/window/pane/CWD layout every 15 minutes. Its automatic restore is disabled to prevent competing restores.
3. On next workmux startup, one locked explicit tmux-resurrect restore reconstructs layout, working directories, and allowlisted `btop` process. It does not preserve process memory.

Reboot or tmux server termination kills live programs. Restore reconstructs safe layout. `btop` can restart. Codex, Claude, npm, and other coding/development processes are deliberately not blindly restarted. Agent transcripts, terminal scrollback, unsaved editor state, and in-memory servers are not persistence guarantees. Resume coding-agent conversations through each tool’s own history/resume mechanism.

Warp helper retries transient SSH transport failures. Full Warp relaunch automatically opens canonical launch configuration once. cmux remote PTY can survive transient transport disconnect, but full cmux relaunch restores ordinary SSH shell on observed build and needs manual saved command. Nested tmux provides explicit session lifecycle independent of either client.

## Verification

Profile verification:

```bash
python3 "$SKILL_DIR/scripts/sync_terminal_profiles.py" --verify
ssh linux-worker 'bash -lc "command -v tmux btop starship workmux; tmux -V; starship --version"'
ssh secondary-mac 'zsh -lc "command -v tmux btop starship workmux; tmux -V; starship --version"'
zsh -lc 'command -v tmux btop starship workmux; tmux -V; starship --version'
```

Fresh restore test on each host:

1. Run `workmux <machine-id>`.
2. Save with `Ctrl+b Ctrl+s`.
3. Detach with `Ctrl+b d`.
4. Confirm `tmux has-session -t =<machine-id>`.
5. For a fresh managed test only, terminate that test server/session, run `workmux`, and confirm layout returns. Never kill unrelated sessions.

Client checks:

```bash
cmux config doctor
cmux reload-config
cmux tree --all --json
python3 "$SKILL_DIR/scripts/configure_cmux_machine_workspaces.py" --verify
python3 "$SKILL_DIR/scripts/configure_warp_machine_workspaces.py" --verify
! launchctl print "gui/$(id -u)/com.ctx9.workmux-cmux-attach"
```

Visually confirm Warp vertical tabs, one managed title/color/directory and orange tmux status line per enabled profile, matching prompt accents, and CPU/MEM values. Confirm user Tab Config files remain unchanged and optional tabs reopen manually from `+`. Kill only a client-side SSH process to test automatic retry; never kill the tmux server. Cleanly detach and confirm the helper stops. Quit/relaunch Warp and confirm the canonical workspace opens without manual action, then compare `#{session_created}`.

For cmux fallback, confirm the compact sidebar, one pinned machine workspace/color and one `main` surface per enabled profile, saved commands in Command Palette, and no reconnect LaunchAgent. After cmux relaunch, invoke the manual reconnect command and compare the same session IDs. Verification must accept `btop` while selected or managed `sleep` while hidden from `#{pane_current_command}`; the window name alone is insufficient.

## Rollback

Every changed config or shell RC gets adjacent `.backup-YYYYMMDDTHHMMSSZ`. Restore wanted backup with `mv`, then reload shell/tmux/cmux. Plugin replacement keeps timestamped old directory beside installed plugin.

To remove shell integration, delete only text between `# >>> workmux starship >>>` and `# <<< workmux starship <<<`. Do not replace unrelated shell configuration.

To stop using managed sessions without deleting saved state:

```bash
tmux detach-client -s primary  # substitute host session
```

Remove managed files or plugins only after separate authorization. cmux workspace closures are not recovered by terminal profile backups; cmux app session restoration may retain local metadata, but do not treat it as rollback guarantee.

## Client reconnect policy

`~/.config/cmux/cmux.json` must keep automation socket mode and empty-workspace preservation alongside managed sidebar block:

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/manaflow-ai/cmux/main/web/data/cmux.schema.json",
  "schemaVersion": 1,
  "automation": { "socketControlMode": "automation" },
  "app": { "keepWorkspaceOpenWhenClosingLastSurface": true }
}
```

Warp reconnect belongs to foreground `workmux-warp-attach` process inside each remote tab. Marker-managed Warp-only shell RC block opens canonical launch configuration once per new Warp process; it does not attach tmux itself. No LaunchAgent, activation watcher, polling daemon, or Warpify layer participates.

`~/Library/LaunchAgents/com.ctx9.cmux-ssh-policy.plist` still sets `CMUX_SSH_RECONNECT_LIMIT=0` before cmux launches. cmux reconnect uses saved Command Palette helper only. Do not recreate old Keyboard Maestro activation/title-change macro or `com.ctx9.workmux-cmux-attach` LaunchAgent.

Observed 2026-07-22 on cmux `0.64.20` build `100`: signed Auto `surface resume` bindings survived `workspace disconnect`, but `workspace reconnect` cleared binding and opened ordinary remote shell instead of running `workmux`. Pilot bindings and approval records were cleared. Manual helper is fallback contract.

Manual controls:

```bash
launchctl getenv CMUX_SSH_RECONNECT_LIMIT
cmux workspace disconnect
cmux workspace reconnect
cmux ssh-session-list --json
```

Managed remote workspace creation:

```bash
cmux ssh <ssh-alias> --name "<display-name>" --ssh-option RequestTTY=force -- <remote-home>/.local/bin/workmux <machine-id>
cmux ssh <ssh-alias> --name "<display-name>" --ssh-option RequestTTY=force -- /usr/bin/env PATH=<remote-path> <remote-home>/.local/bin/workmux <machine-id>
```

cmux targets automatic SSH aliases, so next connection chooses LAN or WireGuard. Live SSH connection does not migrate routes. Full SSH alias rebuild detail remains in [[primary-mac-remote-access-prerequisites|Primary machine Remote Access Prerequisites]].
