#!/usr/bin/env python3
"""Plan linked, overlaid, and snapshotted non-Vault skill sources."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from skill_source_config import (
    SkillSourceConfigError,
    derive_repo_records,
    github_policies,
    validate_config,
)


SELECTION = Path("_system/agents/_package/instance/skills/skill-sources.json")
GH_ROOT = Path("_system/agents/skills/github")
OVERLAY_ROOT = Path("_system/agents/skills/overlays")
SNAPSHOT_ROOT = Path("_system/agents/skills/snapshots")
MARKER = ".ctx9-skill-materialization.json"
MANAGED_BY = "ctx9-agents sync"
SKILL_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_RE = re.compile(r"(?m)^name:\s*['\"]?([^'\"\n]+)['\"]?\s*$")
POLICY_RE = re.compile(
    r"(?m)^(\s*allow_implicit_invocation:\s*)(?:true|false)(\s*(?:#.*)?)$"
)
TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".toml"}
IGNORED_NAMES = {".DS_Store", "__pycache__", MARKER}


class ProjectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectedSkill:
    name: str
    path: Path
    mode: str
    origin: str
    canonical_path: Path
    declared_path: str | None
    materialization: str


@dataclass(frozen=True)
class ProjectionAction:
    kind: str
    target: Path
    canonical_path: Path | None = None
    name: str | None = None
    allowed: bool = False
    mappings: tuple[tuple[str, str], ...] = ()
    marker: str | None = None


@dataclass(frozen=True)
class ProjectionPlan:
    skills: tuple[ProjectedSkill, ...]
    actions: tuple[ProjectionAction, ...]
    warnings: tuple[str, ...] = ()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectionError(f"Skill source registry missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectionError(f"Skill source registry is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectionError(f"Skill source registry must contain an object: {path}")
    return value


def read_source_name(skill: Path) -> str:
    skill_file = skill / "SKILL.md"
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectionError(f"Skill source lacks readable SKILL.md: {skill}") from exc
    if not text.startswith("---\n"):
        raise ProjectionError(f"Skill frontmatter missing: {skill_file}")
    end = text.find("\n---", 4)
    if end == -1:
        raise ProjectionError(f"Skill frontmatter malformed: {skill_file}")
    match = NAME_RE.search(text[4:end])
    if not match:
        raise ProjectionError(f"Skill frontmatter name missing: {skill_file}")
    name = match.group(1).strip()
    if not SKILL_RE.fullmatch(name) or len(name) > 64:
        raise ProjectionError(f"Invalid skill name {name!r}: {skill_file}")
    if skill.name != name:
        raise ProjectionError(f"Skill folder/name mismatch: {skill} declares {name!r}")
    return name


def read_policy(skill: Path) -> bool | None:
    metadata = skill / "agents/openai.yaml"
    if not metadata.is_file():
        return None
    match = POLICY_RE.search(metadata.read_text(encoding="utf-8"))
    if not match:
        return None
    return "true" in match.group(0).lower()


def policy_text(path: Path, allowed: bool) -> str:
    value = "true" if allowed else "false"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if POLICY_RE.search(text):
        return POLICY_RE.sub(rf"\g<1>{value}\g<2>", text, count=1)
    policy = re.search(r"(?m)^policy:\s*(?:#.*)?$", text)
    if policy:
        insert = policy.end()
        return text[:insert] + f"\n  allow_implicit_invocation: {value}" + text[insert:]
    suffix = "" if not text or text.endswith("\n") else "\n"
    return text + suffix + f"policy:\n  allow_implicit_invocation: {value}\n"


def effective_name(name: str, prefix: str | None) -> str:
    result = f"{prefix}-{name}" if prefix else name
    if not SKILL_RE.fullmatch(result) or len(result) > 64:
        raise ProjectionError(f"Effective skill name is invalid or over 64 characters: {result}")
    return result


def skill_digest(source: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
        relative = path.relative_to(source)
        if any(part in IGNORED_NAMES for part in relative.parts) or path.is_dir():
            continue
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"L\0" + os.readlink(path).encode())
        elif path.is_file():
            digest.update(b"F\0" + path.read_bytes())
        else:
            raise ProjectionError(f"Unsupported skill source entry: {path}")
        digest.update(b"\0")
    return digest.hexdigest()


def marker_text(
    *,
    source_id: str,
    source: Path,
    name: str,
    allowed: bool,
    materialization: str,
    digest: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "managed_by": MANAGED_BY,
        "source_id": source_id,
        "source": str(source),
        "name": name,
        "allow_implicit_invocation": allowed,
        "materialization": materialization,
    }
    if digest is not None:
        payload["source_sha256"] = digest
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def discover_all(repo_path: Path) -> list[tuple[str, Path]]:
    roots = [candidate for candidate in (repo_path / ".agents/skills", repo_path / "skills") if candidate.is_dir()]
    if len(roots) != 1:
        found = ", ".join(str(path) for path in roots) or "none"
        raise ProjectionError(
            f"all_skills requires exactly one .agents/skills or skills root in {repo_path}; found {found}"
        )
    selected: list[tuple[str, Path]] = []
    for skill_file in sorted(roots[0].rglob("SKILL.md")):
        skill = skill_file.parent
        if skill.is_symlink() or any(parent.is_symlink() for parent in skill.parents if parent != repo_path.parent):
            raise ProjectionError(f"Repository skill source may not traverse symlinks: {skill}")
        relative = skill.relative_to(repo_path).as_posix()
        selected.append((relative, skill))
    if not selected:
        raise ProjectionError(f"all_skills found no skills in {roots[0]}")
    return selected


def explicit_skills(repo_path: Path, sources: list[str]) -> list[tuple[str, Path]]:
    selected: list[tuple[str, Path]] = []
    resolved_repo = repo_path.resolve()
    for source in sources:
        skill = repo_path.joinpath(*PurePosixPath(source).parts)
        try:
            skill.resolve().relative_to(resolved_repo)
        except ValueError as exc:
            raise ProjectionError(f"Repository skill escapes its checkout: {source}") from exc
        selected.append((source, skill))
    return selected


def gh_sources(root: Path, data: dict[str, Any]) -> list[dict[str, Any]]:
    gh_root = root / GH_ROOT
    if not gh_root.is_dir():
        raise ProjectionError(f"GitHub skill root missing: {gh_root}")
    policies = github_policies(data)
    directories = {
        child.name: child for child in gh_root.iterdir() if child.is_dir() and not child.is_symlink()
    }
    unknown = set(policies) - set(directories)
    if unknown:
        raise ProjectionError(f"GH policy references missing repository directories: {sorted(unknown)}")
    result: list[dict[str, Any]] = []
    for source_id, repo_root in sorted(directories.items()):
        skills_root = repo_root / "skills"
        if not skills_root.is_dir():
            raise ProjectionError(f"GitHub repository directory needs skills/: {repo_root}")
        policy = policies.get(source_id, {"invocation": {}})
        installed: list[tuple[str, Path]] = []
        for child in sorted(skills_root.iterdir()):
            if child.name in {".DS_Store"}:
                continue
            if child.is_symlink() or not child.is_dir() or not (child / "SKILL.md").is_file():
                raise ProjectionError(f"Malformed GH skill entry: {child}")
            source_text = (child / "SKILL.md").read_text(encoding="utf-8")
            missing_metadata = [
                key
                for key in ("github-repo", "github-path", "github-ref", "github-tree-sha")
                if not re.search(rf"(?m)^\s*{key}:\s*\S+\s*$", source_text)
            ]
            if missing_metadata:
                raise ProjectionError(
                    f"GH skill lacks install metadata {missing_metadata}: {child}"
                )
            installed.append((child.name, child))
        if not installed:
            raise ProjectionError(f"GitHub repository has no installed skills: {repo_root}")
        invocation = policy.get("invocation", {})
        unknown_invocation = set(invocation) - {name for name, _ in installed}
        if unknown_invocation:
            raise ProjectionError(
                f"GH invocation policy references missing skills in {source_id}: {sorted(unknown_invocation)}"
            )
        result.append(
            {
                "id": source_id,
                "origin": "gh",
                "selected": installed,
                "prefix": policy.get("prefix"),
                "invocation": invocation,
                "declared_root": None,
            }
        )
    return result


def repo_sources(data: dict[str, Any], home: Path, require_sources: bool) -> tuple[list[dict[str, Any]], list[str]]:
    sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    for record in derive_repo_records(data, home=home):
        repo_path = Path(record["path"])
        if not repo_path.is_dir():
            message = f"Repository skill checkout unavailable: {record['declared_path']}"
            if require_sources:
                raise ProjectionError(message)
            warnings.append(message)
            continue
        selected = (
            discover_all(repo_path)
            if record["all_skills"]
            else explicit_skills(repo_path, record["skills"] or [])
        )
        invocation = record["invocation"]
        unknown_invocation = set(invocation) - {name for name, _ in selected}
        if unknown_invocation:
            raise ProjectionError(
                f"Repository invocation policy references missing selected skills in {record['id']}: {sorted(unknown_invocation)}"
            )
        sources.append(
            {
                "id": record["id"],
                "origin": "repo",
                "selected": selected,
                "prefix": record.get("prefix"),
                "invocation": invocation,
                "declared_root": record["declared_path"],
            }
        )
    return sources, warnings


def plan(root: Path, *, home: Path | None = None, require_sources: bool = False) -> ProjectionPlan:
    data = read_json(root / SELECTION)
    try:
        validate_config(data)
    except SkillSourceConfigError as exc:
        raise ProjectionError(str(exc)) from exc
    selected_home = (home or Path.home()).expanduser().resolve()
    repo, warnings = repo_sources(data, selected_home, require_sources)
    sources = [*gh_sources(root, data), *repo]
    skills: list[ProjectedSkill] = []
    actions: list[ProjectionAction] = []
    desired_generated: set[Path] = set()

    for source in sources:
        mappings: dict[str, str] = {}
        canonical_by_relative: dict[str, tuple[str, Path]] = {}
        for relative, canonical in source["selected"]:
            declared = read_source_name(canonical)
            effective = effective_name(declared, source.get("prefix"))
            mappings[declared] = effective
            canonical_by_relative[relative] = (effective, canonical)
        for relative, (name, canonical) in canonical_by_relative.items():
            allowed = bool(source["invocation"].get(relative, source["invocation"].get(canonical.name, False)))
            declared_path = None
            if source["origin"] == "repo":
                declared_path = f"{source['declared_root']}/{relative}"
            if source.get("prefix"):
                materialization = "snapshot"
                target = root / SNAPSHOT_ROOT / source["id"] / name
                marker = marker_text(
                    source_id=source["id"],
                    source=canonical,
                    name=name,
                    allowed=allowed,
                    materialization=materialization,
                    digest=skill_digest(canonical),
                )
                action_kind = "snapshot"
            elif read_policy(canonical) == allowed:
                materialization = "direct"
                target = canonical
                marker = None
                action_kind = None
            else:
                materialization = "overlay"
                target = root / OVERLAY_ROOT / source["id"] / name
                marker = marker_text(
                    source_id=source["id"],
                    source=canonical,
                    name=name,
                    allowed=allowed,
                    materialization=materialization,
                )
                action_kind = "overlay"
            if action_kind:
                desired_generated.add(target)
                current_marker = target / MARKER
                if (target.exists() or target.is_symlink()) and not current_marker.is_file():
                    raise ProjectionError(f"Generated skill target collides with unmanaged content: {target}")
                current = (
                    overlay_is_current(target, canonical, marker)
                    if action_kind == "overlay"
                    else target.is_dir()
                    and current_marker.is_file()
                    and current_marker.read_text(encoding="utf-8") == marker
                )
                if not current:
                    actions.append(
                        ProjectionAction(
                            action_kind,
                            target,
                            canonical,
                            name,
                            allowed,
                            tuple(sorted(mappings.items())),
                            marker,
                        )
                    )
            skills.append(
                ProjectedSkill(
                    name,
                    target,
                    "auto" if allowed else "manual",
                    source["origin"],
                    canonical,
                    declared_path,
                    materialization,
                )
            )

    for generated_root in (root / OVERLAY_ROOT, root / SNAPSHOT_ROOT):
        if not generated_root.exists():
            continue
        for marker_path in sorted(generated_root.rglob(MARKER)):
            target = marker_path.parent
            if target not in desired_generated:
                actions.append(ProjectionAction("remove", target))
        for child in generated_root.iterdir():
            if child.is_symlink() or not child.is_dir():
                raise ProjectionError(f"Unexpected generated skill entry: {child}")

    names: dict[str, ProjectedSkill] = {}
    for skill in skills:
        previous = names.get(skill.name)
        if previous:
            raise ProjectionError(
                f"Duplicate external skill name {skill.name!r}: {previous.canonical_path} and {skill.canonical_path}"
            )
        names[skill.name] = skill
    return ProjectionPlan(tuple(skills), tuple(actions), tuple(warnings))


def overlay_is_current(target: Path, source: Path, marker: str) -> bool:
    marker_path = target / MARKER
    if not target.is_dir() or not marker_path.is_file() or marker_path.read_text(encoding="utf-8") != marker:
        return False
    expected = {child.name for child in source.iterdir() if child.name not in IGNORED_NAMES}
    expected.add("agents")
    actual = {child.name for child in target.iterdir() if child.name != MARKER}
    if expected != actual:
        return False
    for child in source.iterdir():
        if child.name in IGNORED_NAMES or child.name == "agents":
            continue
        linked = target / child.name
        if not linked.is_symlink() or linked.resolve(strict=False) != child.resolve(strict=False):
            return False
    return (target / "agents/openai.yaml").is_file()


def materialize_overlay(action: ProjectionAction, target: Path) -> None:
    source = action.canonical_path
    if source is None:
        raise ProjectionError("Overlay action has no source")
    target.mkdir(parents=True)
    for child in source.iterdir():
        if child.name in IGNORED_NAMES:
            continue
        if child.name != "agents":
            (target / child.name).symlink_to(child.resolve(), target_is_directory=child.is_dir())
            continue
        agents = target / "agents"
        agents.mkdir()
        for metadata in child.iterdir():
            if metadata.name == "openai.yaml":
                continue
            (agents / metadata.name).symlink_to(metadata.resolve(), target_is_directory=metadata.is_dir())
    metadata = target / "agents/openai.yaml"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(policy_text(source / "agents/openai.yaml", action.allowed), encoding="utf-8")
    (target / MARKER).write_text(action.marker or "", encoding="utf-8")


def rewrite_snapshot(target: Path, action: ProjectionAction) -> None:
    skill_file = target / "SKILL.md"
    text = skill_file.read_text(encoding="utf-8")
    text, count = NAME_RE.subn(f"name: {action.name}", text, count=1)
    if count != 1:
        raise ProjectionError(f"Could not rewrite snapshot name: {skill_file}")
    original_name = next(
        (old for old, new in action.mappings if new == action.name),
        None,
    )
    prefix = (
        (action.name or "")[: -(len(original_name) + 1)]
        if original_name and action.name and action.name.endswith(f"-{original_name}")
        else ""
    )
    if prefix:
        title = " ".join(part.upper() if len(part) <= 3 else part.title() for part in prefix.split("-"))
        text = re.sub(r"(?m)^# (.+)$", rf"# {title} · \1", text, count=1)
    skill_file.write_text(text, encoding="utf-8")
    mapping = dict(action.mappings)
    for path in target.rglob("*"):
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        original = path.read_text(encoding="utf-8")
        updated = original
        for old, new in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
            updated = re.sub(rf"\${re.escape(old)}\b", f"${new}", updated)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
    metadata = target / "agents/openai.yaml"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(policy_text(metadata, action.allowed), encoding="utf-8")
    (target / MARKER).write_text(action.marker or "", encoding="utf-8")


def materialize_action(action: ProjectionAction, target: Path | None = None) -> Path:
    destination = target or action.target
    if action.kind == "overlay":
        materialize_overlay(action, destination)
    elif action.kind == "snapshot":
        if action.canonical_path is None:
            raise ProjectionError("Snapshot action has no source")
        shutil.copytree(action.canonical_path, destination, symlinks=False)
        rewrite_snapshot(destination, action)
    else:
        raise ProjectionError(f"Cannot materialize action: {action.kind}")
    return destination


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def replace_generated(action: ProjectionAction) -> None:
    action.target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{action.target.name}.incoming-", dir=action.target.parent))
    temporary = staging / "skill"
    try:
        materialize_action(action, temporary)
        previous = action.target.parent / f".{action.target.name}.previous-{os.getpid()}"
        remove_path(previous)
        if action.target.exists() or action.target.is_symlink():
            os.replace(action.target, previous)
        os.replace(temporary, action.target)
        remove_path(previous)
    finally:
        remove_path(staging)


def apply(plan: ProjectionPlan, root: Path) -> None:
    del root
    for action in plan.actions:
        if action.kind == "remove":
            marker = action.target / MARKER
            if not marker.is_file():
                raise ProjectionError(f"Refusing to remove unmanaged generated skill: {action.target}")
            remove_path(action.target)
        else:
            replace_generated(action)
