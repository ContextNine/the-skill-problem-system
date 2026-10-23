---
name: fleet-i-restart-codex
description: Use when the user asks to update or restart Codex on a fleet machine and resume its running chats afterward, recover a stuck remote Codex server, or restart Codex without losing active work.
---

# Restart Codex and continue running chats

Read `$fleet-i-code-folder-and-computer-topology` for target identity and SSH routing, and `$fleet-i-update-coding-tools` for the installed Codex update channel. Limit changes to Codex on the requested machines. Invocation authorizes interrupting those machines' active turns and sending each captured chat exactly `Please continue.` afterward. Histories persist, but interrupted commands may need recovery and continuation can still encounter an approval, missing credential, or model error.

Run this workflow from a chat on another machine. Never restart the server executing this workflow. If the requested target is the executing host, arrange an explicitly authorized coordinator on another host first.

## Capture before interruption

Resolve the enabled target's SSH alias and its exact native chat-tool host ID. Capture all active thread IDs from the live daemon, not SQLite timestamps, lock files, or a truncated sidebar list. The bundled helper pages through every thread source, cross-checks loaded threads, and refuses to save an incomplete snapshot.

```bash
python3 ./scripts/capture_active_threads.py --socket DAEMON_SOCKET --host-id NATIVE_HOST_ID --output RECOVERY_FILE
```

Resolve the script relative to this skill. Run it on the target, using the `socketPath` returned by `codex app-server daemon version`. For SSH targets, stage this reviewed helper outside the Vault, execute it through the registry SSH route, and copy its JSON result to the coordinator before interruption. It uses only Python's standard library and the existing private Unix socket, with no public listener or credential reads. Keep the coordinator's `RECOVERY_FILE` under its native user state directory in `fleet-codex-restart/<target>/<timestamp>.json`, outside a repository. Reuse an unfinished recovery file instead of taking a post-restart empty snapshot. Keep the active thread IDs, target, capture time, pre-restart versions/PID, and per-thread message/verification results in that file. Do not store credentials or transcript bodies. Remove the staged helper after recovery.

Print the captured count and titles. Refresh the snapshot immediately before the first updater or restart and save it before proceeding. Before interruption, the refreshed live state replaces the preliminary list so already completed chats are excluded. After interruption starts, retain every captured ID until its recovery is resolved. If live discovery fails, stop before interruption and report the failure; do not invent a list from cached statuses. A chat that was idle at capture is not a continuation target.

## Update and restart

Use the target user's login shell over the registry SSH route. Inspect the installed commands and provenance before choosing them:

```bash
codex --version
codex app-server daemon version
codex help update
codex app-server daemon update --help
codex app-server daemon restart --help
```

For update-and-restart, run the installed `codex update` when supported, otherwise use the confirmed installation channel from `$fleet-i-update-coding-tools`. Do not run the broad fleet coding-tools updater, which also updates other products. For restart-only, skip the updater.

When the existing daemon is pinned to a different package, and installed help supports it, adopt the updated CLI with `codex app-server daemon update --from-cli --yes`. This command may itself restart the daemon, so the recovery list must already be saved. Use `codex app-server daemon restart` if a restart is still required. Verify with `codex app-server daemon version` that the server is running the intended version and its process was replaced. If an updater fails after interrupting the server, restore service through its existing manager and still recover the captured chats before reporting the update failure.

Prefer the confirmed daemon/service control path. If the native command reports an existing unmanaged server, inspect its exact PID, owner, executable, launch arguments, and log destination. For this explicitly requested restart, a scoped fallback may send SIGTERM to that revalidated server PID and allow a bounded graceful exit. If it remains stuck, try SIGINT; if that also fails, revalidate identity and use SIGKILL only on that exact server and its confirmed owned protocol helpers. With the recovery list saved, wait for those processes to exit, then relaunch the same recorded flags with the updated executable, detached through SSH with stdin closed and output in its existing native runtime log. Preserve independently running development services. Do not guess launch flags or signal an unverified process; report a blocker if the launch cannot be established. Verify replacement PID, private socket readiness, and the running server version before sending continuations.

Never use blanket process kills, delete locks/history, copy authentication, create a replacement service, or bootstrap a missing daemon as an inferred fix. Bound commands and readiness checks; before retrying a failed command confirm that it and its children have exited. Do not open remote terminal windows.

## Continue every captured chat

Wait for the exact target to reconnect. For each saved ID, check its current turn, then use native `send_message_to_thread` with its saved `hostId` and `threadId`, prompt exactly `Please continue.`, and no model or reasoning override. Send once per captured ID and record the returned turn/result immediately. If delivery times out, inspect that chat for the exact message/new turn before retrying, to avoid sending it twice. Continue processing other captured IDs when one fails.

Use bounded native `wait_threads` calls, at most eight targets per call, with returned cursors. Confirm each continuation has a new turn or resumed activity, or report its specific failure/approval state. A successful send alone does not prove that work resumed. If the native chat tool is unavailable, preserve the recovery file and report the unsent IDs; do not substitute a detached CLI agent that cannot service the chat's desktop tools.

Report target, old/new CLI and server versions, captured count, sent count, verified count, blocked IDs, and recovery-file location. Keep unfinished records for retry; never claim all chats resumed when any remain unverified.
