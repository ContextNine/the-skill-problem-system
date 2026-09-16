#!/usr/bin/env python3
"""Build the deterministic public Skill Problem System repository."""

from __future__ import annotations

import hashlib
import fnmatch
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from package_layout import AGENTS_ROOT, EXPORT_ROOT, VAULT_ROOT
import working_repo_skills


MANIFEST_NAME = ".ctx9-agent-export-manifest.json"
NOTICE_NAME = "THIRD_PARTY_NOTICES.md"
INTERNAL_INVENTORY_PATH = AGENTS_ROOT.parent / "local/state/public-skills-export-inventory.json"
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CREDENTIAL_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    (
        "assigned credential",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|secret[_-]?key)\b"
            r"\s*[:=]\s*['\"][A-Za-z0-9_./+=-]{16,}['\"]"
        ),
    ),
)
# Instance identifiers are never part of a portable first-party skill. Keep this
# check separate from credential detection so a new personal example fails export.
PRIVATE_INSTANCE_RE = re.compile(
    r"(?i)\b(?:matthew\s+derman|mattbook|wootbook|workermacair|fridaystudios|impression-group1|outsource-think)\b|taildb6722"
)
FORBIDDEN_PARTS = {
    "private",
    "__pycache__",
    ".git",
    "catalog",
    "dormant",
    "overlays",
    "snapshots",
    working_repo_skills.MARKER,
}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
ICLOUD_DUPLICATE_RE = re.compile(r"^.+ \d+(?:\.[^.]+)?$")
WIKILINK_RE = re.compile(r"\[\[([^\]\n]+)\]\]")
EXCLUSIONS_PATH = AGENTS_ROOT / "edit/settings/public-skill-repo-export-exclusions.json"
LEGACY_PUBLIC_ROOTS = (Path("_system/agents"),)


class ExportError(RuntimeError):
    pass


def read_manifest(path: Path | None = None) -> dict[str, Any]:
    target = path or EXPORT_ROOT / "agent-package-export.json"
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"agent export manifest is invalid: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise ExportError("agent export manifest needs schema_version 2")
    return value


def safe_relative(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ExportError(f"{label} needs a path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ExportError(f"{label} has an unsafe path: {value}")
    return path


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_file(source: Path, target: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise ExportError(f"public source file is missing or is a symlink: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def matches_exclusion(relative: Path, patterns: tuple[str, ...]) -> str | None:
    rendered = relative.as_posix()
    return next((pattern for pattern in patterns if fnmatch.fnmatchcase(rendered, pattern)), None)


def read_exclusions(path: Path = EXCLUSIONS_PATH) -> tuple[str, ...]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"public skill export exclusions are invalid: {exc}") from exc
    raw = value.get("exclude") if isinstance(value, dict) and value.get("schema_version") == 1 else None
    if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
        raise ExportError("public skill export exclusions need schema_version 1 and a string list")
    for pattern in raw:
        candidate = Path(pattern)
        if pattern.startswith("!") or candidate.is_absolute() or ".." in candidate.parts:
            raise ExportError(f"public skill export exclusion is unsafe: {pattern!r}")
    return tuple(raw)


def copy_tree(
    source: Path,
    target: Path,
    *,
    edit_prefix: Path | None = None,
    exclusions: tuple[str, ...] = (),
    exclusion_log: list[dict[str, str]] | None = None,
) -> None:
    if not source.is_dir() or source.is_symlink():
        raise ExportError(f"public source tree is missing or is a symlink: {source}")
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_symlink():
            raise ExportError(f"public source tree contains a symlink: {path}")
        if any(part in FORBIDDEN_PARTS for part in relative.parts) or path.suffix in FORBIDDEN_SUFFIXES:
            continue
        edit_relative = edit_prefix / relative if edit_prefix is not None else None
        rule = matches_exclusion(edit_relative, exclusions) if edit_relative is not None else None
        if rule:
            if exclusion_log is not None and path.is_file():
                exclusion_log.append({"path": edit_relative.as_posix(), "rule": rule})
            continue
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            copy_file(path, destination)


def prune_excluded_tree(
    target: Path,
    edit_prefix: Path,
    exclusions: tuple[str, ...],
    exclusion_log: list[dict[str, str]],
) -> None:
    for path in sorted(target.rglob("*"), reverse=True):
        relative = edit_prefix / path.relative_to(target)
        rule = matches_exclusion(relative, exclusions)
        if rule and path.is_file():
            exclusion_log.append({"path": relative.as_posix(), "rule": rule})
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def frontmatter_name(skill_file: Path) -> str | None:
    lines = skill_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return None


def _markdown_without_fenced_code(text: str) -> str:
    """Return Markdown prose while preserving line positions and omitting fenced code."""
    result: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = next((item for item in ("```", "~~~") if stripped.startswith(item)), None)
        if marker:
            fence = None if fence == marker else marker if fence is None else fence
            result.append("\n" if line.endswith("\n") else "")
        elif fence is None:
            result.append(line)
        else:
            result.append("\n" if line.endswith("\n") else "")
    return "".join(result)


def _owning_skill(path: Path, stage: Path) -> Path | None:
    for parent in (path.parent, *path.parents):
        if parent == stage.parent:
            break
        if (parent / "SKILL.md").is_file():
            return parent
        if parent == stage:
            break
    return None


def _candidate_files(base: Path) -> list[Path]:
    candidates = [base]
    if base.suffix == "":
        candidates.append(base.with_suffix(".md"))
        candidates.append(base / "README.md")
    return candidates


def _resolve_public_wikilink(stage: Path, current: Path, raw_target: str) -> tuple[Path | None, str | None]:
    target, separator, heading = raw_target.partition("#")
    target = target.strip()
    heading = heading.strip() if separator else None
    if not target:
        return current, heading
    if target.startswith("_system/agents/"):
        target = target.removeprefix("_system/agents/")
    target_path = Path(target)
    skill = _owning_skill(current, stage)
    bases: list[Path] = []
    if target.startswith(("edit/", "internal/", "skills/")):
        bases.append(stage / target_path)
    bases.append(current.parent / target_path)
    if skill is not None:
        bases.append(skill / target_path)
    for base in bases:
        for candidate in _candidate_files(base):
            resolved = candidate.resolve(strict=False)
            if (resolved == stage or stage in resolved.parents) and candidate.is_file():
                return candidate, heading
    if "/" not in target:
        search_root = skill or stage
        names = {target, f"{target}.md"}
        matches = [
            item for item in search_root.rglob("*")
            if item.is_file() and item.name in names
        ]
        if len(matches) == 1:
            return matches[0], heading
    return None, heading


def _heading_slug(value: str) -> str:
    lowered = value.casefold().strip()
    lowered = re.sub(r"[^\w\s-]", "", lowered)
    return re.sub(r"[\s-]+", "-", lowered).strip("-")


def _rewrite_prose_wikilinks(stage: Path, current: Path, prose: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        target, divider, label = raw.partition("|")
        target = target.strip()
        display = label.strip() if divider else target.rsplit("/", 1)[-1].lstrip("#")
        resolved, heading = _resolve_public_wikilink(stage, current, target)
        if resolved is None:
            return display
        relative = Path(os.path.relpath(resolved, current.parent)).as_posix()
        destination = quote(relative, safe="/._-")
        if heading:
            destination += f"#{_heading_slug(heading)}"
        return f"[{display}]({destination})"

    return WIKILINK_RE.sub(replace, prose)


def rewrite_public_markdown_links(stage: Path) -> None:
    """Convert Obsidian wikilinks in public prose to portable Markdown or plain labels."""
    stage = stage.resolve()
    for path in sorted(stage.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        rewritten: list[str] = []
        fence: str | None = None
        for line in lines:
            stripped = line.lstrip()
            marker = next((item for item in ("```", "~~~") if stripped.startswith(item)), None)
            if marker:
                fence = None if fence == marker else marker if fence is None else fence
                rewritten.append(line)
            elif fence is None:
                rewritten.append(_rewrite_prose_wikilinks(stage, path, line))
            else:
                rewritten.append(line)
        path.write_text("".join(rewritten), encoding="utf-8")


def validate_retained_skill_exclusions(
    stage: Path,
    exclusions: list[dict[str, str]],
) -> None:
    """Fail when a retained skill still names a file removed by a user exclusion."""
    for item in exclusions:
        relative = Path(item["path"])
        if relative.parts[:1] != ("skills",) or len(relative.parts) < 4:
            continue
        skill_root = stage / "edit" / Path(*relative.parts[:3])
        if not (skill_root / "SKILL.md").is_file():
            continue
        omitted = Path(*relative.parts[3:])
        aliases = {omitted.as_posix()}
        if omitted.suffix == ".md":
            aliases.add(omitted.with_suffix("").as_posix())
        markdown = [
            path.read_text(encoding="utf-8")
            for path in sorted(skill_root.rglob("*.md"))
        ]
        searchable = (
            "\n".join(markdown)
            if omitted.parts[:1] == ("scripts",)
            else "\n".join(_markdown_without_fenced_code(text) for text in markdown)
        )
        if any(alias in searchable for alias in aliases):
            raise ExportError(
                f"public exclusion {item['rule']!r} removed required skill file "
                f"{item['path']!r} referenced by {skill_root.relative_to(stage)}"
            )


def validate_no_public_wikilinks(stage: Path) -> None:
    for path in sorted(stage.rglob("*.md")):
        prose = _markdown_without_fenced_code(path.read_text(encoding="utf-8"))
        if WIKILINK_RE.search(prose):
            raise ExportError(f"public Markdown retains an Obsidian wikilink: {path.relative_to(stage)}")


def github_repo(skill_file: Path) -> str | None:
    match = re.search(r"github-repo:\s*(\S+)", skill_file.read_text(encoding="utf-8"))
    return match.group(1).rstrip("/") if match else None


def strip_install_metadata(skill_file: Path) -> None:
    text = skill_file.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^\s+github-(?:path|ref|repo|tree-sha):.*\n", "", text)
    text = re.sub(r"(?m)^metadata:\n(?=[A-Za-z][A-Za-z0-9_-]*:)", "", text)
    skill_file.write_text(text, encoding="utf-8")


def skill_decision(
    skill_dir: Path,
    manifest: dict[str, Any],
) -> tuple[bool, str, str | None, str | None]:
    skill_file = skill_dir / "SKILL.md"
    texts: list[str] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    text = "\n".join(texts)
    repo = github_repo(skill_file)
    for label, pattern in CREDENTIAL_PATTERNS:
        if pattern.search(text):
            raise ExportError(f"credential-like {label} found in active skill: {skill_file}")
    licenses = {
        key.casefold(): value
        for key, value in manifest.get("third_party_licenses", {}).items()
    }
    declaration = licenses.get(repo.casefold()) if repo else None
    license_id = str(declaration["spdx"]) if isinstance(declaration, dict) and declaration.get("spdx") else None
    return True, "active non-repository skill", repo, license_id


def source_skill_files(root: Path) -> list[Path]:
    """Find top-level skills without descending into a discovered skill bundle."""
    found: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        skill_file = directory / "SKILL.md"
        if skill_file.is_file():
            found.append(skill_file)
            continue
        pending.extend(
            child for child in directory.iterdir()
            if child.is_dir() and not child.is_symlink() and child.name not in FORBIDDEN_PARTS
        )
    return sorted(found)


def discover_skills(
    stage: Path,
    manifest: dict[str, Any],
    exclusions: tuple[str, ...],
    exclusion_log: list[dict[str, str]],
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    names: dict[str, Path] = {}
    skills_root = AGENTS_ROOT / "edit/skills"
    roots = [
        child for child in sorted(skills_root.iterdir())
        if child.is_dir()
        and not child.is_symlink()
        and child.name.startswith("_")
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for skill_file in source_skill_files(root):
            skill_dir = skill_file.parent
            relative = skill_dir.relative_to(skills_root)
            edit_relative = Path("skills") / relative
            rule = matches_exclusion(edit_relative / "SKILL.md", exclusions)
            if rule:
                exclusion_log.append({"path": edit_relative.as_posix(), "rule": rule})
                continue
            if skill_file.is_symlink() or any(path.is_symlink() for path in skill_dir.rglob("*")):
                raise ExportError(f"active skill contains a symlink: {skill_dir}")
            name = frontmatter_name(skill_file)
            if not name or not SKILL_NAME_RE.fullmatch(name) or skill_dir.name != name:
                raise ExportError(f"invalid skill name or directory: {skill_dir} ({name!r})")
            if name in names and relative.parts[0] != "github":
                raise ExportError(f"duplicate active skill name {name}: {names[name]} and {skill_dir}")
            names[name] = skill_dir
            include, reason, source_repo, license_id = skill_decision(skill_dir, manifest)
            item = {
                "name": name,
                "source": f"edit/skills/{relative.as_posix()}",
                "status": "included" if include else "excluded",
                "reason": reason,
            }
            if source_repo:
                item["source_repository"] = source_repo
            if license_id:
                item["license"] = license_id
            inventory.append(item)
            if include:
                target = stage / "edit/skills" / relative
                copy_tree(
                    skill_dir,
                    target,
                    edit_prefix=edit_relative,
                    exclusions=exclusions,
                    exclusion_log=exclusion_log,
                )
                strip_install_metadata(target / "SKILL.md")

    projected = working_repo_skills.plan(VAULT_ROOT, require_sources=False)
    if projected.actions:
        raise ExportError("skill materializations are stale; run fleet sync --skills first")
    for skill in sorted(
        (item for item in projected.skills if item.origin == "gh"),
        key=lambda item: item.name,
    ):
        try:
            canonical_relative = skill.canonical_path.relative_to(skills_root / "github")
        except ValueError as exc:
            raise ExportError(f"GH skill escapes its repository root: {skill.canonical_path}") from exc
        if len(canonical_relative.parts) < 3 or canonical_relative.parts[1] != "skills":
            raise ExportError(f"GH skill has an invalid repository layout: {skill.canonical_path}")
        repository = canonical_relative.parts[0]
        relative = Path("github") / repository / "skills" / skill.name
        edit_relative = Path("skills") / relative
        rule = matches_exclusion(edit_relative / "SKILL.md", exclusions)
        if rule:
            exclusion_log.append({"path": edit_relative.as_posix(), "rule": rule})
            continue
        if skill.name in names:
            raise ExportError(
                f"duplicate active skill name {skill.name}: {names[skill.name]} and {skill.canonical_path}"
            )
        names[skill.name] = skill.canonical_path
        include, reason, source_repo, license_id = skill_decision(skill.canonical_path, manifest)
        item = {
            "name": skill.name,
            "source": f"edit/skills/{relative.as_posix()}",
            "status": "included" if include else "excluded",
            "reason": reason,
        }
        if source_repo:
            item["source_repository"] = source_repo
        if license_id:
            item["license"] = license_id
        inventory.append(item)
        if include:
            target = stage / "edit/skills" / relative
            shutil.copytree(
                skill.path,
                target,
                symlinks=False,
                ignore=lambda _directory, names: {
                    name
                    for name in names
                    if name in {"__pycache__", ".DS_Store", working_repo_skills.MARKER}
                    or name.endswith(".pyc")
                    or ICLOUD_DUPLICATE_RE.fullmatch(name)
                },
            )
            prune_excluded_tree(target, edit_relative, exclusions, exclusion_log)
            metadata = target / "agents/openai.yaml"
            metadata.parent.mkdir(parents=True, exist_ok=True)
            metadata.write_text(
                working_repo_skills.policy_text(metadata, False), encoding="utf-8"
            )
            strip_install_metadata(target / "SKILL.md")
    return inventory


def inventory_payload(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "included": sum(item["status"] == "included" for item in inventory),
        "excluded": sum(item["status"] == "excluded" for item in inventory),
        "omitted_collections": {
            "catalog": "generated symlink-only view",
            "dormant": "intentionally inactive skill sources",
        },
        "skills": inventory,
    }


def validate_exported_templates(stage: Path) -> None:
    for config_path in sorted((stage / "edit/skills").rglob("fleet-templates/render.json")):
        skill_root = config_path.parent.parent
        if not (skill_root / "SKILL.md").is_file():
            raise ExportError(f"fleet template config has no owning skill: {config_path}")
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExportError(f"fleet template config is invalid: {config_path}: {exc}") from exc
        outputs = config.get("outputs") if isinstance(config, dict) else None
        if not isinstance(config, dict) or config.get("schema_version") != 1 or not isinstance(outputs, list) or not outputs:
            raise ExportError(f"fleet template config needs schema_version 1 and outputs: {config_path}")
        for output in outputs:
            if not isinstance(output, dict):
                raise ExportError(f"fleet template output must be an object: {config_path}")
            for field in ("base", "template"):
                raw = output.get(field)
                if raw is None:
                    continue
                source = skill_root / safe_relative(raw, f"fleet template {field}")
                if not source.is_file() or source.is_symlink():
                    raise ExportError(
                        f"public exclusion removed required fleet template {field}: {source}"
                    )
            fragments = output.get("fragments", [])
            if not isinstance(fragments, list):
                raise ExportError(f"fleet template fragments must be a list: {config_path}")
            for fragment in fragments:
                if not isinstance(fragment, dict):
                    raise ExportError(f"fleet template fragment must be an object: {config_path}")
                source = skill_root / safe_relative(
                    fragment.get("path"), "fleet template fragment"
                )
                if not source.is_file() or source.is_symlink():
                    raise ExportError(
                        f"public exclusion removed required fleet template fragment: {source}"
                    )


def write_internal_inventory(
    inventory: list[dict[str, Any]],
    path: Path = INTERNAL_INVENTORY_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(inventory_payload(inventory), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_notices(stage: Path, inventory: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    used = sorted({item.get("source_repository") for item in inventory if item["status"] == "included" and item.get("source_repository")})
    lines = ["# Third-party notices", "", "The following skill sources are redistributed under their original licenses.", ""]
    licenses = {
        key.casefold(): value
        for key, value in manifest.get("third_party_licenses", {}).items()
    }
    for repo in used:
        declaration = licenses.get(str(repo).casefold())
        if isinstance(declaration, dict):
            lines.append(f"- {repo}: {declaration['spdx']}, {declaration['license_url']}")
        else:
            lines.append(f"- {repo}")
    (stage / NOTICE_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def materialize(
    stage: Path,
    manifest: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, str]]]:
    exclusions = read_exclusions()
    exclusion_log: list[dict[str, str]] = []
    for raw in manifest.get("trees", []):
        target_relative = safe_relative(raw.get("target"), "tree target")
        edit_prefix = Path(*target_relative.parts[1:]) if target_relative.parts[:1] == ("edit",) else None
        copy_tree(
            AGENTS_ROOT / safe_relative(raw.get("source"), "tree source"),
            stage / target_relative,
            edit_prefix=edit_prefix,
            exclusions=exclusions,
            exclusion_log=exclusion_log,
        )
    for raw in manifest.get("files", []):
        target_relative = safe_relative(raw.get("target"), "file target")
        edit_relative = Path(*target_relative.parts[1:]) if target_relative.parts[:1] == ("edit",) else None
        rule = matches_exclusion(edit_relative, exclusions) if edit_relative is not None else None
        if rule:
            exclusion_log.append({"path": edit_relative.as_posix(), "rule": rule})
            continue
        copy_file(
            AGENTS_ROOT / safe_relative(raw.get("source"), "file source"),
            stage / target_relative,
        )
    copy_file(stage / "AGENTS.md", stage / "CLAUDE.md")
    inventory = discover_skills(stage, manifest, exclusions, exclusion_log)
    validate_retained_skill_exclusions(stage, exclusion_log)
    validate_exported_templates(stage)
    rewrite_public_markdown_links(stage)
    validate_no_public_wikilinks(stage)
    write_notices(stage, inventory, manifest)
    owned = sorted(
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file() or path.is_symlink()
    )
    value = {"schema_version": 1, "owned_paths": owned}
    (stage / MANIFEST_NAME).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    unique_exclusions = [
        {"path": path, "rule": rule}
        for path, rule in sorted({(item["path"], item["rule"]) for item in exclusion_log})
    ]
    return [*owned, MANIFEST_NAME], inventory, unique_exclusions


def scan(stage: Path) -> None:
    for path in sorted(stage.rglob("*")):
        relative = path.relative_to(stage)
        rendered = relative.as_posix()
        if path.is_symlink():
            raise ExportError(f"public export contains a symlink: {rendered}")
        if any(part in FORBIDDEN_PARTS for part in relative.parts) or path.suffix in FORBIDDEN_SUFFIXES:
            raise ExportError(f"public export contains forbidden path: {rendered}")
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in CREDENTIAL_PATTERNS:
            if pattern.search(text):
                raise ExportError(f"credential-like {label} found in {rendered}")
        if relative.parts[:2] == ("edit", "skills") and "github" not in relative.parts and PRIVATE_INSTANCE_RE.search(text):
            raise ExportError(f"private instance identifier found in first-party skill: {rendered}")


def public_skill_names(root: Path) -> set[str]:
    return {
        name
        for skill_file in root.rglob("SKILL.md")
        if (name := frontmatter_name(skill_file)) is not None
    }


def prevent_silent_skill_removal(
    destination: Path,
    stage: Path,
    manifest: dict[str, Any],
    exclusions: list[dict[str, str]],
) -> None:
    if not destination.is_dir():
        return
    previous_names = public_skill_names(destination)
    next_names = public_skill_names(stage)
    raw_renames = manifest.get("skill_renames", {})
    if not isinstance(raw_renames, dict) or any(
        not isinstance(old, str) or not isinstance(new, str)
        for old, new in raw_renames.items()
    ):
        raise ExportError("agent export skill_renames needs a string-to-string object")
    invalid = sorted(
        f"{old} -> {new}" for old, new in raw_renames.items() if new not in next_names
    )
    if invalid:
        raise ExportError("agent export skill rename targets are missing: " + ", ".join(invalid))
    raw_removals = manifest.get("skill_removals", [])
    if not isinstance(raw_removals, list) or any(
        not isinstance(name, str) for name in raw_removals
    ):
        raise ExportError("agent export skill_removals needs a string list")
    renamed = {old for old, new in raw_renames.items() if new in next_names}
    removed = set(raw_removals)
    excluded_names = {
        part
        for item in exclusions
        for part in [Path(item["path"]).name]
        if SKILL_NAME_RE.fullmatch(part)
    }
    silent = sorted(previous_names - next_names - renamed - removed - excluded_names)
    if silent:
        raise ExportError("previously public skills disappeared from the export: " + ", ".join(silent))


def replace_owned(destination: Path, stage: Path) -> None:
    previous_manifest = destination / MANIFEST_NAME
    previous = json.loads(previous_manifest.read_text(encoding="utf-8")) if previous_manifest.is_file() else {"owned_paths": []}
    for relative in previous.get("owned_paths", []):
        target = destination / safe_relative(relative, "previous export path")
        if target.is_file() or target.is_symlink():
            target.unlink()
    for relative in LEGACY_PUBLIC_ROOTS:
        target = destination / relative
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
    for source in sorted(stage.rglob("*")):
        target = destination / source.relative_to(stage)
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for directory in sorted((path for path in destination.rglob("*") if path.is_dir()), reverse=True):
        if directory != destination / ".git" and not any(directory.iterdir()):
            directory.rmdir()


def export_changes(destination: Path, stage: Path) -> list[dict[str, str]]:
    previous_manifest = destination / MANIFEST_NAME
    previous = json.loads(previous_manifest.read_text(encoding="utf-8")) if previous_manifest.is_file() else {"owned_paths": []}
    previous_paths = {str(item) for item in previous.get("owned_paths", [])}
    previous_paths.update(
        path.relative_to(destination).as_posix()
        for root in LEGACY_PUBLIC_ROOTS
        for path in (destination / root).rglob("*")
        if path.is_file() or path.is_symlink()
    )
    next_paths = {
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    changes: list[dict[str, str]] = []
    for relative in sorted(previous_paths | next_paths):
        before = destination / relative
        after = stage / relative
        if relative not in previous_paths:
            changes.append({"path": relative, "status": "added"})
        elif relative not in next_paths:
            changes.append({"path": relative, "status": "removed"})
        elif not before.is_file() or file_sha(before) != file_sha(after):
            changes.append({"path": relative, "status": "changed"})
    return changes


def annotate_excluded_removals(
    changes: list[dict[str, str]],
    exclusions: list[dict[str, str]],
) -> None:
    """Attach the responsible user rule to removed files in dry-run output."""
    omitted = [(Path(item["path"]), item["rule"]) for item in exclusions]
    for change in changes:
        public_path = Path(change["path"])
        if change["status"] != "removed" or public_path.parts[:1] != ("edit",):
            continue
        editable_path = Path(*public_path.parts[1:])
        rule = next(
            (
                candidate_rule
                for candidate, candidate_rule in omitted
                if editable_path == candidate or candidate in editable_path.parents
            ),
            None,
        )
        if rule:
            change["exclusion_rule"] = rule


def export(destination: Path, *, apply: bool, manifest_path: Path | None = None) -> dict[str, Any]:
    destination = destination.expanduser().resolve()
    source = AGENTS_ROOT.resolve()
    if destination == source or source in destination.parents or destination in source.parents:
        raise ExportError("agent export destination must be outside the source package and Vault")
    manifest = read_manifest(manifest_path)
    with tempfile.TemporaryDirectory(prefix="ctx9-agent-export-") as temporary:
        stage = Path(temporary)
        owned, inventory, exclusions = materialize(stage, manifest)
        scan(stage)
        prevent_silent_skill_removal(destination, stage, manifest, exclusions)
        changes = export_changes(destination, stage)
        annotate_excluded_removals(changes, exclusions)
        if apply:
            destination.mkdir(parents=True, exist_ok=True)
            replace_owned(destination, stage)
            default_destination = Path(str(manifest["default_export_root"])).expanduser().resolve()
            if destination == default_destination:
                write_internal_inventory(inventory)
    counts = inventory_payload(inventory)
    return {
        "ok": True,
        "applied": apply,
        "destination": str(destination),
        "files": len(owned),
        "included_skills": counts["included"],
        "excluded_skills": counts["excluded"],
        "skill_inventory": inventory,
        "changes": changes,
        "exclusions": exclusions,
    }


def release_preflight(destination: Path) -> dict[str, Any]:
    release = json.loads((EXPORT_ROOT / "release.json").read_text(encoding="utf-8"))
    report = export(destination, apply=False)
    return {**report, "version": release["version"], "publication_ready": True}
