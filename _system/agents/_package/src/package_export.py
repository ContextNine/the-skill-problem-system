#!/usr/bin/env python3
"""Build the deterministic public Skill Problem System repository."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from package_layout import AGENTS_ROOT, EXPORT_ROOT


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
FORBIDDEN_PARTS = {"private", "__pycache__", ".git", "catalog", "dormant"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}


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


def copy_tree(source: Path, target: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise ExportError(f"public source tree is missing or is a symlink: {source}")
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_symlink():
            raise ExportError(f"public source tree contains a symlink: {path}")
        if any(part in FORBIDDEN_PARTS for part in relative.parts) or path.suffix in FORBIDDEN_SUFFIXES:
            continue
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            copy_file(path, destination)


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


def github_repo(skill_file: Path) -> str | None:
    match = re.search(r"github-repo:\s*(\S+)", skill_file.read_text(encoding="utf-8"))
    return match.group(1).rstrip("/") if match else None


def strip_install_metadata(skill_file: Path) -> None:
    text = skill_file.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^\s+github-(?:path|ref|repo|tree-sha):.*\n", "", text)
    text = re.sub(r"(?m)^metadata:\n(?=[A-Za-z][A-Za-z0-9_-]*:)", "", text)
    skill_file.write_text(text, encoding="utf-8")


def declared_external_sources() -> dict[str, str]:
    """Map projected skill source paths to their declared GitHub repository."""
    path = AGENTS_ROOT / "_package/instance/skills/sources.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    mapped: dict[str, str] = {}
    for repo in data.get("repos", []):
        url = f"https://github.com/{repo['github']}"
        for skill in repo.get("skills", []):
            mode = skill.get("mode", "manual")
            target = f"skills/{mode}/{skill['group']}/{skill['name']}"
            mapped[target] = url
    return mapped


def skill_decision(
    skill_dir: Path,
    mode: str,
    relative: Path,
    manifest: dict[str, Any],
    projected_sources: dict[str, str],
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
    source_key = f"skills/{mode}/{relative.as_posix()}"
    repo = projected_sources.get(source_key) or github_repo(skill_file)
    if mode == "projected":
        return False, "repository-owned projection is not a redistributable source", repo, None
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


def discover_skills(stage: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    names: dict[str, Path] = {}
    projected_sources = declared_external_sources()
    modes = ("auto", "manual", "github", "projected")
    for mode in modes:
        root = AGENTS_ROOT / "skills" / mode
        if not root.is_dir():
            continue
        for skill_file in sorted(root.rglob("SKILL.md")):
            skill_dir = skill_file.parent
            relative = skill_dir.relative_to(root)
            if skill_file.is_symlink() or any(path.is_symlink() for path in skill_dir.rglob("*")):
                raise ExportError(f"active skill contains a symlink: {skill_dir}")
            name = frontmatter_name(skill_file)
            if not name or not SKILL_NAME_RE.fullmatch(name) or skill_dir.name != name:
                raise ExportError(f"invalid skill name or directory: {skill_dir} ({name!r})")
            if name in names:
                raise ExportError(f"duplicate active skill name {name}: {names[name]} and {skill_dir}")
            names[name] = skill_dir
            include, reason, source_repo, license_id = skill_decision(
                skill_dir, mode, relative, manifest, projected_sources
            )
            item = {
                "name": name,
                "source": f"_system/agents/skills/{mode}/{relative.as_posix()}",
                "status": "included" if include else "excluded",
                "reason": reason,
            }
            if source_repo:
                item["source_repository"] = source_repo
            if license_id:
                item["license"] = license_id
            inventory.append(item)
            if include:
                target = stage / "_system/agents/skills" / mode / relative
                copy_tree(skill_dir, target)
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


def materialize(stage: Path, manifest: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    for raw in manifest.get("trees", []):
        copy_tree(
            AGENTS_ROOT / safe_relative(raw.get("source"), "tree source"),
            stage / safe_relative(raw.get("target"), "tree target"),
        )
    for raw in manifest.get("files", []):
        copy_file(
            AGENTS_ROOT / safe_relative(raw.get("source"), "file source"),
            stage / safe_relative(raw.get("target"), "file target"),
        )
    copy_file(stage / "AGENTS.md", stage / "CLAUDE.md")
    inventory = discover_skills(stage, manifest)
    write_notices(stage, inventory, manifest)
    owned = sorted(
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file() or path.is_symlink()
    )
    value = {"schema_version": 1, "owned_paths": owned}
    (stage / MANIFEST_NAME).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return [*owned, MANIFEST_NAME], inventory


def scan(stage: Path) -> None:
    for path in sorted(stage.rglob("*")):
        relative = path.relative_to(stage)
        rendered = relative.as_posix()
        if path.is_symlink():
            raise ExportError(f"public export contains a symlink: {rendered}")
        package_private = relative.parts[:4] in {
            ("_system", "agents", "_package", "instance"),
            ("_system", "agents", "_package", "generated"),
        }
        if package_private or any(part in FORBIDDEN_PARTS for part in relative.parts) or path.suffix in FORBIDDEN_SUFFIXES:
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


def public_skill_names(root: Path) -> set[str]:
    return {
        name
        for skill_file in root.rglob("SKILL.md")
        if (name := frontmatter_name(skill_file)) is not None
    }


def prevent_silent_skill_removal(destination: Path, stage: Path) -> None:
    if not destination.is_dir():
        return
    silent = sorted(public_skill_names(destination) - public_skill_names(stage))
    if silent:
        raise ExportError("previously public skills disappeared from the export: " + ", ".join(silent))


def replace_owned(destination: Path, stage: Path) -> None:
    previous_manifest = destination / MANIFEST_NAME
    previous = json.loads(previous_manifest.read_text(encoding="utf-8")) if previous_manifest.is_file() else {"owned_paths": []}
    for relative in previous.get("owned_paths", []):
        target = destination / safe_relative(relative, "previous export path")
        if target.is_file() or target.is_symlink():
            target.unlink()
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


def export(destination: Path, *, apply: bool, manifest_path: Path | None = None) -> dict[str, Any]:
    destination = destination.expanduser().resolve()
    source = AGENTS_ROOT.resolve()
    if destination == source or source in destination.parents or destination in source.parents:
        raise ExportError("agent export destination must be outside the source package and Vault")
    manifest = read_manifest(manifest_path)
    with tempfile.TemporaryDirectory(prefix="ctx9-agent-export-") as temporary:
        stage = Path(temporary)
        owned, inventory = materialize(stage, manifest)
        scan(stage)
        prevent_silent_skill_removal(destination, stage)
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
    }


def release_preflight(destination: Path) -> dict[str, Any]:
    release = json.loads((EXPORT_ROOT / "release.json").read_text(encoding="utf-8"))
    report = export(destination, apply=False)
    return {**report, "version": release["version"], "publication_ready": True}
