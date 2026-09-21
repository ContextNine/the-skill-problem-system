---
name: fleet-i-sync-code-workspaces
description: Synchronizes registered Code workspaces and primary-owned Codex and Claude configuration across fleet machines. Use when the user asks to sync or refresh Code folders, prepare a new machine's workspaces, reconcile moved repositories, update agent settings on another machine, inspect workspace sync history, or verify remote workspace readiness.
---

# Fleet · Sync Code Workspaces

Read `$fleet-i-code-folder-and-computer-topology` and every prerequisite it requires before operating.

Read GitHub Fleet Authentication before changing GitHub remotes or diagnosing GitHub authentication.

Read [Platform Runtime](references/platform-runtime.md) before running the workflow. Fleet renders that reference for the selected machine during installation.

1. Run `fleet config validate`, then load `fleet/machines.json` and schema-v3 `fleet/workspaces.json` below the resolved config path. Workspace paths are relative to each selected machine's registered Code root. Optional `development` targets are repository-specific and non-secret. Keep missing or invalid configuration inactive.
2. Read [Workspace Sync Commands](references/workspace-sync-commands.md) for modes, command syntax, safety gates, and post-sync checks.
3. Read [Catalog Schema](references/catalog-schema.md) before changing catalog entries, profiles, machine filters, or clone policy.
4. Read [State and Reconciliation](references/state-and-reconciliation.md) before adopting source moves, relocating target checkouts, or inspecting run history.
5. Read [Fleet Agent Configuration Sync](references/agent-configuration-sync.md) before changing managed Codex or Claude files, eligibility, role overlays, or onboarding integration.
6. Read [Fleet Codex Plugin Reconciliation](references/plugin-reconciliation.md) before changing plugin inventory, marketplace handling, ownership state, or readiness reporting.
7. The scripts preflight every selected target before any apply. Use their explicit preview modes when the user asks for a dry run.

The editable global instruction base and its colocated templates live in `edit/agent-instructions/`. `fleet sync` is the sole default-apply entrypoint. It resolves settings from `edit/settings/` and renders exact absolute Code and Vault roots for the selected machine.

Use `reconcile` for normal repeat synchronization and during onboarding. `bootstrap` remains available for first-run clone behavior; `refresh` updates existing clean workspaces; `doctor` verifies without mutation. Use `migrate-github-remotes` only after every selected machine passes dedicated GitHub SSH verification; it changes same-identity transport on the source and targets with rollback and history. After an authorized GitHub repository transfer, use `transfer-github-owner` with the exact old and new owners. It requires GitHub to resolve both slugs to the same immutable repository ID before updating the source, targets, and catalog.

Never copy working trees, `.git`, credentials, sessions, plugin caches, marketplace snapshots, or the whole Code directory between machines. Never reset, stash, clean, force-update, switch an existing branch, change repository identity, or use GUI access as an authentication fallback. Remote transport may change only through the documented same-identity reconciliation path. Repository ownership may change only through the explicit owner-transfer path after the provider transfer is complete and numeric identity is verified.
