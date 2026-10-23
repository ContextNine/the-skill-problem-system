#!/usr/bin/env python3
"""Preview or edit saved remote Codex projects while the desktop is closed."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import time


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def desktop_is_running() -> bool:
    # macOS reports the full executable path, so pgrep -x can miss the desktop.
    process_paths = subprocess.run(["ps", "-axo", "comm="], check=True,
                                   capture_output=True, text=True).stdout.splitlines()
    executables = ("/ChatGPT.app/Contents/MacOS/ChatGPT", "/Codex.app/Contents/MacOS/Codex")
    return any(path.strip().endswith(executable) for path in process_paths for executable in executables)


def read_operations(path: Path) -> list[dict]:
    operations = json.loads(path.read_text())
    if not isinstance(operations, list) or not operations:
        fail("operations must be a non-empty JSON list")
    ids = set()
    for op in operations:
        if not isinstance(op, dict) or set(op) - {"previous_assignments"} != {"project_id", "host_id", "from_path", "to_path", "name", "thread_ids"}:
            fail("each operation requires project_id, host_id, from_path, to_path, name, thread_ids")
        for key in ("project_id", "host_id", "from_path", "to_path", "name"):
            if not isinstance(op[key], str) or not op[key].strip():
                fail(f"{key} must be a non-empty string")
        if not op["host_id"].startswith("remote-"):
            fail("only saved remote projects are supported")
        for key in ("from_path", "to_path"):
            p = PurePosixPath(op[key])
            if not p.is_absolute() or ".." in p.parts or str(p) != op[key] or str(p) == "/":
                fail(f"{key} must be a normalized absolute remote path")
        if op["project_id"] in ids:
            fail("duplicate project operation")
        ids.add(op["project_id"])
        if not isinstance(op.get("previous_assignments", {}), dict):
            fail("previous_assignments must be an exact thread-to-assignment map")
        if not isinstance(op["thread_ids"], list) or not all(isinstance(t, str) and t for t in op["thread_ids"]):
            fail("thread_ids must contain the verified source-workspace thread IDs")
    return operations


def build_plan(state: dict, operations: list[dict]) -> tuple[dict, list[dict]]:
    result = copy.deepcopy(state)
    projects = result.get("remote-projects")
    assignments = result.setdefault("thread-project-assignments", {})
    if not isinstance(projects, list) or not isinstance(assignments, dict):
        fail("invalid remote-projects or thread-project-assignments schema")
    changes = []
    for op in operations:
        matches = [p for p in projects if p.get("id") == op["project_id"]]
        if len(matches) != 1:
            fail(f"expected one saved project {op['project_id']}")
        project = matches[0]
        if project.get("hostId") != op["host_id"] or project.get("remotePath") not in (op["from_path"], op["to_path"]):
            fail(f"saved project host/path changed: {op['project_id']}")
        if any(p.get("id") != op["project_id"] and p.get("hostId") == op["host_id"]
               and p.get("remotePath") == op["to_path"] for p in projects):
            fail(f"another project already owns {op['host_id']}:{op['to_path']}")
        selected = set(op["thread_ids"])
        selected.update(t for t, a in assignments.items() if a.get("projectId") == op["project_id"])
        for thread_id in selected:
            old = assignments.get(thread_id)
            if old is not None and (old.get("projectKind") != "remote" or old.get("projectId") != op["project_id"]
                                    or old.get("hostId") != op["host_id"]):
                approved_previous = op.get("previous_assignments", {}).get(thread_id)
                if old != approved_previous or old.get("projectKind") != "remote":
                    fail(f"thread has a different explicit project assignment: {thread_id}")
            if old is not None and old.get("path") not in (None, op["from_path"], op["to_path"]):
                fail(f"thread has a different assigned path: {thread_id}")
            assignments[thread_id] = {**(old or {}), "projectKind": "remote", "projectId": op["project_id"],
                                      "hostId": op["host_id"], "path": op["to_path"]}
        project["remotePath"] = op["to_path"]
        project["label"] = op["name"]
        changes.append({"project_id": op["project_id"], "host_id": op["host_id"],
                        "from_path": op["from_path"], "to_path": op["to_path"],
                        "name": op["name"], "thread_ids": sorted(selected)})
    return result, changes


def apply_file(path: Path, operations: list[dict]) -> dict:
    if desktop_is_running():
        fail("Codex desktop is running; quit it before editing saved project state")
    original = path.read_bytes()
    state = json.loads(original)
    result, changes = build_plan(state, operations)
    if result == state:
        return {"mode": "unchanged", "changes": changes}
    backup_root = path.parent / "thread-port-backups"
    backup_root.mkdir(exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix="project-edit-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=backup_root))
    shutil.copy2(path, backup / path.name)
    if path.with_name(path.name + ".bak").exists():
        shutil.copy2(path.with_name(path.name + ".bak"), backup / (path.name + ".bak"))
    fd, temporary = tempfile.mkstemp(prefix=".project-edit-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        if desktop_is_running() or path.read_bytes() != original:
            fail("desktop reopened or state changed during preview; retry with all writers closed")
        os.replace(temporary, path)
        if json.loads(path.read_text()) != result:
            fail(f"written state failed verification; backup: {backup}")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    report = {"mode": "applied", "backup": str(backup), "original_sha256": hashlib.sha256(original).hexdigest(), "changes": changes}
    (backup / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path.home() / ".codex/.codex-global-state.json")
    parser.add_argument("--operations", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--wait-for-desktop-exit", type=int, default=0, metavar="SECONDS")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    operations = read_operations(args.operations)
    if args.wait_for_desktop_exit and not args.apply:
        fail("waiting requires --apply")
    deadline = time.monotonic() + args.wait_for_desktop_exit
    while args.apply and desktop_is_running() and time.monotonic() < deadline:
        time.sleep(1)
    if args.apply:
        report = apply_file(args.state.expanduser().resolve(), operations)
    else:
        _, changes = build_plan(json.loads(args.state.read_text()), operations)
        report = {"mode": "preview", "changes": changes}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        os.chmod(args.report, 0o600)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
