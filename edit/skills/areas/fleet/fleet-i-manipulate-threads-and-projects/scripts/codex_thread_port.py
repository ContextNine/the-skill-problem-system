#!/usr/bin/env python3
"""Export, merge-import, and verify selected local Codex threads."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any


BUNDLE_VERSION = 1
THREAD_URL_PREFIX = "codex://threads/"


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def codex_home(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else Path.home() / ".codex"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read JSON {path}: {exc}")


def read_index(home: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    path = home / "session_index.jsonl"
    if not path.exists():
        return records, by_id
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"invalid {path}:{number}: {exc}")
        if isinstance(item, dict):
            records.append(item)
            if isinstance(item.get("id"), str):
                by_id[item["id"]] = item
    return records, by_id


def pinned_ids(home: Path) -> list[str]:
    state = read_json(home / ".codex-global-state.json", {})
    pins = state.get("pinned-thread-ids", []) if isinstance(state, dict) else []
    return [item for item in pins if isinstance(item, str)]


def open_db(home: Path, readonly: bool = True) -> sqlite3.Connection:
    path = home / "state_5.sqlite"
    if not path.exists():
        fail(f"missing Codex database: {path}")
    if readonly:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def normalize_id(value: str) -> str:
    return value[len(THREAD_URL_PREFIX) :] if value.startswith(THREAD_URL_PREFIX) else value


def select_threads(home: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    _, index = read_index(home)
    pins = set(pinned_ids(home))
    with open_db(home) as connection:
        rows = [dict(row) for row in connection.execute("SELECT * FROM threads")]

    primary_selector = bool(args.pinned or args.id or args.query or args.cwd or args.all)
    any_selector = bool(primary_selector or args.archive_state)
    if not any_selector:
        fail("provide at least one selector: --pinned, --id, --query, --cwd, --archive-state, or --all")

    exact_ids = {normalize_id(item) for item in (args.id or [])}
    queries = [item.casefold() for item in (args.query or [])]
    workspaces = set(args.cwd or [])
    wanted_archived = None
    if args.archive_state:
        wanted_archived = 1 if args.archive_state == "archived" else 0

    selected: list[dict[str, Any]] = []
    for row in rows:
        thread_id = row["id"]
        text = "\n".join(
            str(value)
            for value in (
                row.get("title", ""),
                row.get("first_user_message", ""),
                index.get(thread_id, {}).get("thread_name", ""),
            )
        ).casefold()
        matches = args.all or not primary_selector
        matches = matches or (args.pinned and thread_id in pins)
        matches = matches or thread_id in exact_ids
        matches = matches or any(query in text for query in queries)
        matches = matches or row.get("cwd") in workspaces
        if wanted_archived is not None and int(row.get("archived") or 0) != wanted_archived:
            matches = False
        if matches:
            selected.append(row)

    found_ids = {row["id"] for row in selected}
    missing_ids = exact_ids - found_ids
    if missing_ids:
        fail(f"thread IDs not found: {', '.join(sorted(missing_ids))}")
    selected.sort(key=lambda item: (int(item.get("updated_at_ms") or 0), item["id"]), reverse=True)
    return selected


def transcript_details(home: Path, row: dict[str, Any]) -> tuple[Path, str, str]:
    source = Path(row["rollout_path"])
    if not source.is_file():
        fail(f"missing transcript for {row['id']}: {source}")
    archive_root = "archived_sessions" if int(row.get("archived") or 0) else "sessions"
    root = home / archive_root
    try:
        relative = source.resolve().relative_to(root.resolve())
    except ValueError:
        relative = Path(source.name)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return source, archive_root, relative.as_posix(), digest


def display_inventory(home: Path, rows: list[dict[str, Any]]) -> None:
    _, index = read_index(home)
    pins = set(pinned_ids(home))
    output = []
    for row in rows:
        source = Path(row["rollout_path"])
        output.append(
            {
                "id": row["id"],
                "title": index.get(row["id"], {}).get("thread_name") or row.get("title", ""),
                "cwd": row.get("cwd"),
                "archived": bool(row.get("archived")),
                "pinned": row["id"] in pins,
                "transcript": str(source),
                "transcript_exists": source.is_file(),
            }
        )
    print(json.dumps({"count": len(output), "threads": output}, indent=2, ensure_ascii=False))


def command_inventory(args: argparse.Namespace) -> None:
    home = codex_home(args.codex_home)
    display_inventory(home, select_threads(home, args))


def command_export(args: argparse.Namespace) -> None:
    home = codex_home(args.codex_home)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        fail(f"output already exists: {output}")
    rows = select_threads(home, args)
    if not rows:
        fail("selection matched zero threads")
    _, index = read_index(home)
    pins = set(pinned_ids(home))

    with tempfile.TemporaryDirectory(prefix="codex-thread-port-") as temp_name:
        stage = Path(temp_name) / "bundle"
        transcripts = stage / "transcripts"
        transcripts.mkdir(parents=True)
        manifest_threads = []
        for row in rows:
            source, root, relative, digest = transcript_details(home, row)
            bundled_name = f"{row['id']}.jsonl"
            shutil.copy2(source, transcripts / bundled_name)
            manifest_threads.append(
                {
                    "row": row,
                    "index": index.get(row["id"]),
                    "pinned": row["id"] in pins,
                    "transcript": {
                        "bundle_path": f"transcripts/{bundled_name}",
                        "destination_root": root,
                        "relative_path": relative,
                        "sha256": digest,
                        "size": source.stat().st_size,
                    },
                }
            )
        manifest = {
            "format": "codex-thread-port",
            "version": BUNDLE_VERSION,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_codex_home": str(home),
            "thread_count": len(manifest_threads),
            "threads": manifest_threads,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(output, "w:gz") as archive:
            archive.add(stage, arcname="bundle")
    os.chmod(output, 0o600)
    print(json.dumps({"output": str(output), "threads": len(rows), "bytes": output.stat().st_size}, indent=2))


def safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != root and root not in target.parents:
            fail(f"unsafe archive path: {member.name}")
        if member.issym() or member.islnk():
            fail(f"bundle links are not allowed: {member.name}")
    try:
        archive.extractall(destination, filter="data")
    except TypeError:
        # Python <3.12 has no extraction filter. Paths and links were validated above.
        archive.extractall(destination)


def load_bundle(path_value: str) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        fail(f"bundle not found: {path}")
    temp = tempfile.TemporaryDirectory(prefix="codex-thread-import-")
    destination = Path(temp.name)
    try:
        with tarfile.open(path, "r:gz") as archive:
            safe_extract(archive, destination)
        root = destination / "bundle"
        manifest = read_json(root / "manifest.json", None)
        if not isinstance(manifest, dict):
            fail("bundle manifest missing or invalid")
        if manifest.get("format") != "codex-thread-port" or manifest.get("version") != BUNDLE_VERSION:
            fail(f"unsupported bundle format/version: {manifest.get('format')} {manifest.get('version')}")
        if manifest.get("thread_count") != len(manifest.get("threads", [])):
            fail("bundle thread count mismatch")
        for item in manifest["threads"]:
            transcript = root / item["transcript"]["bundle_path"]
            if not transcript.is_file():
                fail(f"bundle transcript missing: {transcript}")
            digest = hashlib.sha256(transcript.read_bytes()).hexdigest()
            if digest != item["transcript"]["sha256"]:
                fail(f"bundle transcript hash mismatch: {item['row']['id']}")
        return temp, root, manifest
    except Exception:
        temp.cleanup()
        raise


def parse_cwd_maps(values: list[str] | None) -> list[tuple[str, str]]:
    mappings = []
    for value in values or []:
        if "=" not in value:
            fail(f"invalid --cwd-map {value!r}; expected OLD=NEW")
        old, new = value.split("=", 1)
        if not old or not new:
            fail(f"invalid --cwd-map {value!r}; expected non-empty OLD=NEW")
        mappings.append((old.rstrip("/"), new.rstrip("/")))
    return sorted(mappings, key=lambda item: len(item[0]), reverse=True)


def parse_destination_ids(values: list[str] | None) -> dict[str, str]:
    mappings: dict[str, str] = {}
    destinations: set[str] = set()
    for value in values or []:
        if "=" not in value:
            fail(f"invalid --destination-id {value!r}; expected SOURCE=DESTINATION")
        source, destination = (normalize_id(item.strip()) for item in value.split("=", 1))
        if not source or not destination or source == destination:
            fail(
                f"invalid --destination-id {value!r}; source and destination must be distinct IDs"
            )
        if source in mappings or destination in destinations:
            fail(f"duplicate --destination-id mapping: {value!r}")
        mappings[source] = destination
        destinations.add(destination)
    return mappings


def map_cwd(value: Any, mappings: list[tuple[str, str]]) -> Any:
    if not isinstance(value, str):
        return value
    for old, new in mappings:
        if value == old or value.startswith(old + "/"):
            return new + value[len(old) :]
    return value


def destination_for(home: Path, item: dict[str, Any]) -> Path:
    transcript = item["transcript"]
    root_name = transcript["destination_root"]
    if root_name not in {"sessions", "archived_sessions"}:
        fail(f"invalid transcript destination root: {root_name}")
    relative = Path(transcript["relative_path"])
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"invalid transcript relative path: {relative}")
    return home / root_name / relative


def transplant_destination(
    item: dict[str, Any],
    destination_ids: dict[str, str],
    existing: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    source_id = item["row"]["id"]
    destination_id = destination_ids.get(source_id, source_id)
    destination_row = existing.get(destination_id) if destination_id != source_id else None
    if destination_id != source_id and destination_row is None:
        fail(
            f"destination-native thread does not exist: {destination_id}; "
            "create it on the destination host before transplanting history"
        )
    return destination_id, destination_row


def rewritten_transcript(
    source: Path,
    source_id: str,
    destination_id: str,
    source_cwd: Any,
    destination_cwd: Any,
) -> str:
    lines: list[str] = []
    for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"invalid transcript JSONL {source}:{number}: {exc}")
        if isinstance(item, dict) and isinstance(item.get("payload"), dict):
            payload = item["payload"]
            if item.get("type") == "session_meta":
                if payload.get("id") == source_id:
                    payload["id"] = destination_id
                if payload.get("session_id") == source_id:
                    payload["session_id"] = destination_id
                if payload.get("cwd") == source_cwd:
                    payload["cwd"] = destination_cwd
            elif item.get("type") == "turn_context":
                if payload.get("cwd") == source_cwd:
                    payload["cwd"] = destination_cwd
                roots = payload.get("workspace_roots")
                if isinstance(roots, list):
                    payload["workspace_roots"] = [
                        destination_cwd if root == source_cwd else root for root in roots
                    ]
        lines.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + "\n"


def replace_index_record(
    records: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    destination_id: str,
    source_record: dict[str, Any],
) -> None:
    replacement = dict(source_record)
    replacement["id"] = destination_id
    existing = by_id.get(destination_id)
    if existing is None:
        records.append(replacement)
    else:
        records[records.index(existing)] = replacement
    by_id[destination_id] = replacement


def backup_destination(home: Path, connection: sqlite3.Connection) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = home / "thread-port-backups" / stamp
    suffix = 1
    while backup.exists():
        backup = home / "thread-port-backups" / f"{stamp}-{suffix}"
        suffix += 1
    backup.mkdir(parents=True, mode=0o700)
    with sqlite3.connect(backup / "state_5.sqlite") as target:
        connection.backup(target)
    for name in ("session_index.jsonl", ".codex-global-state.json"):
        source = home / name
        if source.exists():
            shutil.copy2(source, backup / name)
    return backup


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.thread-port-{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def import_plan(home: Path, manifest: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    mappings = parse_cwd_maps(args.cwd_map)
    destination_ids = parse_destination_ids(args.destination_id)
    with open_db(home) as connection:
        existing = {
            row["id"]: dict(row)
            for row in connection.execute("SELECT * FROM threads")
        }
        columns = {row[1] for row in connection.execute("PRAGMA table_info(threads)")}
    actions = []
    for item in manifest["threads"]:
        source_id = item["row"]["id"]
        thread_id, destination_row = transplant_destination(item, destination_ids, existing)
        if destination_row is not None and args.existing != "update":
            fail("--destination-id requires --existing update")
        destination = (
            Path(destination_row["rollout_path"])
            if destination_row is not None
            else destination_for(home, item)
        )
        actions.append(
            {
                "id": thread_id,
                "source_id": source_id,
                "title": (item.get("index") or {}).get("thread_name") or item["row"].get("title", ""),
                "action": "transplant" if destination_row is not None else "update" if thread_id in existing and args.existing == "update" else "skip" if thread_id in existing else "insert",
                "cwd": destination_row.get("cwd") if destination_row is not None else map_cwd(item["row"].get("cwd"), mappings),
                "destination": str(destination),
                "destination_exists": destination.exists(),
                "pinned_after": args.pins == "all" or (args.pins == "preserve" and bool(item.get("pinned"))),
                "compatible_columns": len(set(item["row"]) & columns),
            }
        )
    return {"codex_home": str(home), "thread_count": len(actions), "actions": actions}


def command_import(args: argparse.Namespace) -> None:
    home = codex_home(args.codex_home)
    temp, root, manifest = load_bundle(args.bundle)
    try:
        plan = import_plan(home, manifest, args)
        if not args.apply:
            print(json.dumps({"mode": "preview", **plan}, indent=2, ensure_ascii=False))
            return

        mappings = parse_cwd_maps(args.cwd_map)
        destination_ids = parse_destination_ids(args.destination_id)
        all_index, index_by_id = read_index(home)
        state_path = home / ".codex-global-state.json"
        state = read_json(state_path, {})
        if not isinstance(state, dict):
            fail(f"global state is not an object: {state_path}")
        destination_pins = [item for item in state.get("pinned-thread-ids", []) if isinstance(item, str)]
        imported_ids: list[str] = []
        copied: list[str] = []

        with open_db(home, readonly=False) as connection:
            backup = backup_destination(home, connection)
            columns = [row[1] for row in connection.execute("PRAGMA table_info(threads)")]
            existing = {
                row["id"]: dict(row)
                for row in connection.execute("SELECT * FROM threads")
            }
            connection.execute("BEGIN IMMEDIATE")
            restored_transcripts: list[tuple[Path, Path]] = []
            try:
                for item in manifest["threads"]:
                    row = dict(item["row"])
                    source_id = row["id"]
                    thread_id, destination_row = transplant_destination(
                        item, destination_ids, existing
                    )
                    if destination_row is not None and args.existing != "update":
                        fail("--destination-id requires --existing update")
                    skip_row = thread_id in existing and args.existing == "skip"
                    if not skip_row:
                        destination = (
                            Path(destination_row["rollout_path"])
                            if destination_row is not None
                            else destination_for(home, item)
                        )
                        source = root / item["transcript"]["bundle_path"]
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if destination_row is not None:
                            transcript_backup = backup / "transcripts" / destination.name
                            transcript_backup.parent.mkdir(parents=True, exist_ok=True)
                            if destination.exists():
                                shutil.copy2(destination, transcript_backup)
                                restored_transcripts.append((transcript_backup, destination))
                            atomic_text(
                                destination,
                                rewritten_transcript(
                                    source,
                                    source_id,
                                    thread_id,
                                    row.get("cwd"),
                                    destination_row.get("cwd"),
                                ),
                            )
                            row["id"] = thread_id
                            row["rollout_path"] = str(destination)
                            row["cwd"] = destination_row.get("cwd")
                            for owned in (
                                "archived",
                                "archived_at",
                                "is_pinned",
                                "git_origin_url",
                                "git_branch",
                                "git_sha",
                            ):
                                if owned in destination_row:
                                    row[owned] = destination_row[owned]
                        elif destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != item["transcript"]["sha256"]:
                            fail(f"destination transcript conflict: {destination}")
                        if destination_row is None and not destination.exists():
                            shutil.copy2(source, destination)
                            copied.append(str(destination))
                        if destination_row is None:
                            row["rollout_path"] = str(destination)
                            row["cwd"] = map_cwd(row.get("cwd"), mappings)
                        usable = {key: value for key, value in row.items() if key in columns}
                        names = list(usable)
                        placeholders = ",".join("?" for _ in names)
                        quoted = ",".join(f'"{name}"' for name in names)
                        if thread_id in existing:
                            updates = [name for name in names if name != "id"]
                            assignments = ",".join(f'"{name}"=?' for name in updates)
                            connection.execute(
                                f"UPDATE threads SET {assignments} WHERE id=?",
                                [usable[name] for name in updates] + [thread_id],
                            )
                        else:
                            connection.execute(
                                f"INSERT INTO threads ({quoted}) VALUES ({placeholders})",
                                [usable[name] for name in names],
                            )
                            existing[thread_id] = row
                        imported_ids.append(thread_id)
                    record = item.get("index") or {
                        "id": thread_id,
                        "thread_name": row.get("title", ""),
                        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    }
                    if destination_row is not None or thread_id not in index_by_id:
                        replace_index_record(all_index, index_by_id, thread_id, record)
                    should_pin = args.pins == "all" or (
                        args.pins == "preserve" and bool(item.get("pinned"))
                    )
                    if should_pin and thread_id not in destination_pins:
                        destination_pins.append(thread_id)
                    if args.pins == "none" and thread_id in destination_pins:
                        destination_pins.remove(thread_id)
                connection.commit()
            except Exception:
                connection.rollback()
                for transcript_backup, destination in restored_transcripts:
                    shutil.copy2(transcript_backup, destination)
                raise

        atomic_text(
            home / "session_index.jsonl",
            "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in all_index),
        )
        state["pinned-thread-ids"] = destination_pins
        atomic_text(state_path, json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(
            json.dumps(
                {
                    "mode": "applied",
                    "backup": str(backup),
                    "imported_or_updated": len(imported_ids),
                    "skipped": len(manifest["threads"]) - len(imported_ids),
                    "copied_transcripts": len(copied),
                    "ids": imported_ids,
                },
                indent=2,
            )
        )
    finally:
        temp.cleanup()


def command_verify(args: argparse.Namespace) -> None:
    home = codex_home(args.codex_home)
    temp, _, manifest = load_bundle(args.bundle)
    try:
        pins = set(pinned_ids(home))
        with open_db(home) as connection:
            rows = {
                row["id"]: dict(row)
                for row in connection.execute("SELECT * FROM threads")
                if row["id"] in {item["row"]["id"] for item in manifest["threads"]}
            }
        checks = []
        ok = True
        for item in manifest["threads"]:
            thread_id = item["row"]["id"]
            row = rows.get(thread_id)
            path = Path(row["rollout_path"]) if row else None
            exists = bool(path and path.is_file())
            digest_ok = bool(exists and hashlib.sha256(path.read_bytes()).hexdigest() == item["transcript"]["sha256"])
            pin_ok = not args.require_preserved_pins or not item.get("pinned") or thread_id in pins
            item_ok = row is not None and exists and digest_ok and pin_ok
            ok = ok and item_ok
            checks.append(
                {
                    "id": thread_id,
                    "database_row": row is not None,
                    "transcript": str(path) if path else None,
                    "transcript_exists": exists,
                    "sha256_matches": digest_ok,
                    "pinned": thread_id in pins,
                    "ok": item_ok,
                }
            )
        print(json.dumps({"ok": ok, "thread_count": len(checks), "checks": checks}, indent=2))
        if not ok:
            raise SystemExit(1)
    finally:
        temp.cleanup()


def add_selectors(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pinned", action="store_true", help="select IDs in pinned-thread-ids")
    parser.add_argument("--id", action="append", help="select exact UUID or codex://threads/UUID")
    parser.add_argument("--query", action="append", help="match title, first message, or index title")
    parser.add_argument("--cwd", action="append", help="select exact workspace path")
    parser.add_argument("--archive-state", choices=("active", "archived"))
    parser.add_argument("--all", action="store_true", help="select every thread")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subcommands = root.add_subparsers(dest="command", required=True)

    inventory = subcommands.add_parser("inventory", help="preview source selection")
    inventory.add_argument("--codex-home")
    add_selectors(inventory)
    inventory.set_defaults(function=command_inventory)

    export = subcommands.add_parser("export", help="create portable bundle")
    export.add_argument("--codex-home")
    export.add_argument("--output", required=True)
    add_selectors(export)
    export.set_defaults(function=command_export)

    import_parser = subcommands.add_parser("import", help="preview or apply merge import")
    import_parser.add_argument("--codex-home")
    import_parser.add_argument("--bundle", required=True)
    import_parser.add_argument("--cwd-map", action="append", metavar="OLD=NEW")
    import_parser.add_argument(
        "--pins",
        choices=("preserve", "all", "none"),
        default="none",
        help="destination pin behavior; defaults to none and must be explicit to preserve or add pins",
    )
    import_parser.add_argument("--existing", choices=("skip", "update"), default="skip")
    import_parser.add_argument(
        "--destination-id",
        action="append",
        metavar="SOURCE=DESTINATION",
        help=(
            "transplant source history into an existing destination-native thread; "
            "requires --existing update"
        ),
    )
    import_parser.add_argument("--apply", action="store_true")
    import_parser.set_defaults(function=command_import)

    verify = subcommands.add_parser("verify", help="verify imported rows, transcripts, and pins")
    verify.add_argument("--codex-home")
    verify.add_argument("--bundle", required=True)
    verify.add_argument(
        "--require-preserved-pins",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="also require every source-pinned thread to be pinned at the destination",
    )
    verify.set_defaults(function=command_verify)
    return root


def main() -> None:
    args = parser().parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
