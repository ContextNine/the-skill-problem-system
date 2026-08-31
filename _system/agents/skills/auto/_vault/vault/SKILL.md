---
name: vault
description: Locate and use Matt Derman's personal Workspace vault containing tasks, projects, epics, library notes, Impression knowledge, personal brand material, and personal notes. Use when the user asks for vault context, Workspace notes, personal knowledge, Impression notes, task/project/epic routing, TaskNotes tasks, or Matt Derman-specific reference material.
---

# Vault

## Host Gate — Do This First

Before reading any task-specific Vault file, resolve machine identity and the schema-v7 Vault mode. Valid modes are the registered primary's full iCloud worktree with external Git, a registered Gitless iCloud Mac worktree, or a registered full `remote-sshfs` client whose status proves the exact source, read-write mount, sentinel, and iCloud health. A code-only host, retired clone, sparse checkout, arbitrary Linux path, missing mount, wrong source, read-only mount, degraded iCloud state, or unresolved identity follows [[README-vault-host-boundary|Vault Host Boundary]] and stops.

## Enter the Installed Vault

Resolve the installation through the dispatcher; never hard-code an iCloud or `~/Code` path:

```bash
cd "$(vault root)"
git config --local --get vault.machine-id 2>/dev/null || cat "$HOME/.config/vault/machine-id"
vault access status
```

Read root `AGENTS.md` before task-specific Vault access. On a remote client, status is mandatory before reads. Before any remote or managed direct-Mac write, close unmanaged Vault writers and acquire the shared lease:

```bash
vault access begin --task-id TASK_OR_THREAD_ID
```

Finish every leased edit session:

```bash
vault access finish
```

`vault access finish` returns after host filesystem durability and lease release. It never waits for iCloud upload; receipts and upload state are diagnostic only. A remote client never runs Vault Git, refresh, release, agents sync, bootstrap publication, or Git-backed media maintenance, and it never claims `git-pushed`. Normal Git remains allowed in its ordinary Code repositories. A Gitless iCloud worker has the same Vault Git prohibition. The registered Git owner commits and pushes the complete worktree currently visible to it without waiting for a receipt.

Then run `vault inventory` as the live routing source. It prints periods, default capture, context/source paths, task state, epics, and projects. Add `--json` when machine parsing helps.

## Low-Context Lookups

Use `rg` filename-first, then inspect only frontmatter/opening notes:

```bash
sed -n '1,60p' "impression/_obsidian/tasks/starter-task.md"
```

Prefer inventory output and existing names over remembered examples. Useful focused queries:

```bash
rg -l '^status: in-progress$' */_obsidian/tasks 2>/dev/null | head -20
rg -l '^status: (idea|cogs-are-turning|draft|planning-scripting|scheduled)$' */_obsidian/content/items 2>/dev/null | head -20
```

If exact Obsidian Base drag order matters, check `tasknotes_manual_order` or use the Base in Obsidian.

Create routed TaskNotes task using existing names from inventory:

```bash
vault task create impression "Task title" --project "Existing Project" --epic "Existing Epic" --status backlog --priority normal
```

Useful optional task flags: `--due YYYY-MM-DD`, `--scheduled YYYY-MM-DD`, `--time-estimate MINUTES`, `--body TEXT`, `--dry-run`.

Create missing routing objects:

```bash
vault project create impression "New Project" --epic "Existing Epic" --status backlog
vault epic create impression "New Epic" --status in-progress
vault folder --name 06-new-context --status active
```

Inventory reads tasks, projects, epics, and contexts live. Run `vault refresh --skip-gcal --skip-git-maintenance` only when Dashboard, schedules, or periodic views should regenerate.

Every completed Vault task reaches the primary Mac, where it stages, commits, and pushes the entire current worktree, including unrelated, incomplete, generated, and incidental `.obsidian` changes. Follow root `AGENTS.md` for media verification, final fetch/merge, and push commands. Do not report completion before the push succeeds or an exact blocker is identified.

## Google Calendar

Create specific calendar events on the default Google Calendar:

```bash
vault gcal create-event --title "Event title" --start "2026-06-02T19:30" --end "2026-06-02T20:30"
```

Use `vault gcal create-event` for appointments, travel, meetings, reservations, and other concrete dated events. It writes to `primary` unless `--calendar` or `_system/local/calendar.json` says otherwise.

Use `vault gcal create-block` only when user explicitly asks for time blocking or broad planning blocks on `Time Blocks`.

## Skills

Implicit skills live under grouped `_system/agents/skills/auto`; explicit-only skills under grouped `_system/agents/skills/manual`; GitHub-managed installs under `_system/agents/skills/github`.
`_system/agents/skills/catalog` is the generated flat symlink-only catalog. Never install content there.
Organizer folders use `_lower-kebab` and may nest. Skill folder basename must match `SKILL.md` frontmatter name. Names must be globally unique.
Run `ctx9-agents sync --dry-run`, then `ctx9-agents sync`. Sync enforces auto/manual invocation policy, updates moved dependency projections, rebuilds the Vault-local catalog, and distributes point-in-time skill copies without importing discovery-target content.
External agent skill sources and repo projections are independently owned by `ctx9-agents update --skills` and `ctx9-agents sync --skills`; public Vault dependencies remain under `_system/deps`.
Restart Codex or open new task after sync because current task caches catalog.

Repo-local `.agents/skills` folders are real directories reserved for repo-scoped skills and should not be symlinked. Repo `.claude/skills` may symlink to `../.agents/skills` so Claude reads those same repo-scoped skills.

If user asks to create/update an implicit skill, work under `_system/agents/skills/auto`. If explicit-only, use `_system/agents/skills/manual`.

If user asks to store a skill but not make it discoverable, use `_system/agents/skills/dormant`.

Skill changes do not require generated agent-context refresh; routing comes from source skills and live inventory.

## Public Vault Export

If user says "publish the public vault", "release the public vault", or similar:

1. Finish requested source-vault changes first.
2. Run `vault release publish --dry-run --bump patch` and inspect the planned SemVer, dependency lock hash, and public repo actions.
3. Run `vault release publish --bump patch` unless the user requested `--bump minor`, `--bump major`, or `--version X.Y.Z`.
4. Read `export_root` from `_system/bootstrap/bootstrap-export.json`; confirm resolved export repo is clean and GitHub release/tag exists.

This updates `MDerman/the-context-vault-template` from the source vault export, bumps `_system/bootstrap/release.json`, snapshots `_system/local/dependencies.lock.json`, commits public export, tags `vX.Y.Z`, pushes, and creates a GitHub Release.

Use `vault bootstrap-export --force` only for local export inspection or exceptional manual repair. Public releases must use `vault release publish` so installed vaults can report installed and attempted upgrade versions.
