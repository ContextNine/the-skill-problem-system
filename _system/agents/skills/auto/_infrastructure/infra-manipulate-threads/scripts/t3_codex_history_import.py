#!/usr/bin/env python3
"""Bridge selected pinned Codex history into a T3 Code project.

Preview is default. Apply requires explicit confirmation that T3 is stopped and
creates a consistent SQLite backup before changing T3 state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


NAMESPACE = uuid.UUID("8a8348b4-19f1-47b4-ac75-3ae8bde5bf22")
INJECTED_USER_PREFIXES = (
    "# AGENTS.md instructions for ",
    "<permissions instructions>",
    "<app-context>",
    "<collaboration_mode>",
    "<environment_context>",
    "<skills_instructions>",
    "<apps_instructions>",
    "<plugins_instructions>",
    "<recommended_plugins>",
)
REQUIRED_T3_TABLES = {
    "orchestration_events",
    "projection_projects",
    "projection_state",
    "projection_thread_messages",
    "projection_thread_sessions",
    "projection_threads",
    "provider_session_runtime",
}


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def deterministic_id(kind: str, source: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{source}"))


def iso_timestamp(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        candidate = value.strip()
        try:
            parsed = dt.datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            pass
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    number = float(value or 0)
    if number > 10_000_000_000:
        number /= 1000
    return dt.datetime.fromtimestamp(number, tz=dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_pins(codex_home: Path) -> list[str]:
    path = codex_home / ".codex-global-state.json"
    if not path.is_file():
        fail(f"missing Codex global state: {path}")
    state = json.loads(path.read_text(encoding="utf-8"))
    pins = state.get("pinned-thread-ids", []) if isinstance(state, dict) else []
    return [item for item in pins if isinstance(item, str)]


def read_titles(codex_home: Path) -> dict[str, str]:
    path = codex_home / "session_index.jsonl"
    if not path.exists():
        return {}
    titles: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"invalid {path}:{number}: {exc}")
        if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("thread_name"), str):
            titles[item["id"]] = item["thread_name"]
    return titles


def select_threads(codex_home: Path, source_cwd: str, canary_id: str | None) -> list[dict[str, Any]]:
    pins = read_pins(codex_home)
    if not pins:
        fail("Codex pin list is empty")
    state_db = codex_home / "state_5.sqlite"
    connection = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in pins)
    rows = {
        row["id"]: dict(row)
        for row in connection.execute(f"SELECT * FROM threads WHERE id IN ({placeholders})", pins)
    }
    connection.close()
    selected = [
        rows[thread_id]
        for thread_id in pins
        if thread_id in rows
        and rows[thread_id].get("cwd") == source_cwd
        and not int(rows[thread_id].get("archived") or 0)
    ]
    if canary_id:
        selected = [row for row in selected if row["id"] == canary_id]
        if not selected:
            fail(f"canary is not an active pinned thread in {source_cwd}: {canary_id}")
    if not selected:
        fail(f"no active pinned Codex threads selected for cwd: {source_cwd}")
    return selected


def visible_chunks(payload: dict[str, Any]) -> tuple[str, int]:
    role = payload.get("role")
    chunks: list[str] = []
    non_text_parts = 0
    for content in payload.get("content") or []:
        if not isinstance(content, dict):
            continue
        text = content.get("text")
        if isinstance(text, str):
            if role == "user" and text.lstrip().startswith(INJECTED_USER_PREFIXES):
                continue
            chunks.append(text)
            continue
        non_text_parts += 1
        if content.get("type") == "input_image":
            chunks.append("[Image attached in original Codex history; exact image remains available to resumed Codex context.]")
        else:
            chunks.append(f"[Non-text {content.get('type') or 'attachment'} preserved in original Codex history.]")
    return "\n\n".join(chunk for chunk in chunks if chunk), non_text_parts


def parse_messages(transcript: Path, codex_id: str) -> tuple[list[dict[str, Any]], int]:
    messages: list[dict[str, Any]] = []
    non_text_parts = 0
    active_turn_id: str | None = None
    user_ordinal = 0
    for line_number, line in enumerate(transcript.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"invalid {transcript}:{line_number}: {exc}")
        if item.get("type") != "response_item":
            continue
        payload = item.get("payload") or {}
        if payload.get("type") != "message" or payload.get("role") not in {"user", "assistant"}:
            continue
        text, omitted = visible_chunks(payload)
        non_text_parts += omitted
        if not text.strip():
            continue
        role = payload["role"]
        provider_turn_id = (payload.get("internal_chat_message_metadata_passthrough") or {}).get("turn_id")
        if role == "user":
            user_ordinal += 1
            active_turn_id = provider_turn_id or deterministic_id("turn", f"{codex_id}:{user_ordinal}")
        elif provider_turn_id:
            active_turn_id = provider_turn_id
        messages.append(
            {
                "message_id": deterministic_id("message", f"{codex_id}:{line_number}"),
                "role": role,
                "text": text,
                "turn_id": active_turn_id,
                "created_at": iso_timestamp(item.get("timestamp")),
            }
        )
    return messages, non_text_parts


def parse_resume_cursor(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed.get("threadId") if isinstance(parsed, dict) and isinstance(parsed.get("threadId"), str) else None


def validate_t3_schema(connection: sqlite3.Connection) -> None:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_system WHERE type = 'table'")}
    missing = sorted(REQUIRED_T3_TABLES - tables)
    if missing:
        fail(f"unsupported T3 schema; missing tables: {', '.join(missing)}")


def load_project(connection: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT * FROM projection_projects WHERE project_id = ? AND deleted_at IS NULL",
        (project_id,),
    ).fetchone()
    if row is None:
        fail(f"T3 project not found: {project_id}")
    return dict(row)


def prepare(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    codex_home = Path(args.codex_home).expanduser().resolve()
    t3_db = Path(args.t3_db).expanduser().resolve()
    rows = select_threads(codex_home, args.source_cwd, args.canary_id)
    if args.expected_count is not None and len(rows) != args.expected_count:
        fail(f"selected {len(rows)} threads; expected {args.expected_count}")

    connection = sqlite3.connect(f"file:{t3_db}?mode=ro", uri=True)
    validate_t3_schema(connection)
    project = load_project(connection, args.project_id)
    if project["workspace_root"] != args.runtime_cwd and not args.allow_project_cwd_mismatch:
        fail(
            f"T3 project workspace is {project['workspace_root']!r}, not runtime cwd {args.runtime_cwd!r}; "
            "use --allow-project-cwd-mismatch only after inspection"
        )
    if not project.get("default_model_selection_json"):
        fail("T3 project has no default model selection")
    existing_thread_ids = {row[0] for row in connection.execute("SELECT thread_id FROM projection_threads")}
    existing_cursors = {
        cursor
        for row in connection.execute(
            "SELECT resume_cursor_json FROM provider_session_runtime WHERE resume_cursor_json IS NOT NULL"
        )
        if (cursor := parse_resume_cursor(row[0]))
    }
    connection.close()

    titles = read_titles(codex_home)
    model_selection = json.loads(project["default_model_selection_json"])
    prepared: list[dict[str, Any]] = []
    for pin_index, row in enumerate(rows):
        codex_id = row["id"]
        t3_id = deterministic_id("thread", codex_id)
        transcript = Path(row["rollout_path"])
        if not transcript.is_file():
            fail(f"missing transcript: {transcript}")
        messages, non_text_parts = parse_messages(transcript, codex_id)
        if not messages:
            fail(f"no visible messages: {codex_id}")
        prepared.append(
            {
                "codex_id": codex_id,
                "t3_id": t3_id,
                "title": titles.get(codex_id) or row.get("title") or codex_id,
                "transcript": str(transcript),
                "transcript_sha256": hashlib.sha256(transcript.read_bytes()).hexdigest(),
                "pin_index": pin_index,
                "created_at": iso_timestamp(row.get("created_at_ms") or row.get("created_at")),
                "latest_message_at": messages[-1]["created_at"],
                "latest_user_at": next(
                    (message["created_at"] for message in reversed(messages) if message["role"] == "user"),
                    None,
                ),
                "message_count": len(messages),
                "user_message_count": sum(message["role"] == "user" for message in messages),
                "assistant_message_count": sum(message["role"] == "assistant" for message in messages),
                "non_text_parts": non_text_parts,
                "messages": messages,
                "model_selection": model_selection,
                "already_imported": t3_id in existing_thread_ids or codex_id in existing_cursors,
            }
        )
    return project, prepared


def create_backup(t3_db: Path, requested_dir: str | None) -> Path:
    stamp = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-before-codex-import")
    backup_dir = Path(requested_dir).expanduser().resolve() if requested_dir else t3_db.parent.parent / "thread-import-backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    source = sqlite3.connect(f"file:{t3_db}?mode=ro", uri=True)
    destination = sqlite3.connect(backup_dir / "state.sqlite")
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup_dir


def add_event(
    connection: sqlite3.Connection,
    thread_id: str,
    version: int,
    event_type: str,
    occurred_at: str,
    payload: dict[str, Any],
) -> None:
    command_id = deterministic_id("command", f"{thread_id}:{version}:{event_type}")
    connection.execute(
        """INSERT INTO orchestration_events
        (event_id, aggregate_kind, stream_id, stream_version, event_type, occurred_at,
         command_id, causation_event_id, correlation_id, actor_kind, payload_json, metadata_json)
        VALUES (?, 'thread', ?, ?, ?, ?, ?, NULL, ?, 'client', ?, '{}')""",
        (
            deterministic_id("event", f"{thread_id}:{version}:{event_type}"),
            thread_id,
            version,
            event_type,
            occurred_at,
            command_id,
            command_id,
            compact_json(payload),
        ),
    )


def import_threads(args: argparse.Namespace, threads: list[dict[str, Any]]) -> tuple[Path, int]:
    if not args.confirm_t3_stopped:
        fail("--apply requires --confirm-t3-stopped")
    pending = [thread for thread in threads if not thread["already_imported"]]
    if len(pending) != len(threads) and not args.skip_existing:
        duplicates = [thread["codex_id"] for thread in threads if thread["already_imported"]]
        fail(f"threads already imported: {', '.join(duplicates)}")
    t3_db = Path(args.t3_db).expanduser().resolve()
    backup_dir = create_backup(t3_db, args.backup_dir)
    connection = sqlite3.connect(t3_db)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        for thread in pending:
            thread_id = thread["t3_id"]
            model_selection = thread["model_selection"]
            created_at = thread["created_at"]
            updated_at = thread["latest_message_at"]
            version = 0
            add_event(
                connection,
                thread_id,
                version,
                "thread.created",
                created_at,
                {
                    "threadId": thread_id,
                    "projectId": args.project_id,
                    "title": thread["title"],
                    "modelSelection": model_selection,
                    "runtimeMode": "full-access",
                    "interactionMode": "default",
                    "branch": args.branch,
                    "worktreePath": None,
                    "createdAt": created_at,
                    "updatedAt": created_at,
                },
            )
            connection.execute(
                """INSERT INTO projection_threads
                (thread_id, project_id, title, branch, worktree_path, latest_turn_id, created_at,
                 updated_at, deleted_at, runtime_mode, interaction_mode, model_selection_json,
                 archived_at, latest_user_message_at, pending_approval_count,
                 pending_user_input_count, has_actionable_proposed_plan)
                VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, NULL, 'full-access', 'default', ?, NULL, ?, 0, 0, 0)""",
                (
                    thread_id,
                    args.project_id,
                    thread["title"],
                    args.branch,
                    created_at,
                    updated_at,
                    compact_json(model_selection),
                    thread["latest_user_at"],
                ),
            )
            for message in thread["messages"]:
                version += 1
                payload = {
                    "threadId": thread_id,
                    "messageId": message["message_id"],
                    "role": message["role"],
                    "text": message["text"],
                    "attachments": [],
                    "turnId": message["turn_id"],
                    "streaming": False,
                    "createdAt": message["created_at"],
                    "updatedAt": message["created_at"],
                }
                add_event(connection, thread_id, version, "thread.message-sent", message["created_at"], payload)
                connection.execute(
                    """INSERT INTO projection_thread_messages
                    (message_id, thread_id, turn_id, role, text, is_streaming, created_at, updated_at, attachments_json)
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?, NULL)""",
                    (
                        message["message_id"],
                        thread_id,
                        message["turn_id"],
                        message["role"],
                        message["text"],
                        message["created_at"],
                        message["created_at"],
                    ),
                )
            version += 1
            session = {
                "threadId": thread_id,
                "status": "stopped",
                "providerName": "codex",
                "providerInstanceId": "codex",
                "runtimeMode": "full-access",
                "activeTurnId": None,
                "lastError": None,
                "updatedAt": updated_at,
            }
            add_event(connection, thread_id, version, "thread.session-set", updated_at, {"threadId": thread_id, "session": session})
            connection.execute(
                """INSERT INTO projection_thread_sessions
                (thread_id, status, provider_name, provider_session_id, provider_thread_id,
                 active_turn_id, last_error, updated_at, runtime_mode, provider_instance_id)
                VALUES (?, 'stopped', 'codex', NULL, NULL, NULL, NULL, ?, 'full-access', 'codex')""",
                (thread_id, updated_at),
            )
            runtime_payload = {
                "cwd": args.runtime_cwd,
                "model": model_selection.get("model"),
                "activeTurnId": None,
                "lastError": None,
                "modelSelection": model_selection,
                "lastRuntimeEvent": "codex.history-import",
                "lastRuntimeEventAt": updated_at,
            }
            connection.execute(
                """INSERT INTO provider_session_runtime
                (thread_id, provider_name, adapter_key, runtime_mode, status, last_seen_at,
                 resume_cursor_json, runtime_payload_json, provider_instance_id)
                VALUES (?, 'codex', 'codex', 'full-access', 'stopped', ?, ?, ?, 'codex')""",
                (
                    thread_id,
                    updated_at,
                    compact_json({"threadId": thread["codex_id"]}),
                    compact_json(runtime_payload),
                ),
            )
        max_sequence = connection.execute("SELECT COALESCE(MAX(sequence), 0) FROM orchestration_events").fetchone()[0]
        applied_at = dt.datetime.now(tz=dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        connection.execute(
            "UPDATE projection_state SET last_applied_sequence = ?, updated_at = ?",
            (max_sequence, applied_at),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return backup_dir, len(pending)


def report(
    project: dict[str, Any],
    threads: list[dict[str, Any]],
    applied: bool,
    backup_dir: Path | None,
    applied_count: int,
) -> dict[str, Any]:
    return {
        "mode": "applied" if applied else "preview",
        "backup_dir": str(backup_dir) if backup_dir else None,
        "applied_count": applied_count,
        "project": {
            "project_id": project["project_id"],
            "title": project["title"],
            "workspace_root": project["workspace_root"],
        },
        "thread_count": len(threads),
        "message_count": sum(thread["message_count"] for thread in threads),
        "user_message_count": sum(thread["user_message_count"] for thread in threads),
        "assistant_message_count": sum(thread["assistant_message_count"] for thread in threads),
        "non_text_parts": sum(thread["non_text_parts"] for thread in threads),
        "threads": [
            {
                key: thread[key]
                for key in (
                    "codex_id",
                    "t3_id",
                    "title",
                    "pin_index",
                    "message_count",
                    "user_message_count",
                    "assistant_message_count",
                    "non_text_parts",
                    "transcript",
                    "transcript_sha256",
                    "already_imported",
                )
            }
            for thread in threads
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", required=True)
    parser.add_argument("--t3-db", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--source-cwd", required=True)
    parser.add_argument("--runtime-cwd", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--canary-id")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--manifest")
    parser.add_argument("--backup-dir")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--allow-project-cwd-mismatch", action="store_true")
    parser.add_argument("--confirm-t3-stopped", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    project, threads = prepare(args)
    backup_dir: Path | None = None
    applied_count = 0
    if args.apply:
        backup_dir, applied_count = import_threads(args, threads)
    output = report(project, threads, args.apply, backup_dir, applied_count)
    rendered = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.manifest:
        Path(args.manifest).expanduser().write_text(rendered, encoding="utf-8")
    if backup_dir:
        (backup_dir / "import-manifest.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
