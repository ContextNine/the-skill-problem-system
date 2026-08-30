#!/usr/bin/env python3
"""Validate compact skill-source choices and derive runtime projection records."""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "agents/_package/src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from package_layout import load_instance


ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GROUP_RE = re.compile(r"^_[a-z0-9]+(?:-[a-z0-9]+)*$")
GITHUB_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MODES = {"auto", "manual"}
KINDS = {"skill", "skill-pack"}


class SkillSourceConfigError(ValueError):
    pass


def _safe_relative(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SkillSourceConfigError(f"{label} needs a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise SkillSourceConfigError(f"{label} has an unsafe path: {value!r}")
    return path.as_posix()


def github_skill_modes(data: dict[str, Any]) -> dict[str, str]:
    """Return explicit invocation-mode overrides for GitHub-managed skills."""
    if data.get("schema_version") != 3:
        raise SkillSourceConfigError("skill source config needs schema_version 3")
    raw = data.get("github_skills", {})
    if not isinstance(raw, dict):
        raise SkillSourceConfigError("github_skills must be an object")
    modes: dict[str, str] = {}
    for name, mode in raw.items():
        if not isinstance(name, str) or not ID_RE.fullmatch(name):
            raise SkillSourceConfigError(f"invalid GitHub-managed skill name: {name!r}")
        if mode not in MODES:
            raise SkillSourceConfigError(
                f"GitHub-managed skill {name!r} has invalid mode {mode!r}"
            )
        modes[name] = mode
    return modes


def _projection(repo_id: str, raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SkillSourceConfigError(f"repository {repo_id!r} has a non-object skill choice")
    unknown = set(raw) - {
        "source", "mode", "kind", "group", "name", "title", "prefix", "rewrite_sources"
    }
    if unknown:
        raise SkillSourceConfigError(f"repository {repo_id!r} skill has unsupported fields: {sorted(unknown)}")
    source = _safe_relative(raw.get("source"), label=f"repository {repo_id!r} skill")
    mode = raw.get("mode", "manual")
    kind = raw.get("kind", "skill")
    group = raw.get("group")
    name = raw.get("name")
    if mode not in MODES:
        raise SkillSourceConfigError(f"repository {repo_id!r} skill {source!r} has invalid mode {mode!r}")
    if kind not in KINDS:
        raise SkillSourceConfigError(f"repository {repo_id!r} skill {source!r} has invalid kind {kind!r}")
    if not isinstance(group, str) or not GROUP_RE.fullmatch(group):
        raise SkillSourceConfigError(f"repository {repo_id!r} skill {source!r} has invalid group {group!r}")
    if not isinstance(name, str) or not (
        ID_RE.fullmatch(name) if kind == "skill" else GROUP_RE.fullmatch(name)
    ):
        raise SkillSourceConfigError(f"repository {repo_id!r} skill {source!r} has invalid name {name!r}")
    if kind == "skill-pack" and mode != "manual":
        raise SkillSourceConfigError("skill packs must use manual invocation mode")
    projection_type = f"{mode}-skill" if kind == "skill" else "manual-skill-pack"
    target = f"_system/agents/skills/{mode}/{group}/{name}"
    projection: dict[str, Any] = {
        "source": source,
        "target": target,
        "type": projection_type,
        "managed": True,
    }
    optional = {
        "title": "title_override",
        "prefix": "skill_prefix",
        "rewrite_sources": "rewrite_skill_sources",
    }
    for source_key, target_key in optional.items():
        if source_key in raw:
            projection[target_key] = raw[source_key]
    if "rewrite_skill_sources" in projection:
        rewrite_sources = projection["rewrite_skill_sources"]
        if not isinstance(rewrite_sources, list):
            raise SkillSourceConfigError(f"repository {repo_id!r} skill pack needs rewrite_sources list")
        projection["rewrite_skill_sources"] = [
            _safe_relative(item, label=f"repository {repo_id!r} rewrite source")
            for item in rewrite_sources
        ]
    return projection


def derive_repo_records(
    data: dict[str, Any],
    *,
    code_root: str | Path | None = None,
    github_transport: str | None = None,
) -> list[dict[str, Any]]:
    """Return the expanded records consumed by repo sync and projection workers."""
    if data.get("schema_version") != 3:
        raise SkillSourceConfigError("skill source config needs schema_version 3")
    if code_root is None or github_transport is None:
        instance = load_instance()
        primary_id = instance["fleet"]["machines"]
        selected = next(
            machine for machine in primary_id.values() if machine.get("role") == "primary"
        )
        code_root = code_root or selected["resolved_roots"]["code"]
        github_transport = github_transport or str(instance["profile"].get("github_transport") or "")
    clone_root = Path(code_root) / "open_source"
    transport = github_transport
    repos = data.get("repos")
    if not Path(clone_root).is_absolute():
        raise SkillSourceConfigError("resolved Code root must be absolute")
    if transport not in {"ssh", "https"}:
        raise SkillSourceConfigError("github_transport must be ssh or https")
    if not isinstance(repos, list):
        raise SkillSourceConfigError("skill source config needs a repos list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in repos:
        if not isinstance(raw, dict):
            raise SkillSourceConfigError("every skill source repository must be an object")
        unknown = set(raw) - {"id", "github", "checkout", "ref", "enabled", "skills"}
        if unknown:
            raise SkillSourceConfigError(f"skill source repository has unsupported fields: {sorted(unknown)}")
        repo_id = raw.get("id")
        github = raw.get("github")
        checkout = raw.get("checkout", repo_id)
        if not isinstance(repo_id, str) or not ID_RE.fullmatch(repo_id):
            raise SkillSourceConfigError(f"invalid skill source repository id: {repo_id!r}")
        if repo_id in seen:
            raise SkillSourceConfigError(f"duplicate skill source repository id: {repo_id}")
        seen.add(repo_id)
        if not isinstance(github, str) or not GITHUB_RE.fullmatch(github):
            raise SkillSourceConfigError(f"repository {repo_id!r} needs owner/repo github identity")
        if not isinstance(checkout, str) or not ID_RE.fullmatch(checkout):
            raise SkillSourceConfigError(f"repository {repo_id!r} has invalid checkout directory")
        raw_skills = raw.get("skills", [])
        if not isinstance(raw_skills, list):
            raise SkillSourceConfigError(f"repository {repo_id!r} needs a skills list")
        url = (
            f"git@github.com:{github}.git"
            if transport == "ssh"
            else f"https://github.com/{github}.git"
        )
        result.append(
            {
                "id": repo_id,
                "url": url,
                "path": str(clone_root / checkout),
                "ref": str(raw.get("ref") or "main"),
                "sync_enabled": bool(raw.get("enabled", True)),
                "projections": [_projection(repo_id, item) for item in raw_skills],
            }
        )
    return result


def validate_config(data: dict[str, Any]) -> None:
    # Validation is intentionally location-independent. Runtime expansion supplies
    # the selected machine's Code root and profile transport separately.
    derive_repo_records(data, code_root="/__ctx9_code__", github_transport="https")
    workspace = data.get("repository_skills", {})
    if not isinstance(workspace, dict):
        raise SkillSourceConfigError("repository_skills must be an object")
    github_skill_modes(data)
    unknown = set(data) - {"schema_version", "repos", "repository_skills", "github_skills"}
    if unknown:
        raise SkillSourceConfigError(f"skill source config has unsupported fields: {sorted(unknown)}")
