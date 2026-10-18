---
type: agent-reference
status: enabled
---

## State and Reconciliation

### Identity and desired paths

The canonical remote identity is the stable repository key; the Code-relative catalog path is desired fleet layout. URL credentials, query strings, fragments, local remotes, and ambiguous remotes are never persisted or used for relocation.

Transport is desired state but is not repository identity. A literal same-identity URL that differs from the catalog is `transport-drift`. The migrator reads the literal `remote.<name>.url` so a global `insteadOf` rewrite cannot hide drift. It updates only the unambiguous named remote after fleet-wide access preflight, verifies the literal URL and remote access, and restores the old sanitized URL if verification fails. An idempotent second pass returns `transport-current`.

For an exact catalog entry whose source path is missing, discovery scans the selected machine's resolved Code root for its configured remote. One match is reported as catalog drift. Multiple matches block adoption. `--adopt-source-layout` permits the detected path for preview; with `--apply`, it atomically updates that Code-root-relative entry in private `fleet/workspaces.json` before target work. Commit and push that private config change so later runs share the new desired layout.

### Target reconciliation

For each desired repository:

1. Keep a matching repository already at the desired path.
2. When the destination is absent, scan physical Git roots under the target Code root while excluding `.workspace-sync`, dependencies, builds, caches, symlinks, and repository subtrees.
3. Move only one unassigned checkout with the same canonical remote. Preview reports `planned-move`; apply uses a filesystem rename and never falls back to copy-then-delete.
4. Require `--allow-dirty-relocation` for a dirty checkout. Preserve its tracked and untracked work during the directory move.
5. Stop on multiple matches, another desired path owning the match, linked worktrees, `.git`-file checkouts, nested repositories, path escape, destination conflicts, or move failure.
6. Clone from the remote only when no reusable checkout exists.

Repeated reconciliation returns `already-present` and performs no Git or filesystem mutation.

### Noninteractive preflight

Workspace operations are SSH/CLI-only. Screen Sharing, GUI terminals, Computer Use, AppleScript, clipboard transfer, and processes launched into a GUI login session are prohibited as execution or credential fallbacks.

Before an apply, the controller asks every selected target to preview its filesystem action and run `git ls-remote` with terminal prompts disabled for every selected remote. No target applies until all target preflights pass. Each target repeats the remote check before creating its registered Code root, acquiring runtime state, moving a checkout, fetching, or cloning. A failed preflight records no applied-run history and requires the user to choose or repair a noninteractive credential method. The two phases prevent known failures from causing partial fleet changes; a later connectivity race can still interrupt an apply and is reported without GUI fallback.

### Machine-local records

Applied `bootstrap`, `reconcile`, `refresh`, and `migrate-github-remotes` runs share one run ID across the controller and targets. Each participating machine writes:

```text
<resolved Code root>/.workspace-sync/
  state.json
  plugin-state.json
  history.jsonl
  runs/<UTC-run-id>.json
  operation.lock
```

- `state.json` is the latest observed mapping from sanitized remote identities to Code-relative paths and commit heads.
- `plugin-state.json` is the latest machine-local ownership record for plugins and marketplaces installed by this workflow. It never records credentials or claims machine-local authentication succeeded.
- `history.jsonl` is a bounded 500-run summary ledger.
- `runs/` retains the newest 100 full result records.
- Directories use mode `0700`; files use `0600`; writes replace atomically.
- A nonblocking machine-local lock prevents overlapping apply runs; source history writes also serialize locally.
- Preview, preflight, failed preflight, and doctor do not create state. Records are machine-local, rebuildable, and never copied to another computer.
- The first applied run atomically moves legacy state into this directory. If old and new state directories both exist, the run stops without merging or overwriting either one.

The source record summarizes all target results; each target record captures its local result and post-run repository locations. A history-write failure is surfaced as an incomplete run rather than hidden.
