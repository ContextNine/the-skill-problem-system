## Codex Between Machines

### Route Matrix

| User intent | Preferred route | Source retained | Destination identity |
| --- | --- | --- | --- |
| Move one task | Exact-state bundle over approved SSH | No, after verification | Same task |
| Copy one task and keep both | Direct port into a destination-native task | Yes | New native ID |
| Same repo on another machine, visible here | Direct port, then destination-app verification | Per move/copy wording | Same for move; new for coexistence |
| Handoff one task | Native Codex handoff | No | Same task in a destination worktree |
| Exact migration or recovery | Bundle export/import | Yes unless later deleted | Same ID |
| Rename, pin, unpin, archive, restore | Native thread tools on resolved host | N/A | Unchanged |

### Direct Move Or Copy Workflow

1. List projects and threads. Resolve source/destination host IDs and exact workspace paths.
2. Read the source thread and wait for any active turn to finish.
3. Export only the selected rows and transcript with `codex_thread_port.py`; transfer the verified bundle and required script over the approved SSH route.
4. Stop destination state writers, preview the import with the required workspace mapping, apply it, then restart exactly what was stopped.
5. Verify destination history, workspace, host, title, pin/archive state, database integrity, and rendered sidebar/project visibility.
6. For a move, remove the source only after destination verification. For a copy that must coexist visibly, use a destination-native ID rather than duplicating a visible UUID.

This route transfers thread state, not repository contents, and does not create a Git worktree. Do not copy an entire Codex state directory or authentication/config files.

### Native Handoff Workflow

Use only when the user says “handoff” or explicitly approves Codex's native method. The destination must expose a matching saved project. Codex creates or reuses a destination Git worktree, transfers the chat and Git state, and switches the task to that host. The calling task cannot hand itself off; operate from another task. Cross-host handoff interrupts a running source and does not preserve sidebar order.

### Same Repository, Different Machine, Visible In Codex

This is the acceptance-sensitive workflow:

1. Confirm move versus copy, identity, pin state, and the destination workspace mapping.
2. Port the selected thread directly with the exact-state workflow over the approved SSH route.
3. Restart or refresh the destination state writers after import.
4. Verify source and destination identities independently.
5. In the requesting Codex desktop app, expand the remote project and confirm the destination title is rendered and opens with the expected history.

Do not stop at `list_threads`. A thread can exist in the remote database or global feed without appearing beneath its project in the sidebar.

### Same Machine, Replacement SSH Alias

When a canonical alias replaces `-lan`, `-mesh`, an IP address, or another transport-specific alias for the same physical machine, the remote Codex database already contains the threads. Do not port transcripts or create new thread IDs.

1. Confirm both aliases resolve to the same machine and Codex home.
2. Inventory the old and new Codex host IDs, saved projects, selected thread assignments, pins, and archive state.
3. Preview `scripts/codex_alias_rekey.py` for only the selected threads. It clones each matching saved project under the replacement host ID and updates the requesting desktop's project assignment while retaining the old project and connection for rollback.
4. Quit the Codex desktop state writer, apply, then reopen the same app.
5. Verify each thread under the replacement host/project in the actual sidebar before removing any old project or connection.

The re-key script must refuse an assignment whose source host or project template does not match. Its apply creates a dated backup under `~/.codex/thread-port-backups/`. Keep old connections until the user separately approves retirement.

For a local-to-remote copy, first create a native destination thread on the target host. Transplant the source history with `codex_thread_port.py --destination-id SOURCE=DESTINATION --existing update`; this retains the original source and avoids duplicate visible UUIDs. Stop destination state writers for apply, retain the generated database and transcript backup, and verify the destination-native ID and history after restart.

### Visibility Fallback

If native handoff cannot match a saved project but the user explicitly requested a new destination task:

1. Create a destination-native task directly in the target saved project and wait for its first turn to complete.
2. Back up the destination state database and both transcript files.
3. Preserve the destination-native task ID and project/workspace row. Transplant history only with a tested conversion procedure appropriate to the current schemas.
4. Restart the destination Codex app and SSH app server.
5. Verify with thread read/list tools and the visible sidebar. The old hidden/intermediate import may be removed only after the native destination opens with full history.

Do not “fix” visibility by changing only `thread_source`, `forked_from_id`, or `multi_agent_version`. Those fields are related but are not a substitute for destination-native ownership and end-to-end verification.

### Identity And Pin Rules

- Exact-ID copies are for migration/recovery. Duplicate IDs across visible hosts can collapse or resolve to the wrong host.
- Destination-native tasks are preferred for independent coexistence and receive internally consistent new IDs.
- Imported, forked, and destination-native tasks remain unpinned unless the user asks otherwise.
- Verify pin state separately on each host. Do not assume a pin follows a task.
- Deletion is a separate, explicit operation. Verify the exact host and ID immediately before it.
