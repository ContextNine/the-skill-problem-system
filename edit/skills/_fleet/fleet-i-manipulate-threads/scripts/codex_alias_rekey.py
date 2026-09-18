#!/usr/bin/env python3
"""Re-associate selected Codex desktop threads with a replacement SSH alias."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def read_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read Codex desktop state {path}: {exc}")
    if not isinstance(state, dict):
        fail(f"Codex desktop state is not an object: {path}")
    return state


def desktop_is_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def atomic_state(path: Path, state: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.alias-rekey-{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def project_by_id(projects: list[dict[str, Any]], project_id: str) -> dict[str, Any]:
    matches = [project for project in projects if project.get("id") == project_id]
    if len(matches) != 1:
        fail(f"expected one project template {project_id}, found {len(matches)}")
    return matches[0]


def destination_project(
    projects: list[dict[str, Any]], template: dict[str, Any], destination_host: str
) -> dict[str, Any] | None:
    matches = [
        project
        for project in projects
        if project.get("hostId") == destination_host
        and project.get("remotePath") == template.get("remotePath")
        and project.get("label") == template.get("label")
    ]
    if len(matches) > 1:
        fail(
            "multiple destination projects match "
            f"{destination_host}:{template.get('remotePath')}"
        )
    return matches[0] if matches else None


def build_plan(state: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    projects = state.get("remote-projects", [])
    assignments = state.get("thread-project-assignments", {})
    if not isinstance(projects, list) or not all(isinstance(item, dict) for item in projects):
        fail("remote-projects is missing or invalid")
    if not isinstance(assignments, dict):
        fail("thread-project-assignments is missing or invalid")

    actions: list[dict[str, Any]] = []
    planned_projects: dict[str, dict[str, Any]] = {}
    for thread_id in args.thread:
        assignment = assignments.get(thread_id)
        if args.project_template_id:
            template = project_by_id(projects, args.project_template_id)
        else:
            if not isinstance(assignment, dict):
                fail(f"thread has no project assignment: {thread_id}")
            if assignment.get("hostId") != args.source_host:
                fail(
                    f"thread {thread_id} belongs to {assignment.get('hostId')}, "
                    f"not {args.source_host}"
                )
            template = project_by_id(projects, str(assignment.get("projectId")))
        if template.get("hostId") != args.source_host:
            fail(
                f"project template {template.get('id')} belongs to {template.get('hostId')}, "
                f"not {args.source_host}"
            )

        key = f"{template.get('remotePath')}\0{template.get('label')}"
        target = destination_project(projects, template, args.destination_host)
        if target is None:
            target = planned_projects.setdefault(
                key,
                {
                    "id": None,
                    "hostId": args.destination_host,
                    "remotePath": template.get("remotePath"),
                    "label": template.get("label"),
                },
            )
        actions.append(
            {
                "thread_id": thread_id,
                "source_project_id": template.get("id"),
                "destination_project_id": target.get("id"),
                "destination_project_will_be_created": target.get("id") is None,
                "destination_host": args.destination_host,
                "remote_path": template.get("remotePath"),
                "label": template.get("label"),
            }
        )
    return {"actions": actions, "planned_projects": list(planned_projects.values())}


def apply_plan(state: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    projects = state["remote-projects"]
    assignments = state["thread-project-assignments"]
    created_by_key: dict[str, dict[str, Any]] = {}
    for planned in plan["planned_projects"]:
        project = dict(planned)
        project["id"] = str(uuid.uuid4())
        projects.append(project)
        key = f"{project.get('remotePath')}\0{project.get('label')}"
        created_by_key[key] = project

    applied: list[dict[str, Any]] = []
    for action in plan["actions"]:
        project_id = action["destination_project_id"]
        if project_id is None:
            key = f"{action.get('remote_path')}\0{action.get('label')}"
            project_id = created_by_key[key]["id"]
        assignments[action["thread_id"]] = {
            "projectKind": "remote",
            "projectId": project_id,
            "path": action["remote_path"],
            "hostId": action["destination_host"],
            "pendingCoreUpdate": False,
        }
        applied.append({**action, "destination_project_id": project_id})
    return {"actions": applied, "created_projects": list(created_by_key.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        default=str(Path.home() / ".codex" / ".codex-global-state.json"),
    )
    parser.add_argument("--source-host", required=True)
    parser.add_argument("--destination-host", required=True)
    parser.add_argument("--thread", action="append", required=True)
    parser.add_argument(
        "--project-template-id",
        help="use this source project when the selected thread has no source-host assignment",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = Path(args.state).expanduser().resolve()
    state = read_state(path)
    plan = build_plan(state, args)
    if not args.apply:
        print(json.dumps({"mode": "preview", **plan}, indent=2, ensure_ascii=False))
        return
    if desktop_is_running():
        fail("ChatGPT desktop is running; quit it before applying alias re-key state")

    backup_root = path.parent / "thread-port-backups"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_root / f"alias-rekey-{stamp}"
    suffix = 1
    while backup.exists():
        backup = backup_root / f"alias-rekey-{stamp}-{suffix}"
        suffix += 1
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(path, backup / path.name)

    applied = apply_plan(state, plan)
    atomic_state(path, state)
    print(
        json.dumps(
            {"mode": "applied", "backup": str(backup), **applied},
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
