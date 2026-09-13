#!/usr/bin/env python3
"""Managed standalone installation for fleet."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import global_agent_configuration
import fleet_templates
from package_layout import ConfigurationError, installed_config_root, installed_package_root, installed_state_root, load_instance
import working_repo_skills


INSTALL_MARKER = ".fleet-install.json"
MANAGED_TEXT_MARKER = "fleet.managed"
PACKAGE_VERSION = "0.2.10"
ICLOUD_DUPLICATE_RE = re.compile(r"^.+ \d+(?:\.[^.]+)?$")


def install_ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in {"__pycache__", ".DS_Store", working_repo_skills.MARKER}
        or name.endswith(".pyc")
        or ICLOUD_DUPLICATE_RE.fullmatch(name)
    }
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
    required = [source / "internal" / name for name in ("src", "schemas", "defaults")]
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
    agents_root = source
    root = agents_root / "edit/skills"
    if not root.is_dir():
        return []
    if not (source / "internal/release/agent-package-export.json").is_file():
        return [(skill.name, skill) for skill in source_skill_roots(root)]
    instance_registry = source / "edit/settings/skills/skill-sources.json"
    if not instance_registry.is_file():
        return [(skill.name, skill) for skill in source_skill_roots(root)]

    owned = [
        skill
        for group in sorted(root.iterdir())
        if group.is_dir() and not group.is_symlink() and group.name.startswith("_")
        for skill in source_skill_roots(group)
    ]
    projected = working_repo_skills.plan(agents_root, require_sources=False)
    if projected.actions:
        raise InstallError("skill materializations are stale; run fleet sync --skills first")
    github = [skill for skill in projected.skills if skill.origin == "gh"]
    return [
        *((skill.name, skill) for skill in owned),
        *((skill.name, skill.path) for skill in github),
    ]


def is_private_source(source: Path) -> bool:
    return (source / "internal/release/agent-package-export.json").is_file()


def stage_public_skills(
    source: Path,
    stage: Path,
    *,
    template_values: dict[str, object] | None = None,
) -> None:
    names: set[str] = set()
    for name, skill in public_skill_roots(source):
        if name in names:
            raise InstallError(f"duplicate public skill name: {name}")
        names.add(name)
        target = stage / "skills" / name
        shutil.copytree(skill, target, symlinks=False, ignore=install_ignore)
        config = target / "fleet-templates/render.json"
        if not config.is_file():
            continue
        if template_values is None:
            raise InstallError(f"skill {name} needs machine facts for fleet templates")
        try:
            outputs = fleet_templates.render_bundle(target, config, template_values)
        except fleet_templates.FleetTemplateError as exc:
            raise InstallError(f"skill {name} template failed: {exc}") from exc
        for output in outputs:
            output_path = target / output.target
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output.content, encoding="utf-8")


def stage_workspace_sync_helpers(source: Path, stage: Path) -> None:
    """Bundle private-source helpers that public exports already place in src/."""
    helper_source = source / "edit/skills/_infrastructure/infra-i-sync-code-workspaces/scripts"
    for name in WORKSPACE_SYNC_HELPERS:
        target = stage / "src" / name
        if target.is_file():
            continue
        candidate = helper_source / name
        if candidate.is_file() and not candidate.is_symlink():
            shutil.copy2(candidate, target)


def managed_file(path: Path) -> bool:
    return path.is_file() and MANAGED_TEXT_MARKER in path.read_text(encoding="utf-8", errors="replace")


def managed_alias(path: Path) -> bool:
    """Recognize an owned alias while migrating it to the canonical target."""
    if not path.is_symlink():
        return False
    try:
        return managed_file(path.resolve(strict=True))
    except (OSError, RuntimeError):
        return False


def render_global(
    source: Path,
    config_root: Path,
    machine_id: str | None = None,
    *,
    source_home: Path,
) -> str:
    instance = load_instance(config_root)
    machines = instance["fleet"]["machines"]
    selected_id = machine_id or next(key for key, value in machines.items() if value.get("role") == "primary")
    machine = machines.get(selected_id)
    if not isinstance(machine, dict):
        raise InstallError(f"machine does not exist in installed configuration: {selected_id}")
    raw_registry = json.loads((config_root / "fleet/machines.json").read_text(encoding="utf-8"))
    return global_agent_configuration.render_global_agents(
        source,
        config_root,
        raw_registry,
        machine,
        source_home=source_home,
    )


def customize_machine_settings(
    machines_path: Path,
    home: Path,
    *,
    machine_id: str | None,
    code_root: str | None,
    vault_root: str | None,
) -> str:
    machines = json.loads(machines_path.read_text(encoding="utf-8"))
    primary = machines["machines"][0]
    selected_id = machine_id or str(primary["id"])
    if machine_id:
        primary["id"] = machine_id
        primary["display_name"] = machine_id.replace("-", " ").title()
        machines["primary_machine_id"] = machine_id
        if machines["vault_git"]["owner_machine_id"] is not None:
            machines["vault_git"]["owner_machine_id"] = machine_id
            machines["vault_git"]["refresh_owner_machine_id"] = machine_id
    primary["home"] = str(home)
    primary["platform"] = "macos" if platform.system() == "Darwin" else "linux"
    primary["roots"]["code"] = code_root or "~/Code"
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
    return selected_id


def settings_include_machine(settings_root: Path, machine_id: str | None) -> bool:
    if not machine_id:
        return False
    try:
        registry = json.loads((settings_root / "fleet/machines.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    machines = registry.get("machines")
    return isinstance(machines, list) and any(
        isinstance(machine, dict) and machine.get("id") == machine_id
        for machine in machines
    )


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
        if path.is_file() and not path.is_symlink() and managed_file(path):
            if apply:
                path.unlink()
        elif not managed_alias(path):
            raise InstallError(f"refusing to replace unmanaged alias: {path}")
        elif apply:
            path.unlink()
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
    initialize_source: bool = False,
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
    if global_instructions:
        ensure_managed_symlink(
            home / ".codex/AGENTS.md",
            "../.agents/instructions/AGENTS.md",
            apply=False,
        )
        if claude_alias:
            ensure_managed_symlink(
                home / ".claude/CLAUDE.md",
                "../.agents/instructions/AGENTS.md",
                apply=False,
            )
    actions: list[dict[str, str]] = []
    settings_source = source / "edit/settings"
    if not settings_source.is_dir():
        settings_source = source / "internal/defaults/settings"
    selected_id = machine_id
    if initialize_source and apply:
        if settings_source != source / "edit/settings":
            raise InstallError("editable source settings are missing")
        selected_id = customize_machine_settings(
            settings_source / "fleet/machines.json",
            home,
            machine_id=machine_id,
            code_root=code_root,
            vault_root=vault_root,
        )
        actions.append({"path": str(settings_source / "fleet/machines.json"), "status": "initialized"})
    staged_root: Path | None = None
    if apply:
        state_target.mkdir(parents=True, exist_ok=True, mode=0o700)
        staged_root = Path(tempfile.mkdtemp(prefix="fleet-install-", dir=state_target))
        for path in parts:
            shutil.copytree(path, staged_root / path.name, symlinks=True, ignore=install_ignore)
    if not config_target.exists():
        if apply:
            shutil.copytree(settings_source, config_target)
            if not initialize_source and not settings_include_machine(settings_source, machine_id):
                selected_id = customize_machine_settings(
                    config_target / "fleet/machines.json",
                    home,
                    machine_id=machine_id,
                    code_root=code_root,
                    vault_root=vault_root,
                )
        actions.append({"path": str(config_target), "status": "initialized" if apply else "would-initialize"})
    else:
        actions.append({"path": str(config_target), "status": "preserved"})

    if apply and staged_root is not None:
        instance = load_instance(config_target)
        selected_id = selected_id or next(
            key for key, value in instance["fleet"]["machines"].items() if value.get("role") == "primary"
        )
        machine = instance["fleet"]["machines"].get(selected_id)
        if not isinstance(machine, dict):
            raise InstallError(f"machine does not exist in installed configuration: {selected_id}")
        raw_registry = json.loads((config_target / "fleet/machines.json").read_text(encoding="utf-8"))
        template_values = global_agent_configuration.machine_template_values(
            raw_registry,
            machine,
            source_home=home,
        )
        if not is_private_source(source):
            stage_public_skills(source, staged_root, template_values=template_values)
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

    identity = state_target / "machine-id"
    if apply:
        identity.parent.mkdir(parents=True, exist_ok=True)
        identity.write_text(str(selected_id or machine_id or "primary") + "\n", encoding="utf-8")
    actions.append({"path": str(identity), "status": "written" if apply else "would-write"})

    launcher = home / ".local/bin/fleet"
    launcher_content = (
        f"#!/bin/sh\n# {MANAGED_TEXT_MARKER}\n"
        "command_name=${1:-}\n"
        "case \"$command_name\" in\n"
        "  sync|update)\n"
        "    shift\n"
        f"    exec python3 {json.dumps(str(package_target / 'src/fleet.py'))} \"$command_name\" \"$@\" --root {json.dumps(str(source))}\n"
        "    ;;\n"
        "  *)\n"
        f"    exec python3 {json.dumps(str(package_target / 'src/fleet.py'))} \"$@\"\n"
        "    ;;\n"
        "esac\n"
    )
    actions.append({"path": str(launcher), "status": ensure_managed_text(launcher, launcher_content, apply=apply)})
    if apply:
        launcher.chmod(0o755)

    owned = [str(package_target), str(launcher), str(identity)]
    if global_instructions:
        if not apply and not config_target.is_dir():
            raise InstallError("apply the initial install before rendering global instructions")
        rendered = render_global(source, config_target, selected_id, source_home=home)
        target = home / ".agents/instructions/AGENTS.md"
        actions.append({"path": str(target), "status": ensure_managed_text(target, rendered, apply=apply)})
        owned.append(str(target))
        codex_alias = home / ".codex/AGENTS.md"
        actions.append(
            {
                "path": str(codex_alias),
                "status": ensure_managed_symlink(
                    codex_alias,
                    "../.agents/instructions/AGENTS.md",
                    apply=apply,
                ),
            }
        )
        owned.append(str(codex_alias))
        if claude_alias:
            alias = home / ".claude/CLAUDE.md"
            actions.append(
                {
                    "path": str(alias),
                    "status": ensure_managed_symlink(
                        alias,
                        "../.agents/instructions/AGENTS.md",
                        apply=apply,
                    ),
                }
            )
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
    installed_version: str | None = None
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
    else:
        try:
            installed = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"installed ownership manifest is invalid: {exc}")
        else:
            installed_version = installed.get("package_version")
            if installed_version != PACKAGE_VERSION:
                problems.append(
                    f"installed Fleet version is {installed_version or 'unknown'}; expected {PACKAGE_VERSION}"
                )
    return {
        "ok": not problems,
        "ready": not problems,
        "version": installed_version,
        "expected_version": PACKAGE_VERSION,
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
        elif path == state / "machine-id" and path.is_file():
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
