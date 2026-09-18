## T3 Code Bridge

T3 Code does not use Codex `state_5.sqlite` as its sidebar database. Its server state normally lives at `~/.t3/userdata/state.sqlite`, so a bridge has two stages:

1. Make the selected Codex rows and exact transcript JSONL available in the destination machine’s Codex state with `scripts/codex_thread_port.py`.
2. Import visible history into T3 projections with `scripts/t3_codex_history_import.py`, preserving the original Codex ID as T3’s provider resume cursor.

Rediscover the installed T3 version and database schema before every import. Do not assume a previously validated nightly build remains compatible.

For a user-requested **move** or **copy**, use the direct Codex state port over the approved SSH route and then this T3 projection import; do not substitute native Codex handoff. Native Codex **handoff** is a separate, explicitly named operation with destination worktree semantics and does not make a task T3-visible by itself.

### Preview And Canary

```bash
python3 scripts/t3_codex_history_import.py \
  --codex-home ~/.codex \
  --t3-db ~/.t3/userdata/state.sqlite \
  --project-id <T3_PROJECT_UUID> \
  --source-cwd /path/to/repo \
  --runtime-cwd /path/to/repo \
  --branch codex/<machine> \
  --expected-count <COUNT>
```

Stop T3 before applying. First apply one `--canary-id` with `--confirm-t3-stopped --apply`; verify it in T3, then repeat for the complete set with the expected count and `--skip-existing`.

### Data Semantics

- T3 UUIDs derive deterministically from original Codex task IDs.
- Visible user/assistant messages become T3 messages and orchestration events.
- Injected system/app/AGENTS context is excluded from visible T3 history, not from the source transcript.
- Non-text parts become visible markers; exact transcripts and attachments remain in Codex storage.
- The provider resume cursor retains the original Codex thread ID.
- Continuing through T3 resumes the underlying Codex task. Port that updated Codex task normally to return work to another Codex machine.
- T3 projections do not have Codex pin membership; T3 uses activity ordering.

### Verification

1. `PRAGMA integrity_check` returns `ok`.
2. Imported task/message counts, resume cursors, project, branch, and runtime workspace match the preview.
3. Source Codex transcript hashes and pin count are unchanged.
4. Orchestration and projection sequences agree.
5. Search and open an old imported title in T3; verify full visible history and destination project.

Do not assume T3 refreshes imported state automatically. Restart or refresh the exact T3 writer stopped for apply, then verify the task renders, opens, and can resume in the intended project. Report the method, IDs, source retention, backup, and rendered visibility after completion.

For rollback, stop T3, preserve the failed database, restore the script-created backup, remove only stale WAL/SHM companions, restart, and recheck integrity. Never delete source Codex tasks during bridge validation.
