#!/usr/bin/env python3
"""Safely update configured skill sources and record verified snapshot facts."""

from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import tempfile
from typing import Any
from urllib.parse import quote


class SkillSourceUpdateError(RuntimeError):
    pass


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def command_output(command: list[str], *, cwd: Path | None = None) -> str:
    process = run(command, cwd=cwd)
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).strip().splitlines()
        raise SkillSourceUpdateError(
            f"command failed: {' '.join(command)}: {detail[-1][:500] if detail else 'no output'}"
        )
    return process.stdout.strip()


def github_json(endpoint: str) -> Any:
    output = command_output(["gh", "api", endpoint])
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise SkillSourceUpdateError(f"GitHub API returned invalid JSON for {endpoint}: {exc}") from exc


def normalize_github_remote(value: str) -> str | None:
    match = re.fullmatch(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?", value)
    if not match:
        match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?", value)
    return match.group(1).casefold() if match else None


def compare_github_commits(github: str, local: str, remote: str, path: Path) -> str:
    known = run(["git", "cat-file", "-e", f"{remote}^{{commit}}"], cwd=path).returncode == 0
    if known:
        if run(["git", "merge-base", "--is-ancestor", local, remote], cwd=path).returncode == 0:
            return "behind"
        if run(["git", "merge-base", "--is-ancestor", remote, local], cwd=path).returncode == 0:
            return "ahead"
        return "diverged"
    process = run(["gh", "api", f"repos/{github}/compare/{local}...{remote}", "--jq", ".status"])
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).strip().splitlines()
        raise SkillSourceUpdateError(
            f"cannot compare {github} commits without mutating the checkout: "
            f"{detail[-1][:500] if detail else 'GitHub comparison failed'}"
        )
    return process.stdout.strip()


def inspect_cloned_source(record: dict[str, Any]) -> dict[str, Any]:
    repository_id = str(record["id"])
    path = Path(os.path.expanduser(str(record["path"]))).resolve()
    expected_github = normalize_github_remote(str(record["url"]))
    base = {
        "kind": "cloned",
        "id": repository_id,
        "path": str(path),
        "github": expected_github,
        "url": str(record["url"]),
        "ref": str(record["ref"]),
    }
    if not path.is_dir() or not (path / ".git").exists():
        return {**base, "status": "blocked", "ready": False, "detail": "configured checkout is missing"}
    dirty = command_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=path)
    if dirty:
        return {**base, "status": "blocked", "ready": False, "detail": "checkout is dirty; preserving all work"}
    branch = run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=path)
    if branch.returncode != 0:
        return {**base, "status": "blocked", "ready": False, "detail": "checkout is detached"}
    expected_ref = str(record["ref"])
    if branch.stdout.strip() != expected_ref:
        return {
            **base,
            "status": "blocked",
            "ready": False,
            "detail": f"checkout branch is {branch.stdout.strip()!r}, expected {expected_ref!r}",
        }
    origin = command_output(["git", "remote", "get-url", "origin"], cwd=path)
    origin_matches = (
        normalize_github_remote(origin) == expected_github
        if expected_github is not None
        else origin.removesuffix(".git") == str(record["url"]).removesuffix(".git")
    )
    if not origin_matches:
        return {**base, "status": "blocked", "ready": False, "detail": "origin does not match configured GitHub repository"}
    upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=path)
    if upstream.returncode != 0 or upstream.stdout.strip() != f"origin/{expected_ref}":
        return {**base, "status": "blocked", "ready": False, "detail": f"upstream must be origin/{expected_ref}"}
    local = command_output(["git", "rev-parse", "HEAD"], cwd=path)
    remote_line = command_output(
        ["git", "ls-remote", "--heads", str(record["url"]), f"refs/heads/{expected_ref}"],
        cwd=path,
    )
    fields = remote_line.split()
    if len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{40}", fields[0]):
        return {**base, "status": "blocked", "ready": False, "detail": "configured remote branch did not resolve uniquely"}
    remote = fields[0]
    if local == remote:
        return {**base, "status": "current", "ready": True, "local_commit": local, "remote_commit": remote}
    comparison = compare_github_commits(str(expected_github), local, remote, path)
    if comparison != "behind":
        return {
            **base,
            "status": "blocked",
            "ready": False,
            "local_commit": local,
            "remote_commit": remote,
            "detail": f"checkout is {comparison}; only a clean fast-forward is allowed",
        }
    return {
        **base,
        "status": "planned-fast-forward",
        "ready": True,
        "local_commit": local,
        "remote_commit": remote,
    }


def apply_cloned_source(plan: dict[str, Any]) -> dict[str, Any]:
    if plan["status"] == "current":
        return dict(plan)
    if plan["status"] != "planned-fast-forward" or not plan.get("ready"):
        raise SkillSourceUpdateError(f"source {plan['id']} has no applicable fast-forward plan")
    path = Path(str(plan["path"]))
    if command_output(["git", "rev-parse", "HEAD"], cwd=path) != plan["local_commit"]:
        raise SkillSourceUpdateError(f"source {plan['id']} changed after planning")
    command_output(["git", "fetch", "--prune", "origin", str(plan["ref"])], cwd=path)
    fetched = command_output(["git", "rev-parse", "FETCH_HEAD"], cwd=path)
    if fetched != plan["remote_commit"]:
        raise SkillSourceUpdateError(f"source {plan['id']} remote changed after planning")
    if run(["git", "merge-base", "--is-ancestor", str(plan["local_commit"]), fetched], cwd=path).returncode != 0:
        raise SkillSourceUpdateError(f"source {plan['id']} is not fast-forwardable after fetch")
    command_output(["git", "merge", "--ff-only", fetched], cwd=path)
    accepted = inspect_cloned_source(
        {
            "id": plan["id"],
            "path": plan["path"],
            "url": plan["url"],
            "ref": plan["ref"],
        }
    )
    if accepted.get("status") != "current" or accepted.get("local_commit") != plan["remote_commit"]:
        raise SkillSourceUpdateError(f"source {plan['id']} failed post-fast-forward acceptance")
    return {**accepted, "status": "updated", "before_commit": plan["local_commit"]}


def gh_skill_list(root: Path) -> list[dict[str, Any]]:
    process = run(
        [
            "gh",
            "skill",
            "list",
            "--dir",
            str(root),
            "--json",
            "skillName,sourceURL,version,pinned,path",
        ]
    )
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


def selected_source_names(filters: list[str], cloned_ids: set[str], gh_names: set[str]) -> tuple[set[str], set[str]]:
    if not filters:
        return set(cloned_ids), set(gh_names)
    cloned: set[str] = set()
    github: set[str] = set()
    for value in filters:
        if value.startswith("gh:"):
            name = value.removeprefix("gh:")
            if name not in gh_names:
                raise SkillSourceUpdateError(f"unknown GitHub-managed skill source: {value}")
            github.add(name)
        elif value in cloned_ids:
            cloned.add(value)
        else:
            raise SkillSourceUpdateError(
                f"unknown skill source {value!r}; use a cloned repository ID or gh:<skill-name>"
            )
    return cloned, github


def plan_sources(
    root: Path,
    records: list[dict[str, Any]],
    filters: list[str],
) -> dict[str, Any]:
    gh_root = root / "_system/agents/skills/github"
    github_skills = gh_skill_list(gh_root)
    cloned_ids = {str(record["id"]) for record in records if record.get("sync_enabled", True)}
    gh_by_name = {str(item["skillName"]): item for item in github_skills}
    selected_cloned, selected_gh = selected_source_names(filters, cloned_ids, set(gh_by_name))
    cloned = [inspect_cloned_source(record) for record in records if record.get("sync_enabled", True) and record["id"] in selected_cloned]
    gh_output = ""
    if selected_gh:
        process = run(["gh", "skill", "update", *sorted(selected_gh), "--dir", str(gh_root), "--dry-run"])
        if process.returncode != 0:
            raise SkillSourceUpdateError((process.stderr or process.stdout).strip() or "gh skill update dry-run failed")
        gh_output = process.stdout.strip()
    github = [
        {
            "kind": "github-managed",
            "id": f"gh:{name}",
            "status": "checked",
            "ready": True,
            "version": gh_by_name[name].get("version"),
            "source_url": gh_by_name[name].get("sourceURL"),
            "path": gh_by_name[name].get("path"),
        }
        for name in sorted(selected_gh)
    ]
    return {
        "ready": all(item.get("ready") for item in cloned),
        "cloned": cloned,
        "github": github,
        "github_preview": gh_output,
    }


def apply_sources(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    if not plan.get("ready"):
        raise SkillSourceUpdateError("skill-source plan has blockers")
    cloned = [apply_cloned_source(item) for item in plan.get("cloned", [])]
    github_before = plan.get("github", [])
    github: list[dict[str, Any]] = []
    if github_before:
        names = [str(item["id"]).removeprefix("gh:") for item in github_before]
        process = run(
            [
                "gh",
                "skill",
                "update",
                *names,
                "--dir",
                str(root / "_system/agents/skills/github"),
                "--all",
            ]
        )
        if process.returncode != 0:
            raise SkillSourceUpdateError((process.stderr or process.stdout).strip() or "gh skill update failed")
        after = {str(item["skillName"]): item for item in gh_skill_list(root / "_system/agents/skills/github")}
        for before in github_before:
            name = str(before["id"]).removeprefix("gh:")
            current = after[name]
            materialized = materialize_github_symlinks(Path(str(current["path"])))
            github.append(
                {
                    "kind": "github-managed",
                    "id": f"gh:{name}",
                    "status": "current" if before.get("version") == current.get("version") else "updated",
                    "before_version": before.get("version"),
                    "version": current.get("version"),
                    "source_url": current.get("sourceURL"),
                    "materialized_symlinks": materialized,
                }
            )
    return {"ready": True, "cloned": cloned, "github": github}


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()):
        if item.is_dir() or item.name in {".DS_Store"} or item.suffix == ".pyc":
            continue
        relative = item.relative_to(path).as_posix().encode()
        if item.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + os.readlink(item).encode() + b"\0")
        elif item.is_file():
            digest.update(b"F\0" + relative + b"\0")
            digest.update(item.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def metadata_value(skill: Path, key: str) -> str | None:
    match = re.search(rf"(?m)^\s*{re.escape(key)}:\s*([^\s]+)\s*$", (skill / "SKILL.md").read_text(encoding="utf-8"))
    return match.group(1).strip('"\'') if match else None


def github_blob(repository: str, sha: str) -> bytes:
    value = github_json(f"repos/{repository}/git/blobs/{sha}")
    if not isinstance(value, dict) or value.get("encoding") != "base64" or not isinstance(value.get("content"), str):
        raise SkillSourceUpdateError(f"unsupported GitHub blob response for {repository}@{sha}")
    try:
        return base64.b64decode(value["content"], validate=False)
    except ValueError as exc:
        raise SkillSourceUpdateError(f"invalid GitHub blob encoding for {repository}@{sha}") from exc


def download_github_path(
    repository: str,
    ref: str,
    repository_path: str,
    destination: Path,
    *,
    seen: set[str],
) -> None:
    normalized = posixpath.normpath(repository_path)
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
        raise SkillSourceUpdateError(f"GitHub skill symlink escapes its repository: {repository_path}")
    if normalized in seen:
        raise SkillSourceUpdateError(f"GitHub skill symlink cycle at {repository}:{normalized}")
    seen.add(normalized)
    endpoint = f"repos/{repository}/contents/{quote(normalized, safe='/')}?ref={quote(ref, safe='')}"
    value = github_json(endpoint)
    if isinstance(value, list):
        destination.mkdir(parents=True, exist_ok=True)
        for child in value:
            if not isinstance(child, dict) or not child.get("name") or not child.get("path"):
                raise SkillSourceUpdateError(f"invalid GitHub directory entry under {repository}:{normalized}")
            download_github_path(
                repository,
                ref,
                str(child["path"]),
                destination / str(child["name"]),
                seen=set(seen),
            )
        return
    if not isinstance(value, dict):
        raise SkillSourceUpdateError(f"invalid GitHub content response for {repository}:{normalized}")
    entry_type = value.get("type")
    if entry_type == "symlink":
        target = value.get("target")
        if not isinstance(target, str):
            raise SkillSourceUpdateError(f"GitHub symlink lacks target: {repository}:{normalized}")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(normalized), target))
        download_github_path(repository, ref, resolved, destination, seen=seen)
        return
    if entry_type != "file" or not isinstance(value.get("sha"), str):
        raise SkillSourceUpdateError(
            f"unsupported GitHub skill entry {entry_type!r}: {repository}:{normalized}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(github_blob(repository, str(value["sha"])))


def materialize_github_symlinks(skill: Path) -> list[str]:
    repository_url = metadata_value(skill, "github-repo")
    repository = normalize_github_remote(repository_url or "")
    ref = metadata_value(skill, "github-ref")
    source_root = metadata_value(skill, "github-path")
    tree_sha = metadata_value(skill, "github-tree-sha")
    if not all((repository, ref, source_root, tree_sha)):
        raise SkillSourceUpdateError(f"GitHub-managed skill lacks source metadata: {skill}")
    value = github_json(f"repos/{repository}/git/trees/{tree_sha}?recursive=1")
    entries = value.get("tree") if isinstance(value, dict) else None
    if not isinstance(entries, list):
        raise SkillSourceUpdateError(f"GitHub skill tree did not resolve: {repository}@{tree_sha}")
    materialized: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("mode") != "120000":
            continue
        relative = str(entry.get("path") or "")
        if not relative or relative.startswith("../") or Path(relative).is_absolute():
            raise SkillSourceUpdateError(f"invalid GitHub skill symlink path: {relative!r}")
        local = skill / relative
        if local.is_symlink() or local.is_file():
            local.unlink()
        elif local.is_dir():
            shutil.rmtree(local)
        target_blob = github_blob(str(repository), str(entry.get("sha"))).decode("utf-8").strip()
        target = posixpath.normpath(
            posixpath.join(str(source_root), posixpath.dirname(relative), target_blob)
        )
        download_github_path(str(repository), str(ref), target, local, seen=set())
        materialized.append(relative)
    validate_portable_skill(skill)
    return materialized


def validate_portable_skill(skill: Path) -> None:
    symlinks = [item for item in skill.rglob("*") if item.is_symlink()]
    if symlinks:
        raise SkillSourceUpdateError(f"GitHub-managed skill contains a non-portable symlink: {symlinks[0]}")
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    for raw in re.findall(r"\]\(([^)]+)\)", text):
        target = raw.split("#", 1)[0].strip().strip("<>")
        if not target or "://" in target or target.startswith(("#", "mailto:")):
            continue
        if not (skill / target).exists():
            raise SkillSourceUpdateError(f"GitHub-managed skill has a missing relative reference: {target}")


def observed_cloned_source(record: dict[str, Any]) -> dict[str, Any]:
    """Record local facts without making an unsafe checkout eligible for update."""
    path = Path(os.path.expanduser(str(record["path"]))).resolve()
    if not path.is_dir() or not (path / ".git").exists():
        raise SkillSourceUpdateError(f"cannot record missing cloned source: {record['id']}")
    commit = command_output(["git", "rev-parse", "HEAD"], cwd=path)
    branch_process = run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=path)
    branch = branch_process.stdout.strip() if branch_process.returncode == 0 else None
    dirty = bool(command_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=path))
    origin = command_output(["git", "remote", "get-url", "origin"], cwd=path)
    acceptance = inspect_cloned_source(record)
    return {
        "id": record["id"],
        "github": normalize_github_remote(str(record["url"])),
        "ref": record["ref"],
        "resolved_commit": commit,
        "branch": branch,
        "detached": branch is None,
        "dirty": dirty,
        "origin_matches": normalize_github_remote(origin) == normalize_github_remote(str(record["url"])),
        "update_status": acceptance.get("status"),
        "update_eligible": bool(acceptance.get("ready")),
        **({"update_detail": acceptance["detail"]} if acceptance.get("detail") else {}),
    }


def read_snapshot_state(machine: dict[str, Any], source_id: str) -> dict[str, Any]:
    relative = ".agents/.vault-agent-skill-snapshot.json"
    if machine["id"] == source_id:
        path = Path(str(machine["home"])) / relative
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SkillSourceUpdateError(f"cannot read local skill snapshot state: {exc}") from exc
    else:
        process = run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                str(machine["ssh_alias"]),
                "python3 -c 'import json,pathlib; print(pathlib.Path.home().joinpath(\".agents/.vault-agent-skill-snapshot.json\").read_text())'",
            ]
        )
        if process.returncode != 0:
            raise SkillSourceUpdateError(f"cannot read skill snapshot state from {machine['id']}")
        try:
            value = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise SkillSourceUpdateError(f"invalid skill snapshot state from {machine['id']}") from exc
    if value.get("schema_version") != 1 or not isinstance(value.get("skills"), dict):
        raise SkillSourceUpdateError(f"unsupported skill snapshot state on {machine['id']}")
    serialized = json.dumps(value["skills"], sort_keys=True, separators=(",", ":")).encode()
    return {
        "skill_count": len(value["skills"]),
        "snapshot_sha256": hashlib.sha256(serialized).hexdigest(),
    }


def build_lock(
    root: Path,
    records: list[dict[str, Any]],
    machines: list[dict[str, Any]],
    source_id: str,
) -> dict[str, Any]:
    external = []
    projections = []
    for record in records:
        if not record.get("sync_enabled", True):
            continue
        external.append(observed_cloned_source(record))
        for projection in record.get("projections", []):
            target = root / str(projection["target"])
            if not target.is_dir():
                raise SkillSourceUpdateError(f"projection is missing after sync: {target}")
            projections.append(
                {
                    "repo_id": record["id"],
                    "target": str(projection["target"]),
                    "sha256": tree_digest(target),
                }
            )
    github = []
    for item in gh_skill_list(root / "_system/agents/skills/github"):
        path = Path(str(item["path"]))
        validate_portable_skill(path)
        github.append(
            {
                "id": item["skillName"],
                "source_url": item["sourceURL"],
                "version": item["version"],
                "tree_sha": metadata_value(path, "github-tree-sha"),
                "sha256": tree_digest(path),
            }
        )
    distributed = {str(machine["id"]): read_snapshot_state(machine, source_id) for machine in machines}
    unique_snapshots = {item["snapshot_sha256"] for item in distributed.values()}
    unique_counts = {item["skill_count"] for item in distributed.values()}
    if len(unique_snapshots) != 1 or len(unique_counts) != 1:
        raise SkillSourceUpdateError("distributed fleet skill snapshot evidence does not align")
    return {
        "schema_version": 1,
        "verified_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "external_repos": sorted(external, key=lambda item: str(item["id"])),
        "github_skills": sorted(github, key=lambda item: str(item["id"])),
        "projections": sorted(projections, key=lambda item: (str(item["repo_id"]), str(item["target"]))),
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
