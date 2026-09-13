---
name: vault-i
description: Locate and use Matt Derman's personal Workspace vault containing tasks, projects, epics, library notes, Impression knowledge, personal brand material, and personal notes. Use when the user asks for vault context, Workspace notes, personal knowledge, Impression notes, task/project/epic routing, TaskNotes tasks, or Matt Derman-specific reference material.
---

# Vault

## Host gate

On Linux, run `vault access status` before reading or editing the Vault. Continue only when it succeeds and reports `"ok": true`; otherwise stop. Macs need no access ceremony. Read Primary and Worker Vault Coordination for the full host, iCloud, SSHFS, and Git model.

## Enter the Installed Vault

Resolve the installation through the dispatcher; never hard-code an iCloud or `~/Code` path:

```bash
cd "$(vault root)"
```

Read root `AGENTS.md`, then run `vault inventory` as the live routing source. It prints periods, default capture, context/source paths, task state, epics, and projects. Add `--json` when machine parsing helps.

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

Inventory reads tasks, projects, epics, and contexts live. Run `vault refresh --skip-git-maintenance` only when Dashboard, schedules, or periodic views should regenerate.

Every completed Vault task reaches the primary Mac, where it stages, commits, and pushes the entire current worktree, including unrelated, incomplete, generated, and incidental `.obsidian` changes. Follow root `AGENTS.md` for media verification, final fetch/merge, and push commands. Do not report completion before the push succeeds or an exact blocker is identified.

## Google Calendar

Use `$gws-i-custom-calendar` for Google Workspace authentication, calendar reads, concrete events, and explicit time blocks. Calendar work calls `gws` directly and is not part of the `vault` command.

## Skills

Vault-owned skills live under grouped `_system/agents/edit/skills/<_group>` folders; implicit skills use `-i-` after the category token and manual skills omit it. GitHub-managed installs live under `_system/agents/edit/skills/github/<repo-name>/skills`.
`_system/agents/internal/generated/catalog` is the generated flat symlink-only catalog. Never install content there.
Organizer folders use `_lower-kebab` and may nest. Skill folder basename must match `SKILL.md` frontmatter name. Names must be globally unique.
Run `fleet sync --dry-run`, then `fleet sync`. Sync validates invocation naming, builds required overlays or prefixed snapshots, rebuilds the Vault-local catalog, and distributes skills without importing discovery-target content.
GH source updates are owned by `fleet update --skills`; local checkout enrollment is independently owned by `skill-sources.json`. Public Vault dependencies remain under `_system/deps`.
Restart Codex or open new task after sync because current task caches catalog.

Repo-local `.agents/skills` folders are real directories reserved for repo-scoped skills and should not be symlinked. Repo `.claude/skills` may symlink to `../.agents/skills` so Claude reads those same repo-scoped skills.

If the user asks to create or update a skill, use the appropriate root `_group` and follow `$agents-i-write-or-edit-a-skill`.

If user asks to store a skill but not make it discoverable, use `_system/agents/edit/skills/dormant`.

Skill changes do not require generated agent-context refresh; routing comes from source skills and live inventory.

## Public Vault Export

If user says "publish the public vault", "release the public vault", or similar:

1. Finish requested source-vault changes first.
2. Run `vault release publish --dry-run --bump patch` and inspect the planned SemVer, dependency lock hash, and public repo actions.
3. Run `vault release publish --bump patch` unless the user requested `--bump minor`, `--bump major`, or `--version X.Y.Z`.
4. Read `export_root` from `_system/bootstrap/bootstrap-export.json`; confirm resolved export repo is clean and GitHub release/tag exists.

This updates `MDerman/the-context-vault-template` from the source vault export, bumps `_system/bootstrap/release.json`, snapshots `_system/local/dependencies.lock.json`, commits public export, tags `vX.Y.Z`, pushes, and creates a GitHub Release.

Use `vault bootstrap-export --force` only for local export inspection or exceptional manual repair. Public releases must use `vault release publish` so installed vaults can report installed and attempted upgrade versions.
