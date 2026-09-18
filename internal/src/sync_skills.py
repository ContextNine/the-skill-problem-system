#!/usr/bin/env python3
"""Validate skill sources and rebuild Vault/global discovery links."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

COMMANDS_DIR = Path(__file__).resolve().parents[3] / "commands"
if str(COMMANDS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMANDS_DIR))

import global_agent_configuration
import working_repo_skills
from package_layout import resolve_agents_root


GROUP_RE = re.compile(r"^_[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_RE = re.compile(r"(?m)^name:\s*['\"]?([^'\"\n]+)['\"]?\s*$")
POLICY_RE = re.compile(
    r"(?m)^\s*allow_implicit_invocation:\s*(true|false)\s*(?:#.*)?$"
)
IGNORED = {".DS_Store", ".gitkeep", "README.md"}
RESERVED_ROOTS = {"catalog", "dormant", "github", "overlays", "public", "snapshots"}
CATEGORY_TOKENS = {
    "_agents": ("agents", "Agents"),
    "_blogs": ("blog", "Blogs"),
    "_code": ("code", "Code"),
    "_creative": ("creative", "Creative"),
    "_documents": ("documents", "Documents"),
    "_finance": ("finance", "Finance"),
    "_gws": ("gws", "GWS"),
    "_fleet": ("fleet", "Fleet"),
    "_marketing": ("marketing", "Marketing"),
    "_spreadsheets": ("spreadsheets", "Spreadsheets"),
    "_vault": ("vault", "Vault"),
    "_video": ("video", "Video"),
}


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    path: Path
    source: str
    mode: str
    canonical_path: Path
    declared_path: str | None = None
    materialization: str = "direct"


@dataclass(frozen=True)
class Change:
    description: str
    action: str
    path: Path
    value: str | None = None


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def read_skill_name(skill_file: Path) -> str:
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SyncError(f"Skill frontmatter missing: {skill_file}")
    end = text.find("\n---", 4)
    if end == -1:
        raise SyncError(f"Skill frontmatter malformed: {skill_file}")
    match = NAME_RE.search(text[4:end])
    if not match:
        raise SyncError(f"Skill frontmatter name missing: {skill_file}")
    return match.group(1).strip()


def read_first_h1(skill_file: Path) -> str | None:
    text = skill_file.read_text(encoding="utf-8")
    in_fence = False
    fence = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence = marker
            elif marker == fence:
                in_fence = False
            continue
        if not in_fence and line.startswith("# "):
            return line
    return None


def read_policy(skill: Path) -> bool:
    metadata = skill / "agents/openai.yaml"
    if not metadata.is_file():
        raise SyncError(f"Vault-owned skill needs agents/openai.yaml: {skill}")
    match = POLICY_RE.search(metadata.read_text(encoding="utf-8"))
    if not match:
        raise SyncError(f"Vault-owned skill needs explicit invocation policy: {metadata}")
    return match.group(1) == "true"


def category_token(category: str) -> tuple[str, str] | None:
    if category in CATEGORY_TOKENS:
        return CATEGORY_TOKENS[category]
    if category.startswith("_") and category.endswith("-skills-pack"):
        token = category[1 : -len("-skills-pack")]
        if SKILL_RE.fullmatch(token):
            return token, token.replace("-", " ").title()
    return None


def validate_vault_skill(skill_file: Path, name: str, category: str) -> str:
    category_details = category_token(category)
    if category_details is None:
        allowed = ", ".join(CATEGORY_TOKENS)
        raise SyncError(
            f"Unknown skill category {category!r}; expected one of {allowed} or _<token>-skills-pack"
        )
    token, title = category_details
    implicit = name == f"{token}-i" or name.startswith(f"{token}-i-")
    manual = name.startswith(f"{token}-") and not implicit
    if not (implicit or manual):
        raise SyncError(
            f"Skill name must use category prefix {token!r}: {skill_file.parent} declares {name!r}"
        )
    allowed = read_policy(skill_file.parent)
    if allowed != implicit:
        raise SyncError(
            f"Vault skill -i- marker and invocation policy disagree: {skill_file.parent}"
        )
    h1 = read_first_h1(skill_file)
    if name == "vault-i":
        if h1 != "# Vault":
            raise SyncError(f"Root Vault skill H1 must be '# Vault': {skill_file}")
    else:
        expected = f"# {title} · "
        if h1 is None or not h1.startswith(expected) or not h1.removeprefix(expected).strip():
            raise SyncError(f"Skill H1 must start with {expected!r}: {skill_file}")
    return "auto" if implicit else "manual"


def scan_vault_sources(skills_root: Path) -> list[Skill]:
    found: list[Skill] = []
    for group in sorted(skills_root.iterdir(), key=lambda item: item.name):
        if group.name in RESERVED_ROOTS:
            continue
        if group.name in IGNORED:
            continue
        if group.is_symlink() or not group.is_dir() or not GROUP_RE.fullmatch(group.name):
            raise SyncError(f"Unexpected skill source root entry: {group}")
        if category_token(group.name) is None:
            raise SyncError(f"Unknown Vault skill group: {group}")
        pending = [group]
        skill_files: list[Path] = []
        while pending:
            directory = pending.pop()
            skill_file = directory / "SKILL.md"
            if skill_file.is_file():
                skill_files.append(skill_file)
                continue
            pending.extend(
                child for child in directory.iterdir()
                if child.is_dir() and not child.is_symlink()
            )
        for skill_file in sorted(skill_files):
            skill = skill_file.parent
            if skill.is_symlink():
                raise SyncError(f"Vault-owned skill may not be a symlink: {skill}")
            if not SKILL_RE.fullmatch(skill.name):
                raise SyncError(f"Invalid skill folder name: {skill}")
            declared = read_skill_name(skill_file)
            if declared != skill.name:
                raise SyncError(
                    f"Skill folder/name mismatch: {skill} declares {declared!r}"
                )
            mode = validate_vault_skill(skill_file, declared, group.name)
            found.append(Skill(declared, skill, "vault", mode, skill))
    return found


def resolved_target(link: Path) -> Path:
    raw = Path(os.readlink(link))
    return (link.parent / raw).resolve(strict=False) if not raw.is_absolute() else raw.resolve(strict=False)


def owned_global_link(link: Path, catalog: Path) -> bool:
    if not link.is_symlink():
        return False
    raw = Path(os.readlink(link))
    target = raw if raw.is_absolute() else link.parent / raw
    target = Path(os.path.abspath(target))
    normalized_catalog = Path(os.path.abspath(catalog))
    return target == normalized_catalog or is_relative_to(target, normalized_catalog)


def plan_catalog(catalog: Path, skills: list[Skill]) -> list[Change]:
    desired = {skill.name: skill.path for skill in skills}
    changes: list[Change] = []
    if catalog.exists() and not catalog.is_dir():
        raise SyncError(f"Active skill catalog must be directory: {catalog}")
    existing = list(catalog.iterdir()) if catalog.exists() else []
    if not catalog.exists():
        changes.append(Change(f"Create active skill catalog: {catalog}", "mkdir", catalog))
    for entry in sorted(existing, key=lambda item: item.name):
        if entry.name in {".DS_Store", ".gitkeep"}:
            changes.append(Change(f"Remove catalog housekeeping entry: {entry}", "remove", entry))
            continue
        target = desired.get(entry.name)
        if target is None:
            if entry.is_symlink():
                changes.append(Change(f"Remove stale active link: {entry}", "remove", entry))
                continue
            raise SyncError(f"Unexpected real content in generated catalog: {entry}")
        expected = os.path.relpath(target.resolve(strict=False), catalog.resolve(strict=False))
        if not entry.is_symlink():
            raise SyncError(f"Unmanaged catalog collision: {entry}")
        if os.readlink(entry) != expected:
            changes.append(Change(f"Rebuild active link: {entry} -> {expected}", "symlink", entry, expected))
    for name, target in sorted(desired.items()):
        entry = catalog / name
        if not (entry.exists() or entry.is_symlink()):
            changes.append(
                Change(
                    f"Create active link: {entry}",
                    "symlink",
                    entry,
                    os.path.relpath(target.resolve(strict=False), catalog.resolve(strict=False)),
                )
            )
    return changes


def plan_discovery(home: Path, catalog: Path, names: set[str]) -> list[Change]:
    changes: list[Change] = []
    legacy_codex = home / ".codex/skills"
    if legacy_codex.is_symlink() and resolved_target(legacy_codex) == catalog.resolve(strict=False):
        changes.append(Change(f"Remove owned legacy Codex skill link: {legacy_codex}", "remove", legacy_codex))
    targets = [home / ".agents/skills", home / ".claude/skills", home / ".kilo/skills"]
    if (home / ".kilocode").exists():
        targets.append(home / ".kilocode/skills")
    for directory in targets:
        if directory.is_symlink():
            if resolved_target(directory) != catalog.resolve(strict=False):
                raise SyncError(f"Unmanaged discovery directory symlink blocks sync: {directory}")
            changes.append(Change(f"Replace owned whole-directory link with directory: {directory}", "replace-dir", directory))
            entries: list[Path] = []
        elif directory.exists():
            if not directory.is_dir():
                raise SyncError(f"Discovery path is not directory: {directory}")
            entries = list(directory.iterdir())
        else:
            changes.append(Change(f"Create discovery directory: {directory}", "mkdir", directory))
            entries = []
        by_name = {entry.name: entry for entry in entries}
        for entry in entries:
            if owned_global_link(entry, catalog) and entry.name not in names:
                changes.append(Change(f"Remove stale managed discovery link: {entry}", "remove", entry))
        for name in sorted(names):
            entry = by_name.get(name)
            expected = catalog / name
            if entry is None:
                changes.append(Change(f"Create discovery link: {directory / name}", "symlink", directory / name, str(expected)))
            elif entry.is_symlink() and resolved_target(entry) == expected.resolve(strict=False):
                continue
            elif owned_global_link(entry, catalog):
                changes.append(Change(f"Rebuild discovery link: {entry}", "symlink", entry, str(expected)))
            else:
                raise SyncError(f"Unmanaged global skill collision: {entry}")
    return changes


def apply_changes(changes: list[Change]) -> None:
    for change in changes:
        path = change.path
        if change.action == "mkdir":
            path.mkdir(parents=True, exist_ok=True)
        elif change.action == "remove":
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
            elif path.exists():
                shutil.rmtree(path)
        elif change.action == "replace-dir":
            path.unlink()
            path.mkdir(parents=True, exist_ok=True)
        elif change.action == "symlink":
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(change.value or "", target_is_directory=True)
        else:
            raise AssertionError(change.action)


def print_agent_configuration(report: dict[str, object], *, apply: bool) -> None:
    warning = report.get("warning")
    if warning:
        print(f"WARN  {warning}")
    prefix = "APPLY " if apply else "PLAN  "
    for key in ("root", "home"):
        section = report.get(key)
        if isinstance(section, dict):
            for item in section.get("results", []):
                if item["status"] != "match":
                    print(f"{prefix}{item['detail']}: {item['path']}")


def agent_configuration_change_count(report: dict[str, object]) -> int:
    count = 0
    for key in ("root", "home"):
        section = report.get(key)
        if isinstance(section, dict):
            count += sum(item["status"] != "match" for item in section.get("results", []))
    return count


def discover_skills(
    root: Path,
    *,
    home: Path | None = None,
    require_repo_sources: bool = False,
) -> tuple[working_repo_skills.ProjectionPlan, list[Skill]]:
    agents_root = resolve_agents_root(root)
    skills_root = agents_root / "edit/skills"
    projection_plan = working_repo_skills.plan(
        root, home=home, require_sources=require_repo_sources
    )
    skills = scan_vault_sources(skills_root)
    skills.extend(
        Skill(
            item.name,
            item.path,
            item.origin,
            item.mode,
            item.canonical_path,
            item.declared_path,
            item.materialization,
        )
        for item in projection_plan.skills
    )
    names: dict[str, Skill] = {}
    for skill in skills:
        previous = names.get(skill.name)
        if previous:
            raise SyncError(
                f"Duplicate skill name {skill.name!r}: {previous.path} and {skill.path}"
            )
        names[skill.name] = skill
    return projection_plan, skills


def sync(
    root: Path,
    home: Path,
    apply: bool,
    *,
    require_repo_sources: bool = False,
    manage_home_discovery: bool = True,
    manage_agent_configuration: bool = True,
) -> int:
    agents_root = resolve_agents_root(root)
    catalog = agents_root / "internal/generated/catalog"
    projection_plan, skills = discover_skills(
        root, home=home, require_repo_sources=require_repo_sources
    )
    changes = plan_catalog(catalog, skills)
    if manage_home_discovery:
        changes.extend(plan_discovery(home, catalog, {skill.name for skill in skills}))
    backup_suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    agent_preview = (
        global_agent_configuration.sync_local(root, home, apply=False, backup_suffix=backup_suffix)
        if manage_agent_configuration
        else None
    )
    for warning in projection_plan.warnings:
        print(f"WARN  {warning}")
    for action in projection_plan.actions:
        verb = "Remove stale" if action.kind == "remove" else f"Build {action.kind}"
        print(("APPLY " if apply else "PLAN  ") + f"{verb}: {action.target}")
    for change in changes:
        print(("APPLY " if apply else "PLAN  ") + change.description)
    if agent_preview is not None:
        print_agent_configuration(agent_preview, apply=False)
    if apply:
        agent_report = (
            global_agent_configuration.sync_local(root, home, apply=True, backup_suffix=backup_suffix)
            if manage_agent_configuration
            else None
        )
        if agent_report is not None:
            print_agent_configuration(agent_report, apply=True)
        working_repo_skills.apply(projection_plan, root)
        apply_changes(changes)
        total = len(projection_plan.actions) + len(changes)
        if agent_report is not None:
            total += agent_configuration_change_count(agent_report)
        print(f"Synced {len(skills)} skills; {total} changes applied.")
    else:
        total = len(projection_plan.actions) + len(changes)
        if agent_preview is not None:
            total += agent_configuration_change_count(agent_preview)
        print(f"Validated {len(skills)} skills; {total} changes planned.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and sync Vault skill sources.")
    parser.add_argument("command", choices=["sync"])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview changes (default).")
    mode.add_argument("--apply", action="store_true", help="Apply changes.")
    parser.add_argument("--require-repo-sources", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--home", type=Path)
    parser.add_argument("--catalog-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = (args.root or Path(__file__).resolve().parents[4]).resolve()
    home = (args.home or Path.home()).resolve()
    try:
        return sync(
            root,
            home,
            args.apply,
            require_repo_sources=args.require_repo_sources,
            manage_home_discovery=not args.catalog_only,
            manage_agent_configuration=not args.catalog_only,
        )
    except (
        SyncError,
        working_repo_skills.ProjectionError,
        global_agent_configuration.AgentConfigurationError,
        json.JSONDecodeError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Skill sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
