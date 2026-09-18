## Exact State And Recovery

Use `scripts/codex_thread_port.py` for exact-ID migration, bulk workspace sets, pinned/archive selections, local-state recovery, or when native task tools cannot express the request.

### Export And Preview

```bash
python3 scripts/codex_thread_port.py inventory --pinned
python3 scripts/codex_thread_port.py inventory --query "title words"

python3 scripts/codex_thread_port.py export \
  --id <THREAD_UUID> \
  --output /tmp/codex-threads.tar.gz

python3 /tmp/codex_thread_port.py import \
  --bundle /tmp/codex-threads.tar.gz \
  --cwd-map /source/root=/destination/root
```

Preview is the default. Review the selected IDs, destination paths, archive state, existing-ID policy, and pin result before repeating with `--apply`. Imports default to `--pins none`.

To copy into an existing destination-native task without duplicating the source UUID:

```bash
python3 /tmp/codex_thread_port.py import \
  --bundle /tmp/codex-threads.tar.gz \
  --existing update \
  --destination-id SOURCE_UUID=DESTINATION_NATIVE_UUID
```

Preview first. The destination ID must already exist in the destination database. Apply preserves its ID, rollout path, workspace, archive state, and Git placement; applies the requested `--pins` behavior; rewrites session ownership metadata; and backs up the destination transcript with the database before replacement.

### Import Semantics

- Only selected thread rows, transcript JSONL, session-index entries, and requested pin membership are exported.
- Missing IDs insert. Existing IDs skip unless `--existing update` is explicit.
- Source row columns are intersected with the destination schema.
- `rollout_path` becomes a destination path. `--cwd-map` rewrites leading workspace paths in row metadata, not historical transcript text.
- Archive state selects `sessions/` or `archived_sessions/`.
- Destination index records win on an existing ID.
- Apply creates a backup under `~/.codex/thread-port-backups/` before mutation.
- `--destination-id SOURCE=DESTINATION` is an explicit history transplant into an existing native destination. It requires `--existing update` and never synthesizes the destination ID.

### Desktop SSH Alias Re-key

Use `scripts/codex_alias_rekey.py` when old and new SSH aliases reach the same physical remote Codex home. It changes the requesting desktop's project metadata only; it does not copy transcripts.

```bash
python3 scripts/codex_alias_rekey.py \
  --source-host remote-ssh-discovered:worker-mesh \
  --destination-host remote-ssh-codex-managed:worker \
  --thread THREAD_UUID
```

Preview is the default. Apply refuses to run while ChatGPT desktop is open, backs up `.codex-global-state.json`, clones only required destination projects, and re-associates only selected thread IDs. Use `--project-template-id` for a newly copied destination-native thread that has no old-host assignment yet.

### Selectors

Selectors form a union. `--query` checks titles, first user messages, and indexed thread names case-insensitively. `--cwd` is exact. `--archive-state` filters matches or can select all threads in that state. Inventory before export.

```bash
python3 scripts/codex_thread_port.py export \
  --cwd /path/to/repo \
  --output /tmp/repo-threads.tar.gz

python3 scripts/codex_thread_port.py inventory \
  --archive-state archived --query "incident"
```

### Remote Apply

1. Resolve the destination from the machine-topology source of truth.
2. Check connectivity, versions, state database, free space, running state writers, and workspace paths.
3. Export and verify locally; transfer only the bundle and required script over the approved machine route.
4. Stop destination state writers, preview, then apply with required path mappings.
5. Restart exactly what was stopped. Run bundle verification and open one migrated thread.
6. Remove temporary bundle/script only after verification; retain the generated backup path.

For a user-requested move, delete the source only after the destination app renders and opens the imported thread with the expected identity and history. For a copy, retain the source and avoid duplicate visible UUIDs by using a destination-native identity when both copies must coexist. The completion report must name the direct SSH state-port method, confirm that no handoff worktree was created, and state how Codex or T3 visibility was verified.

### Recovery

If verification fails, keep Codex stopped and restore only files from the generated backup. Remove only transcript paths proven to have been newly imported by the failed run. Never bulk-delete session folders or restore a database over a running process. Preserve the failed state for diagnosis, restart, then verify integrity and the destination’s pre-existing threads.
