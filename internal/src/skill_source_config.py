#!/usr/bin/env python3
"""Validate the compact skill-source registry."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = 4
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$"
)


class SkillSourceConfigError(ValueError):
    pass


def safe_source(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SkillSourceConfigError(f"{label} needs a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() in {"", "."} or ".." in path.parts:
        raise SkillSourceConfigError(f"{label} has an unsafe path: {value!r}")
    return path.as_posix()


def safe_checkout(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("~/"):
        raise SkillSourceConfigError(f"{label} must start with literal '~/': {value!r}")
    if "$" in value or "\\" in value:
        raise SkillSourceConfigError(f"{label} contains an unsupported path expression: {value!r}")
    relative = PurePosixPath(value[2:])
    if relative.as_posix() in {"", "."} or ".." in relative.parts:
        raise SkillSourceConfigError(f"{label} has an unsafe path: {value!r}")
    return "~/" + relative.as_posix()


def source_id(path: str) -> str:
    value = PurePosixPath(path[2:]).name.replace("_", "-").lower()
    if not ID_RE.fullmatch(value):
        raise SkillSourceConfigError(f"cannot derive a source id from repository path: {path!r}")
    return value


def _prefix(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise SkillSourceConfigError(f"{label} must be a lowercase kebab token")
    return value


def _invocation(value: object, *, label: str) -> dict[str, bool]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SkillSourceConfigError(f"{label} must be an object")
    result: dict[str, bool] = {}
    for raw_name, allowed in value.items():
        name = safe_source(raw_name, label=f"{label} key")
        if not isinstance(allowed, bool):
            raise SkillSourceConfigError(f"{label}.{name} must be true or false")
        result[name] = allowed
    return result


def github_policies(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SkillSourceConfigError(f"skill source config needs schema_version {SCHEMA_VERSION}")
    raw = data.get("gh_skills", {})
    if not isinstance(raw, dict):
        raise SkillSourceConfigError("gh_skills must be an object")
    result: dict[str, dict[str, Any]] = {}
    for repo_id, item in raw.items():
        if not isinstance(repo_id, str) or not ID_RE.fullmatch(repo_id):
            raise SkillSourceConfigError(f"invalid GH skill directory: {repo_id!r}")
        if not isinstance(item, dict):
            raise SkillSourceConfigError(f"gh_skills.{repo_id} must be an object")
        unknown = set(item) - {"prefix", "invocation"}
        if unknown:
            raise SkillSourceConfigError(
                f"gh_skills.{repo_id} has unsupported fields: {sorted(unknown)}"
            )
        policy: dict[str, Any] = {
            "invocation": _invocation(
                item.get("invocation"), label=f"gh_skills.{repo_id}.invocation"
            )
        }
        if "prefix" in item:
            policy["prefix"] = _prefix(
                item["prefix"], label=f"gh_skills.{repo_id}.prefix"
            )
        result[repo_id] = policy
    return result


def derive_repo_records(
    data: dict[str, Any], *, home: str | Path | None = None
) -> list[dict[str, Any]]:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SkillSourceConfigError(f"skill source config needs schema_version {SCHEMA_VERSION}")
    raw_repos = data.get("repos")
    if not isinstance(raw_repos, list):
        raise SkillSourceConfigError("skill source config needs a repos list")
    resolved_home = Path(home or Path.home()).expanduser().resolve()
    if not resolved_home.is_absolute():
        raise SkillSourceConfigError("repository skill home must resolve to an absolute path")

    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, raw in enumerate(raw_repos):
        label = f"repos[{index}]"
        if not isinstance(raw, dict):
            raise SkillSourceConfigError(f"{label} must be an object")
        unknown = set(raw) - {
            "path", "github", "skills", "all_skills", "prefix", "invocation"
        }
        if unknown:
            raise SkillSourceConfigError(f"{label} has unsupported fields: {sorted(unknown)}")
        declared_path = safe_checkout(raw.get("path"), label=f"{label}.path")
        repo_id = source_id(declared_path)
        if repo_id in seen_ids:
            raise SkillSourceConfigError(f"duplicate repository skill source id: {repo_id}")
        if declared_path in seen_paths:
            raise SkillSourceConfigError(f"duplicate repository skill path: {declared_path}")
        seen_ids.add(repo_id)
        seen_paths.add(declared_path)

        has_skills = "skills" in raw
        has_all = raw.get("all_skills") is True
        if has_skills == has_all:
            raise SkillSourceConfigError(
                f"{label} needs exactly one of skills or all_skills: true"
            )
        if "all_skills" in raw and raw.get("all_skills") is not True:
            raise SkillSourceConfigError(f"{label}.all_skills may only be true")
        sources: list[str] | None = None
        if has_skills:
            raw_skills = raw.get("skills")
            if not isinstance(raw_skills, list) or not raw_skills:
                raise SkillSourceConfigError(f"{label}.skills must be a non-empty array")
            sources = []
            for skill_index, item in enumerate(raw_skills):
                if not isinstance(item, dict) or set(item) != {"source"}:
                    raise SkillSourceConfigError(
                        f"{label}.skills[{skill_index}] must contain only source"
                    )
                source = safe_source(
                    item.get("source"), label=f"{label}.skills[{skill_index}].source"
                )
                if source in sources:
                    raise SkillSourceConfigError(f"{label} selects duplicate skill {source!r}")
                sources.append(source)

        github = raw.get("github")
        if github is not None and (
            not isinstance(github, str) or not GITHUB_URL_RE.fullmatch(github)
        ):
            raise SkillSourceConfigError(
                f"{label}.github must be an https://github.com/owner/repo URL"
            )
        invocation = _invocation(raw.get("invocation"), label=f"{label}.invocation")
        if sources is not None and not set(invocation) <= set(sources):
            unknown_invocation = sorted(set(invocation) - set(sources))
            raise SkillSourceConfigError(
                f"{label}.invocation references unselected sources: {unknown_invocation}"
            )
        record: dict[str, Any] = {
            "id": repo_id,
            "declared_path": declared_path,
            "path": str(resolved_home.joinpath(*PurePosixPath(declared_path[2:]).parts)),
            "github": github,
            "all_skills": has_all,
            "skills": sources,
            "invocation": invocation,
        }
        if "prefix" in raw:
            record["prefix"] = _prefix(raw["prefix"], label=f"{label}.prefix")
        result.append(record)
    return result


def validate_config(data: dict[str, Any]) -> None:
    unknown = set(data) - {"schema_version", "gh_skills", "repos"}
    if unknown:
        raise SkillSourceConfigError(
            f"skill source config has unsupported fields: {sorted(unknown)}"
        )
    github_policies(data)
    derive_repo_records(data, home="/__ctx9_home__")
