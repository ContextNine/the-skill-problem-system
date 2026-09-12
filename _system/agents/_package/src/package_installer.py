#!/usr/bin/env python3
"""Managed standalone installation for fleet."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from package_layout import ConfigurationError, installed_config_root, installed_package_root, installed_state_root, load_instance
import working_repo_skills


INSTALL_MARKER = ".fleet-install.json"
MANAGED_TEXT_MARKER = "fleet.managed"
PACKAGE_VERSION = "0.2.2"
INSTALL_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".DS_Store", working_repo_skills.MARKER
)
WORKSPACE_SYNC_HELPERS = (
    "agent_configuration_target_worker.py",
    "code_workspace_target_worker.py",
    "plugin_reconciliation.py",
    "sync_agent_configuration.py",
    "sync_code_workspaces.py",
)


class InstallError(RuntimeError):
    pass


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_fingerprint(root: Path) -> list[tuple[str, str, str]]:
    """Return stable content and symlink identity without install metadata."""
    result: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == INSTALL_MARKER or "__pycache__" in path.parts or path.suffix == ".pyc" or path.name == ".DS_Store":
            continue
        if path.is_symlink():
            result.append((relative, "symlink", os.readlink(path)))
        elif path.is_file():
            result.append((relative, "file", digest(path)))
    return result


def distribution_paths(source: Path) -> list[Path]:
    required = [source / name for name in ("src", "docs", "templates", "schemas", "defaults")]
    missing = [str(path) for path in required if not path.is_dir()]
    if missing:
        raise InstallError("agent package distribution is incomplete: " + ", ".join(missing))
    return required


def source_skill_roots(root: Path) -> list[Path]:
    found: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        if (directory / "SKILL.md").is_file():
            found.append(directory)
            continue
        pending.extend(
            child
            for child in directory.iterdir()
            if child.is_dir() and not child.is_symlink()
        )
    return sorted(found)


def public_skill_roots(source: Path) -> list[tuple[str, Path]]:
    agents_root = source.parent if source.name == "_package" else source
    root = agents_root / "skills"
    if not root.is_dir():
        return []
    instance_registry = source / "instance/skills/skill-sources.json"
    if not instance_registry.is_file():
        return [(skill.name, skill) for skill in source_skill_roots(root)]

    vault_root = agents_root.parents[1]
    owned = [
        skill
        for group in sorted(root.iterdir())
        if group.is_dir() and not group.is_symlink() and group.name.startswith("_")
        for skill in source_skill_roots(group)
    ]
    projected = working_repo_skills.plan(vault_root, require_sources=False)
    if projected.actions:
        raise InstallError("skill materializations are stale; run fleet sync --skills first")
    github = [skill for skill in projected.skills if skill.origin == "gh"]
    return [
        *((skill.name, skill) for skill in owned),
        *((skill.name, skill.path) for skill in github),
    ]


def stage_public_skills(source: Path, stage: Path) -> None:
    names: set[str] = set()
    for name, skill in public_skill_roots(source):
        if name in names:
            raise InstallError(f"duplicate public skill name: {name}")
        names.add(name)
        shutil.copytree(skill, stage / "skills" / name, symlinks=False, ignore=INSTALL_IGNORE)


def stage_workspace_sync_helpers(source: Path, stage: Path) -> None:
    """Bundle private-source helpers that public exports already place in src/."""
    helper_source = source.parent / "skills/_infrastructure/infra-i-sync-code-workspaces/scripts"
    for name in WORKSPACE_SYNC_HELPERS:
        target = stage / "src" / name
        if target.is_file():
            continue
        candidate = helper_source / name
        if candidate.is_file() and not candidate.is_symlink():
            shutil.copy2(candidate, target)


def managed_file(path: Path) -> bool:
    return path.is_file() and MANAGED_TEXT_MARKER in path.read_text(encoding="utf-8", errors="replace")


def render_global(config_root: Path, package_root: Path, machine_id: str | None = None) -> str:
    instance = load_instance(config_root)
    machines = instance["fleet"]["machines"]
    selected_id = machine_id or next(key for key, value in machines.items() if value.get("role") == "primary")
    machine = machines.get(selected_id)
    if not isinstance(machine, dict):
        raise InstallError(f"machine does not exist in installed configuration: {selected_id}")
    base = (config_root / "instructions/AGENTS.md").read_text(encoding="utf-8").rstrip()
    templates = package_root / "templates/instructions"
    platform = (templates / "platform" / f"{machine['platform']}.md").read_text(encoding="utf-8").strip()
    role = (templates / "role" / f"{machine['role']}.md").read_text(encoding="utf-8").strip()
    peers = [
        f"- {peer.get('display_name')} (`{peer_id}`): {peer.get('role')} {peer.get('platform')}."
        for peer_id, peer in machines.items()
        if peer_id != selected_id and peer.get("enabled")
    ]
    primary_id = next(key for key, value in machines.items() if value.get("role") == "primary")
    primary = machines[primary_id]
    preview_values = {
        "primary_ssh_alias": primary.get("ssh_alias") or primary_id,
        "primary_loopback": "127.0.0.1",
        "primary_port": "<primary-port>",
        "worker_loopback": "127.0.0.1",
        "worker_port": "<worker-port>",
    }
    development_previews = (
        (templates / "development-previews.md").read_text(encoding="utf-8").format_map(preview_values).strip()
        if peers
        else ""
    )
    values = {
        "display_name": machine["display_name"],
        "machine_id": selected_id,
        "platform_name": "macOS" if machine["platform"] == "macos" else "Linux",
        "code_root": machine["resolved_roots"]["code"],
        "vault_root": machine["resolved_roots"]["vault"] or "not enrolled",
        "vault_participation": machine["vault"]["checkout_mode"] if machine["vault"]["enabled"] else "disabled",
        "vault_guidance": (
            "This machine is the registered standalone Vault owner."
            if machine["vault"]["enabled"]
            else "This machine is a Code-repository worker only and has no Vault access."
        ),
        "machine_access_provider": "configured registry route",
        "mesh_address": "see installed machine configuration",
        "peers": "\n".join(peers) if peers else "- No other enabled machines are registered.",
        "development_previews": development_previews,
        "access_guidance": "",
        "primary_display_name": primary["display_name"],
        "primary_id": primary_id,
        "primary_machine_access_provider": "registered route",
        "primary_mesh_address": "see installed machine configuration",
    }
    machine_text = (templates / "machine.md").read_text(encoding="utf-8").format_map(values).strip()
    return f"{base}\n\n***\n\n<!-- {MANAGED_TEXT_MARKER} -->\n\n***\n\n{platform}\n\n***\n\n{role.format_map(values)}\n\n***\n\n{machine_text}\n"


def ensure_managed_text(path: Path, content: str, *, apply: bool) -> str:
    if path.exists() or path.is_symlink():
        if path.is_file() and not path.is_symlink() and path.read_text(encoding="utf-8", errors="replace") == content:
            return "match"
        if not managed_file(path):
            raise InstallError(f"refusing to replace unmanaged file: {path}")
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    return "installed" if apply else "different"


def ensure_managed_symlink(path: Path, target: str, *, apply: bool) -> str:
    if path.is_symlink() and os.readlink(path) == target:
        return "match"
    if path.exists() or path.is_symlink():
        raise InstallError(f"refusing to replace unmanaged alias: {path}")
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
    return "installed" if apply else "missing"


def install(
    source: Path,
    home: Path,
    *,
    apply: bool,
    global_instructions: bool,
    claude_alias: bool,
    discovery_aliases: bool,
    machine_id: str | None = None,
    code_root: str | None = None,
    vault_root: str | None = None,
) -> dict[str, Any]:
    if claude_alias and not global_instructions:
        raise InstallError("Claude instruction alias requires managed global instructions")
    source = source.expanduser().resolve()
    home = home.expanduser().resolve()
    parts = distribution_paths(source)
    package_target = installed_package_root(home)
    config_target = installed_config_root(home)
    state_target = installed_state_root(home)
    marker = package_target / INSTALL_MARKER
    if package_target.exists() and not marker.is_file():
        raise InstallError(f"refusing to replace unmanaged package directory: {package_target}")
    actions: list[dict[str, str]] = []
    staged_root: Path | None = None
    if apply:
        state_target.mkdir(parents=True, exist_ok=True, mode=0o700)
        staged_root = Path(tempfile.mkdtemp(prefix="fleet-install-", dir=state_target))
        for path in parts:
            shutil.copytree(path, staged_root / path.name, symlinks=True, ignore=INSTALL_IGNORE)
        stage_public_skills(source, staged_root)
        stage_workspace_sync_helpers(source, staged_root)
        (staged_root / INSTALL_MARKER).write_text(
            json.dumps({"schema_version": 1, "installed_at": utc_stamp()}, indent=2) + "\n",
            encoding="utf-8",
        )
        package_matches = package_target.exists() and tree_fingerprint(staged_root) == tree_fingerprint(package_target)
        if package_matches:
            shutil.rmtree(staged_root)
            staged_root = None
        elif package_target.exists():
            backup = state_target / "backups" / f"package-{utc_stamp()}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            package_target.replace(backup)
            actions.append({"path": str(backup), "status": "backup"})
        if staged_root is not None:
            package_target.parent.mkdir(parents=True, exist_ok=True)
            staged_root.replace(package_target)
    package_status = "match" if apply and package_target.exists() and staged_root is None else ("installed" if apply else "would-install")
    actions.append({"path": str(package_target), "status": package_status})
    if not config_target.exists():
        if apply:
            shutil.copytree(source / "defaults/instance", config_target)
            machines_path = config_target / "fleet/machines.json"
            machines = json.loads(machines_path.read_text(encoding="utf-8"))
            primary = machines["machines"][0]
            if machine_id:
                primary["id"] = machine_id
                primary["display_name"] = machine_id.replace("-", " ").title()
                machines["primary_machine_id"] = machine_id
                if machines["vault_git"]["owner_machine_id"] is not None:
                    machines["vault_git"]["owner_machine_id"] = machine_id
                    machines["vault_git"]["refresh_owner_machine_id"] = machine_id
            primary["home"] = str(home)
            primary["platform"] = "macos" if platform.system() == "Darwin" else "linux"
            primary["roots"]["code"] = code_root or ("~/" + "Code")
            if vault_root:
                if primary["platform"] != "macos":
                    raise InstallError(
                        "a Linux primary cannot use a direct Vault root; configure an optional remote-sshfs worker after onboarding"
                    )
                primary["roots"]["vault"] = vault_root
                primary["vault"] = {
                    "enabled": True,
                    "checkout_mode": "primary-external-git",
                    "required": True,
                }
                machines["vault_git"]["owner_machine_id"] = primary["id"]
                machines["vault_git"]["refresh_owner_machine_id"] = primary["id"]
            machines_path.write_text(json.dumps(machines, indent=2) + "\n", encoding="utf-8")
        actions.append({"path": str(config_target), "status": "initialized" if apply else "would-initialize"})
    else:
        actions.append({"path": str(config_target), "status": "preserved"})

    launcher = home / ".local/bin/fleet"
    launcher_content = f"#!/bin/sh\n# {MANAGED_TEXT_MARKER}\nexec python3 {json.dumps(str(package_target / 'src/fleet.py'))} \"$@\"\n"
    actions.append({"path": str(launcher), "status": ensure_managed_text(launcher, launcher_content, apply=apply)})
    if apply:
        launcher.chmod(0o755)

    owned = [str(package_target), str(launcher)]
    if global_instructions:
        rendered = render_global(config_target, package_target, machine_id)
        target = home / ".codex/AGENTS.md"
        actions.append({"path": str(target), "status": ensure_managed_text(target, rendered, apply=apply)})
        owned.append(str(target))
        if claude_alias:
            alias = home / ".claude/CLAUDE.md"
            actions.append({"path": str(alias), "status": ensure_managed_symlink(alias, "../.codex/AGENTS.md", apply=apply)})
            owned.append(str(alias))
    if discovery_aliases and (package_target / "skills").is_dir():
        for skill in sorted((package_target / "skills").iterdir()):
            if not skill.is_dir():
                continue
            alias = home / ".agents/skills" / skill.name
            actions.append({"path": str(alias), "status": ensure_managed_symlink(alias, str(skill), apply=apply)})
            owned.append(str(alias))
    manifest = state_target / "installed.json"
    value = {"schema_version": 1, "package_version": PACKAGE_VERSION, "owned_paths": sorted(set(owned))}
    manifest_status = "would-write"
    if apply:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(value, indent=2) + "\n"
        if manifest.is_file() and manifest.read_text(encoding="utf-8") == content:
            manifest_status = "match"
        else:
            manifest.write_text(content, encoding="utf-8")
            manifest_status = "written"
    actions.append({"path": str(manifest), "status": manifest_status})
    return {"ok": True, "ready": True, "applied": apply, "version": PACKAGE_VERSION, "actions": actions}


def verify(home: Path) -> dict[str, Any]:
    home = home.expanduser().resolve()
    package = installed_package_root(home)
    config = installed_config_root(home)
    state = installed_state_root(home)
    manifest = state / "installed.json"
    problems: list[str] = []
    if not (package / INSTALL_MARKER).is_file():
        problems.append(f"managed package marker is missing: {package}")
    if not config.is_dir():
        problems.append(f"installed config is missing: {config}")
    else:
        try:
            load_instance(config)
        except ConfigurationError as exc:
            problems.append(str(exc))
    if not manifest.is_file():
        problems.append(f"installed ownership manifest is missing: {manifest}")
    return {
        "ok": not problems,
        "ready": not problems,
        "version": PACKAGE_VERSION,
        "problems": problems,
        "package": str(package),
        "config": str(config),
    }


def uninstall(home: Path, *, apply: bool) -> dict[str, Any]:
    home = home.expanduser().resolve()
    state = installed_state_root(home)
    manifest_path = state / "installed.json"
    if not manifest_path.is_file():
        raise InstallError(f"installed ownership manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [Path(value) for value in manifest.get("owned_paths", [])]
    for path in paths:
        if not path.is_absolute() or home not in path.parents:
            raise InstallError(f"ownership manifest contains an unsafe path: {path}")
    actions: list[dict[str, str]] = []
    for path in sorted(paths, key=lambda item: len(item.parts), reverse=True):
        if not (path.exists() or path.is_symlink()):
            actions.append({"path": str(path), "status": "missing"})
            continue
        package = installed_package_root(home)
        if path == package:
            if not (path / INSTALL_MARKER).is_file():
                raise InstallError(f"refusing to remove unmarked package directory: {path}")
            if apply:
                shutil.rmtree(path)
        elif path.is_symlink():
            if apply:
                path.unlink()
        elif managed_file(path):
            if apply:
                path.unlink()
        else:
            raise InstallError(f"owned path was modified or is unmanaged; refusing removal: {path}")
        actions.append({"path": str(path), "status": "removed" if apply else "would-remove"})
    if apply:
        manifest_path.unlink()
    return {"ok": True, "ready": True, "applied": apply, "version": PACKAGE_VERSION, "actions": actions}
