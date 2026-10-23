## Edit saved projects after a repository move

A saved project is a name, host and directory plus chat membership. Moving its checkout does not update these records. Edit the existing project in place so its ID, sidebar position and pins remain stable. A same-host directory change does not copy chats, generate new IDs or create a worktree.

Resolve machine identity and checkout paths through `$fleet-i-code-folder-and-computer-topology`. Use `$fleet-i-sync-code-workspaces` to reconcile the registered destination first. If the new repository has a different remote identity, reconcile it independently. Preserve the old checkout outside the active Code root when removing it, including unpublished branches and untracked files. Inspect running previews before retiring their directory.

### Select the actual project store

List projects and inspect only relevant project metadata before editing. The requesting desktop owns saved SSH project records even though the repository and chats live on a worker. Do not assume editing the worker's desktop state will change the primary's sidebar.

- Saved remote projects currently use `remote-projects` in the requesting desktop's `.codex-global-state.json`. Each record contains `id`, `hostId`, `remotePath` and `label`. Membership can be explicit in `thread-project-assignments` or inferred from chat working directories.
- Local projects can be backed by app-server `projects` and `project_roots`, with legacy IDs mapped through `app-server-project-id-by-legacy-project-id-by-host`. Prefer the native editor or `project/read` and `project/update` when the connected app-server supports them. A change to legacy JSON alone can be ignored by that backend.
- These formats are internal and version-sensitive. Read the installed app code or protocol schema when the store differs. Do not blindly reuse a stale schema or assume an exposed tool can edit directories because it can list projects.

### Change chat working directories

Inventory active and archived chats separately on the actual host, including subagent sources. Select exact IDs whose current directory belongs to the old checkout. Confirm no selected chat is running a turn before changing its directory.

`../scripts/codex_thread_cwd.py` uses native `thread/resume` with `cwd` and `excludeTurns`. It starts no turn and sends no user message. It preserves IDs, checks pin/archive state and creates a SQLite snapshot plus selected transcript backups before applying. Run the script on the host that owns the chats, over the approved SSH route, using that host's Codex executable:

```bash
python3 scripts/codex_thread_cwd.py \
  --from-cwd /home/user/Code/old-repository \
  --cwd /home/user/Code/group/new-repository \
  --thread THREAD_UUID
```

Preview first, then repeat with `--apply`. This helper refuses archived chats; use a separately verified procedure that preserves archive state for those. It uses the normal stdio app-server RPC transport. Do not treat `app-server proxy` as a newline-JSON RPC stream; its daemon transport differs.

After apply, reconnect and resume a selected chat without a cwd override. Confirm it still uses the new directory. Historical transcript text and earlier context can retain old paths; do not rewrite user or assistant messages. A native API update is distinct from direct state editing and does not require stopping unrelated state writers.

### Edit saved remote project metadata

`../scripts/codex_project_edit.py` previews a JSON operations file. Each operation contains:

```json
[
  {
    "project_id": "EXISTING_PROJECT_UUID",
    "host_id": "remote-ssh-codex-managed:worker",
    "from_path": "/home/user/Code/old-repository",
    "to_path": "/home/user/Code/group/new-repository",
    "name": "new-repository",
    "thread_ids": ["VERIFIED_REMOTE_THREAD_UUID"]
  }
]
```

List only verified chat IDs that need this membership. The helper also updates assignments already attached to the selected project. It rejects a conflicting assignment or another project at the destination path. A duplicate UUID may represent a retained local original and a remote copy. Preserve the local original's assignment; do not silently redirect it to the worker.

For stale assignments left by earlier SSH aliases or removed projects, an optional `previous_assignments` map permits replacing only the exact reviewed old assignment for each selected ID. Verify those assignments belong to the same physical machine and checkout. Keep this evidence in machine-local state, not in portable skill source. The helper always refuses converting a local assignment through this exception.

```bash
python3 scripts/codex_project_edit.py --operations /tmp/reviewed-project-edits.json
python3 scripts/codex_project_edit.py --operations /tmp/reviewed-project-edits.json --apply
```

Direct apply requires the requesting desktop to be closed. Codex caches global state in memory and rewrites the full document, so a live file edit can be lost. The helper checks for both current macOS desktop executable names, creates a dated backup under `.codex/thread-port-backups`, rejects a concurrent state change, and replaces only the reviewed fields atomically. It leaves project ordering, pins, titles and unrelated state intact.

If the task is running inside that desktop, finish the preview and all independent work before arranging a restart. `--apply --wait-for-desktop-exit SECONDS --report /path/to/report.json` can wait for a user-controlled quit. Waiting is bounded and never kills the app. Ensure that the report shows completion before reopening. Do not claim the migration is applied merely because a waiter was started.

### Acceptance and recovery

Reopen the requesting desktop, list both projects, and verify the intended names, host IDs and paths. Open an existing chat beneath each project and check its history and working directory. Verify pins, archives and sidebar position. A database row or successful file write does not establish rendered sidebar success. When Computer Use cannot inspect Codex, report that limit and obtain user confirmation of the visible result.

Keep the backup until acceptance. Restore desktop metadata only while its writers are closed. Use native RPC to reverse a cwd edit where possible; do not restore a database snapshot over a running app-server. Remove temporary scripts, operations and bundles after successful verification, retaining the backup and migration report in machine-local state.
