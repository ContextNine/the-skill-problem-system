---
name: fleet-i-manage-terminal-workspaces
description: Configures, audits, repairs, or explains fleet terminal environments across Warp, cmux, tmux, workmux, btop, Starship, terminal profiles, saved workspaces, reconnect behavior, and retired agent notifications. Use for terminal workspace setup, Warp or cmux layout changes, persistent remote shells, T3 SSH terminal integration, workmux recovery, or terminal-profile deployment on registered machines.
---

# Fleet · Manage Fleet Terminal Workspaces

Read [Warp, cmux, and tmux Terminal Workspaces](references/cmux-tmux-terminal-workspaces.md) for architecture, deployment, verification, persistence, and rollback.

User-facing shortcuts are consolidated in terminal-keybindings. Daily commands remain in Terminal Docs. Keep deployment and recovery references inside this skill so distributed copies remain self-contained.

- Use `$fleet-i-code-folder-and-computer-topology` and `fleet config` to load the canonical machine registry and private execution-chain observations. Do not duplicate machine IDs, aliases, homes, roots or routes in this skill.
- Read [Warp and cmux Execution Chain](references/README-warp-cmux-execution-chain.md) when explaining machine boundaries or frontend routing.
- Run `scripts/sync_terminal_profiles.py` for tmux, btop, Starship, workmux, and managed profile deployment. During new-machine onboarding, an explicitly named disabled target may be provisioned and verified with `--target MACHINE_ID --provision-disabled`; omitting the flag continues to reject disabled machines, and the flag never selects disabled machines implicitly.
- Run `scripts/configure_warp_machine_workspaces.py` and `scripts/configure_cmux_machine_workspaces.py` for primary-host layouts. During onboarding, use cmux `--target MACHINE_ID` so an unrelated offline fleet member cannot block creation and verification of the reviewed target workspace; ordinary calls continue applying and verifying the complete enabled layout.
- Keep every controller dry-run by default; use `--apply` only after reviewing exact targets and use `--verify` afterward.
- Read [Workmux Agent Notifications](references/README-workmux-notifications.md) before touching notification hooks. Notifications remain retired and disabled unless the user explicitly asks to re-enable them.
- This skill never owns general Codex or Claude user configuration. Its retired notification helper may merge or remove only its own hook keys; `$fleet-i-sync-code-workspaces` remains authoritative for full user settings and instructions.
- During new-machine work, return gate status to `$fleet-i-onboard-machine`; this skill does not own machine registration, WireGuard, SSH enrollment, or registry enablement.
