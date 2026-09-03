#!/usr/bin/env python3
"""Update repository-scoped GH skill installs and record verified source facts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

import working_repo_skills


class SkillSourceUpdateError(RuntimeError):
    pass


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def gh_skill_list(root: Path) -> list[dict[str, Any]]:
    process = run(["gh", "skill", "list", "--dir", str(root), "--json", "skillName,sourceURL,version,pinned,path"])
    if process.returncode != 0:
        raise SkillSourceUpdateError((process.stderr or process.stdout).strip() or "gh skill list failed")
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise SkillSourceUpdateError(f"gh skill list returned invalid JSON: {exc}") from exc
    if not isinstance(value, list):
        raise SkillSourceUpdateError("gh skill list returned no skill list")
    resolved_root = root.resolve()
    for item in value:
        path = Path(str(item.get("path") or "")).resolve()
        if path.parent != resolved_root or not path.is_dir() or path.is_symlink():
            raise SkillSourceUpdateError(f"GitHub-managed skill path escapes its owner directory: {path}")
    return sorted(value, key=lambda item: str(item.get("skillName")))


def gh_roots(root: Path) -> dict[str, Path]:
    github = root / "_system/agents/skills/github"
    if not github.is_dir():
        raise SkillSourceUpdateError(f"GitHub skill root is missing: {github}")
    result: dict[str, Path] = {}
    for repository in sorted(github.iterdir()):
        if repository.name in {".DS_Store", ".gitkeep"}:
            continue
        skills = repository / "skills"
        if repository.is_symlink() or not repository.is_dir() or not skills.is_dir():
            raise SkillSourceUpdateError(f"GitHub repository install needs a real skills directory: {repository}")
        if not gh_skill_list(skills):
            raise SkillSourceUpdateError(f"GitHub repository install contains no tracked skills: {skills}")
        result[repository.name] = skills
    return result


def selected_roots(filters: list[str], roots: dict[str, Path]) -> dict[str, Path]:
    if not filters:
        return roots
    selected: dict[str, Path] = {}
    for value in filters:
        if not value.startswith("gh:"):
            raise SkillSourceUpdateError(
                f"unknown skill source {value!r}; local checkout updates belong to workspace reconciliation, "
                "and GH installs use gh:<repository-directory>"
            )
        source_id = value.removeprefix("gh:")
        if source_id not in roots:
            raise SkillSourceUpdateError(f"unknown GitHub-managed repository source: {value}")
        selected[source_id] = roots[source_id]
    return selected


def plan_sources(root: Path, filters: list[str]) -> dict[str, Any]:
    selected = selected_roots(filters, gh_roots(root))
    repositories: list[dict[str, Any]] = []
    for source_id, skills in selected.items():
        before = gh_skill_list(skills)
        process = run(["gh", "skill", "update", "--all", "--dir", str(skills), "--dry-run"])
        if process.returncode != 0:
            raise SkillSourceUpdateError(
                (process.stderr or process.stdout).strip() or f"gh skill update dry-run failed for {source_id}"
            )
        repositories.append({
            "kind": "github-managed",
            "id": f"gh:{source_id}",
            "status": "checked",
            "ready": True,
            "path": str(skills),
            "skill_count": len(before),
            "preview": process.stdout.strip(),
        })
    return {"ready": True, "github": repositories}


def apply_sources(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    del root
    if not plan.get("ready"):
        raise SkillSourceUpdateError("skill-source plan has blockers")
    updated: list[dict[str, Any]] = []
    for item in plan.get("github", []):
        skills = Path(str(item["path"]))
        before = {str(skill["path"]): str(skill.get("version") or "") for skill in gh_skill_list(skills)}
        process = run(["gh", "skill", "update", "--all", "--dir", str(skills)])
        if process.returncode != 0:
            raise SkillSourceUpdateError(
                (process.stderr or process.stdout).strip() or f"gh skill update failed for {item['id']}"
            )
        after = gh_skill_list(skills)
        changed = sum(before.get(str(skill["path"])) != str(skill.get("version") or "") for skill in after)
        updated.append({**item, "status": "updated" if changed else "current", "skill_count": len(after), "changed_skills": changed})
    return {"ready": True, "github": updated}


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()):
        relative = item.relative_to(path)
        if item.is_dir() or any(part in {".DS_Store", "__pycache__"} for part in relative.parts) or item.suffix == ".pyc":
            continue
        digest.update(relative.as_posix().encode() + b"\0")
        if item.is_symlink():
            digest.update(b"L\0" + os.readlink(item).encode())
        elif item.is_file():
            digest.update(b"F\0" + item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def metadata_value(skill: Path, key: str) -> str | None:
    match = re.search(rf"(?m)^\s*{re.escape(key)}:\s*([^\s]+)\s*$", (skill / "SKILL.md").read_text(encoding="utf-8"))
    return match.group(1).strip("\"'") if match else None


def read_snapshot_state(machine: dict[str, Any], source_id: str) -> dict[str, Any]:
    relative = ".agents/.vault-agent-skill-snapshot.json"
    if machine["id"] == source_id:
        path = Path(str(machine["home"])) / relative
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SkillSourceUpdateError(f"cannot read local skill distribution state: {exc}") from exc
    else:
        process = run([
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", str(machine["ssh_alias"]),
            "python3 -c 'import pathlib; print(pathlib.Path.home().joinpath(\".agents/.vault-agent-skill-snapshot.json\").read_text())'",
        ])
        if process.returncode != 0:
            raise SkillSourceUpdateError(f"cannot read skill distribution state from {machine['id']}")
        try:
            value = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise SkillSourceUpdateError(f"invalid skill distribution state from {machine['id']}") from exc
    skills = value.get("skills")
    if value.get("schema_version") not in {1, 2} or not isinstance(skills, dict):
        raise SkillSourceUpdateError(f"unsupported skill distribution state on {machine['id']}")
    serialized = json.dumps(skills, sort_keys=True, separators=(",", ":")).encode()
    return {"skill_count": len(skills), "snapshot_sha256": hashlib.sha256(serialized).hexdigest()}


def build_lock(root: Path, source_config: dict[str, Any], machines: list[dict[str, Any]], source_id: str) -> dict[str, Any]:
    plan = working_repo_skills.plan(root, home=Path.home(), require_sources=True)
    local_sources = [
        {
            "name": skill.name,
            "declared_path": skill.declared_path,
            "materialization": skill.materialization,
            "sha256": tree_digest(skill.canonical_path),
        }
        for skill in plan.skills if skill.origin == "repo"
    ]
    github: list[dict[str, Any]] = []
    for repository, skills_root in gh_roots(root).items():
        for item in gh_skill_list(skills_root):
            path = Path(str(item["path"]))
            github.append({
                "repository": repository,
                "id": item["skillName"],
                "source_url": item["sourceURL"],
                "version": item["version"],
                "tree_sha": metadata_value(path, "github-tree-sha"),
                "sha256": tree_digest(path),
            })
    distributed = {str(machine["id"]): read_snapshot_state(machine, source_id) for machine in machines}
    unique_snapshots = {item["snapshot_sha256"] for item in distributed.values()}
    unique_counts = {item["skill_count"] for item in distributed.values()}
    if len(unique_snapshots) != 1 or len(unique_counts) != 1:
        raise SkillSourceUpdateError("distributed fleet skill evidence does not align")
    return {
        "schema_version": 2,
        "verified_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_schema_version": source_config.get("schema_version"),
        "gh_skills": sorted(github, key=lambda item: (str(item["repository"]), str(item["id"]))),
        "local_repo_skills": sorted(local_sources, key=lambda item: str(item["name"])),
        "distributed_snapshots": distributed,
    }


def atomic_write_lock(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
