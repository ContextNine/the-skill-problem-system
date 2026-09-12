#!/usr/bin/env python3
"""Canonical source, installed, and runtime paths for the agent package."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
AGENTS_ROOT = PACKAGE_ROOT.parent
SYSTEM_ROOT = AGENTS_ROOT.parent
VAULT_ROOT = SYSTEM_ROOT.parent

SKILLS_ROOT = AGENTS_ROOT / "skills"
GITHUB_SKILLS_ROOT = SKILLS_ROOT / "github"
OVERLAY_SKILLS_ROOT = SKILLS_ROOT / "overlays"
SNAPSHOT_SKILLS_ROOT = SKILLS_ROOT / "snapshots"
CATALOG_ROOT = SKILLS_ROOT / "catalog"
DORMANT_SKILLS_ROOT = SKILLS_ROOT / "dormant"

SOURCE_INSTANCE_ROOT = PACKAGE_ROOT / "instance"
DEFAULTS_ROOT = PACKAGE_ROOT / "defaults"
GENERATED_ROOT = PACKAGE_ROOT / "generated"
TEMPLATES_ROOT = PACKAGE_ROOT / "templates"
SCHEMAS_ROOT = PACKAGE_ROOT / "schemas"
DOCS_ROOT = PACKAGE_ROOT / "docs"
EXPORT_ROOT = PACKAGE_ROOT / "export"

PROFILE_PATH = SOURCE_INSTANCE_ROOT / "profile.json"
MACHINES_PATH = SOURCE_INSTANCE_ROOT / "fleet/machines.json"
WORKSPACES_PATH = SOURCE_INSTANCE_ROOT / "fleet/workspaces.json"
MACHINE_SECRETS_PATH = SOURCE_INSTANCE_ROOT / "fleet/machine-secrets.json"
STARTUP_PATH = SOURCE_INSTANCE_ROOT / "fleet/startup.json"
SKILL_SOURCES_PATH = SOURCE_INSTANCE_ROOT / "skills/skill-sources.json"
INSTRUCTION_FRAGMENTS_PATH = SOURCE_INSTANCE_ROOT / "instructions/fragments.json"
BASE_INSTRUCTIONS_PATH = SOURCE_INSTANCE_ROOT / "instructions/AGENTS.md"
LANGFUSE_PATH = SOURCE_INSTANCE_ROOT / "integrations/langfuse.json"
DEPENDENCY_SELECTIONS_PATH = SOURCE_INSTANCE_ROOT / "dependencies/selections.json"
DEPENDENCY_DEFAULTS_PATH = DEFAULTS_ROOT / "dependencies.json"
DEPENDENCY_LOCK_PATH = GENERATED_ROOT / "state/dependencies.lock.json"


class ConfigurationError(ValueError):
    pass


def installed_package_root(home: Path | None = None) -> Path:
    override = os.environ.get("CTX9_FLEET_PACKAGE_HOME")
    return Path(override).expanduser().resolve() if override else (home or Path.home()) / ".local/share/fleet"


def installed_config_root(home: Path | None = None) -> Path:
    override = os.environ.get("CTX9_FLEET_CONFIG_HOME")
    return Path(override).expanduser().resolve() if override else (home or Path.home()) / ".config/ctx9/fleet"


def installed_state_root(home: Path | None = None) -> Path:
    override = os.environ.get("CTX9_FLEET_STATE_HOME")
    return Path(override).expanduser().resolve() if override else (home or Path.home()) / ".local/state/fleet"


def active_instance_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    override = os.environ.get("CTX9_FLEET_CONFIG_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if SOURCE_INSTANCE_ROOT.is_dir():
        return SOURCE_INSTANCE_ROOT
    return installed_config_root().resolve()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"{label} is missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"{label} is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be a JSON object: {path}")
    return value


def expand_registered_path(value: object, home: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(home, str) or not PurePosixPath(home).is_absolute() or "$" in home:
        raise ConfigurationError(f"registered home must be an absolute path: {home!r}")
    if not isinstance(value, str) or not value or "$" in value:
        raise ConfigurationError(f"registered root must be a non-empty path: {value!r}")
    if value == "~":
        resolved = PurePosixPath(home)
    elif value.startswith("~/"):
        resolved = PurePosixPath(home).joinpath(*PurePosixPath(value[2:]).parts)
    else:
        resolved = PurePosixPath(value)
    if not resolved.is_absolute() or ".." in resolved.parts or value.startswith("~") and not value.startswith("~/") and value != "~":
        raise ConfigurationError(f"registered root does not resolve safely: {value!r}")
    return resolved.as_posix()


def validate_machines(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if data.get("schema_version") != 7:
        raise ConfigurationError("machine registry needs schema_version 7")
    machines = data.get("machines")
    if not isinstance(machines, list) or not machines:
        raise ConfigurationError("machine registry needs a non-empty machines list")
    resolved: dict[str, dict[str, Any]] = {}
    enabled_ids: set[str] = set()
    primary_id = data.get("primary_machine_id")
    for machine in machines:
        if not isinstance(machine, dict):
            raise ConfigurationError("every machine must be an object")
        machine_id = machine.get("id")
        if not isinstance(machine_id, str) or not machine_id:
            raise ConfigurationError("every machine needs an id")
        if machine_id in resolved:
            raise ConfigurationError(f"duplicate machine id: {machine_id}")
        if machine.get("enabled"):
            if machine_id in enabled_ids:
                raise ConfigurationError(f"duplicate enabled machine id: {machine_id}")
            enabled_ids.add(machine_id)
        roots = machine.get("roots")
        vault = machine.get("vault")
        if (
            not isinstance(roots, dict)
            or set(roots) != {"code", "vault"}
            or not isinstance(vault, dict)
            or not {"enabled", "checkout_mode", "required"} <= set(vault)
            or set(vault) - {"enabled", "checkout_mode", "required", "remote_access"}
            or not isinstance(vault.get("enabled"), bool)
            or not isinstance(vault.get("required"), bool)
        ):
            raise ConfigurationError(f"machine {machine_id!r} needs roots and explicit vault participation")
        mode = vault.get("checkout_mode")
        if mode not in {"primary-external-git", "icloud-gitless", "remote-sshfs", "none"}:
            raise ConfigurationError(f"machine {machine_id!r} has an unsupported Vault mode")
        if vault["enabled"] != vault["required"] or vault["enabled"] != (mode != "none"):
            raise ConfigurationError(f"machine {machine_id!r} has inconsistent Vault enablement")
        code_root = expand_registered_path(roots.get("code"), machine.get("home"))
        vault_root = expand_registered_path(roots.get("vault"), machine.get("home"), optional=not vault["enabled"])
        if vault["enabled"] and vault_root is None:
            raise ConfigurationError(f"machine {machine_id!r} enables the Vault without a Vault root")
        code_path = PurePosixPath(str(code_root))
        vault_path = PurePosixPath(str(vault_root)) if vault_root else None
        if vault_path and (
            code_path == vault_path or code_path in vault_path.parents or vault_path in code_path.parents
        ):
            raise ConfigurationError(f"machine {machine_id!r} has overlapping Code and Vault roots")
        remote = vault.get("remote_access")
        if mode == "remote-sshfs":
            if (
                machine.get("platform") != "linux"
                or machine.get("role") != "worker"
                or machine.get("transport") != "ssh"
                or not isinstance(remote, dict)
                or set(remote) != {"source_machine_id", "writable"}
                or not isinstance(remote.get("source_machine_id"), str)
                or not remote["source_machine_id"]
                or not isinstance(remote.get("writable"), bool)
            ):
                raise ConfigurationError(f"machine {machine_id!r} has an invalid remote-sshfs policy")
        elif remote is not None and (
            mode not in {"primary-external-git", "icloud-gitless"}
            or not isinstance(remote, dict)
            or set(remote) != {"host_enabled"}
            or not isinstance(remote.get("host_enabled"), bool)
        ):
            raise ConfigurationError(f"machine {machine_id!r} has an invalid Vault host policy")
        if mode == "primary-external-git" and (
            machine.get("platform") != "macos" or machine.get("role") != "primary"
        ):
            raise ConfigurationError(f"machine {machine_id!r} cannot own Vault Git")
        if mode == "icloud-gitless" and (
            machine.get("platform") != "macos" or machine.get("role") != "worker"
        ):
            raise ConfigurationError(f"machine {machine_id!r} cannot use icloud-gitless mode")
        rendered = dict(machine)
        rendered["declared_roots"] = dict(roots)
        rendered["roots"] = {"code": code_root, "vault": vault_root}
        rendered["resolved_roots"] = {"code": code_root, "vault": vault_root}
        resolved[machine_id] = rendered
    if primary_id not in resolved or resolved[str(primary_id)].get("role") != "primary":
        raise ConfigurationError("primary_machine_id must select the registered primary")
    if sum(machine.get("role") == "primary" for machine in resolved.values()) != 1:
        raise ConfigurationError("machine registry must contain exactly one primary")
    vault_git = data.get("vault_git")
    vault_git_keys = {"owner_machine_id", "refresh_owner_machine_id", "remote", "branch"}
    if (
        not isinstance(vault_git, dict)
        or set(vault_git) != vault_git_keys
        or not all(isinstance(vault_git.get(field), str) and vault_git[field] for field in ("remote", "branch"))
    ):
        raise ConfigurationError("vault_git needs schema-v7 owner, refresh owner, remote, and branch")
    owners = [
        machine
        for machine in resolved.values()
        if machine.get("enabled") and machine["vault"]["checkout_mode"] == "primary-external-git"
    ]
    owner_id = vault_git.get("owner_machine_id")
    refresh_id = vault_git.get("refresh_owner_machine_id")
    if not owners:
        if owner_id is not None or refresh_id is not None:
            raise ConfigurationError("Vault-free registries need null Git and refresh owners")
    elif len(owners) != 1 or owner_id != owners[0]["id"] or refresh_id != owner_id:
        raise ConfigurationError("Vault Git owners must match the one enabled primary-external-git machine")
    for machine in resolved.values():
        if not machine.get("enabled") or machine["vault"]["checkout_mode"] != "remote-sshfs":
            continue
        source_id = machine["vault"]["remote_access"]["source_machine_id"]
        source = resolved.get(source_id)
        source_remote = source["vault"].get("remote_access") if source else None
        if (
            source_id == machine["id"]
            or source is None
            or not source.get("enabled")
            or source.get("platform") != "macos"
            or source.get("transport") != "ssh"
            or source["vault"]["checkout_mode"] not in {"primary-external-git", "icloud-gitless"}
            or not source["vault"]["enabled"]
            or not source["vault"]["required"]
            or not isinstance(source_remote, dict)
            or source_remote.get("host_enabled") is not True
            or not source.get("ssh_alias")
        ):
            raise ConfigurationError(f"remote Vault source for {machine['id']!r} is not an enabled iCloud SSH host")
        machine["remote_vault_source"] = {
            "id": source_id,
            "display_name": source.get("display_name"),
            "ssh_alias": source["ssh_alias"],
            "root": source["resolved_roots"]["vault"],
        }
    return resolved


def safe_workspace_path(value: object, workspace_id: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"workspace {workspace_id!r} needs a relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() in {"", "."} or ".." in path.parts or value.startswith("~"):
        raise ConfigurationError(f"workspace {workspace_id!r} path escapes the Code root: {value!r}")
    return path


def validate_workspaces(data: dict[str, Any], machines: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if data.get("schema_version") != 2 or not isinstance(data.get("entries"), dict):
        raise ConfigurationError("workspace registry needs schema_version 2 and entries")
    entries = data["entries"]
    resolved: dict[str, dict[str, Any]] = {}
    for workspace_id, raw in entries.items():
        if not isinstance(workspace_id, str) or not isinstance(raw, dict):
            raise ConfigurationError("workspace entries must be named objects")
        relative = safe_workspace_path(raw.get("path"), workspace_id)
        targets: dict[str, str] = {}
        for machine_id, machine in machines.items():
            if not machine.get("enabled"):
                continue
            targets[machine_id] = str(PurePosixPath(machine["resolved_roots"]["code"]).joinpath(*relative.parts))
        resolved[workspace_id] = {**raw, "path": relative.as_posix(), "resolved_paths": targets}
    for machine_id in [key for key, value in machines.items() if value.get("enabled")]:
        seen: dict[str, str] = {}
        for workspace_id, entry in resolved.items():
            target = entry["resolved_paths"][machine_id]
            previous = seen.get(target)
            if previous:
                raise ConfigurationError(f"workspaces {previous!r} and {workspace_id!r} resolve to the same target on {machine_id}")
            seen[target] = workspace_id
    return resolved


def load_instance(root: Path | None = None) -> dict[str, Any]:
    instance = active_instance_root(root)
    profile = read_json(instance / "profile.json", "agent profile")
    if profile.get("schema_version") != 1 or profile.get("github_transport") not in {"ssh", "https"}:
        raise ConfigurationError("agent profile needs schema_version 1 and a supported GitHub transport")
    machines_raw = read_json(instance / "fleet/machines.json", "machine registry")
    workspaces_raw = read_json(instance / "fleet/workspaces.json", "workspace registry")
    machines = validate_machines(machines_raw)
    workspaces = validate_workspaces(workspaces_raw, machines)
    sources = read_json(instance / "skills/skill-sources.json", "skill sources")
    if (
        sources.get("schema_version") != 4
        or not isinstance(sources.get("repos"), list)
        or not isinstance(sources.get("gh_skills", {}), dict)
    ):
        raise ConfigurationError("skill sources need schema_version 4, repos, and optional gh_skills")
    forbidden_source_keys = {"clone_root", "github_transport", "instruction_fragments", "workspace_projections"}
    if forbidden_source_keys & set(sources):
        raise ConfigurationError("skill sources contain retired derived or instruction fields")
    langfuse = read_json(instance / "integrations/langfuse.json", "Langfuse integration")
    if langfuse.get("schema_version") != 2 or not isinstance(langfuse.get("enabled"), bool):
        raise ConfigurationError("Langfuse integration needs schema_version 2 and enabled")
    if langfuse["enabled"] and (not isinstance(langfuse.get("base_url"), str) or not langfuse["base_url"].startswith("https://")):
        raise ConfigurationError("enabled Langfuse integration needs an HTTPS base_url")
    if not langfuse["enabled"] and langfuse.get("base_url") is not None:
        raise ConfigurationError("disabled Langfuse integration cannot retain an endpoint")
    return {
        "root": instance,
        "profile": profile,
        "fleet": {"machines": machines, "workspaces": workspaces},
        "skills": {"sources": sources},
        "integrations": {"langfuse": langfuse},
        "instructions": {"fragments": read_json(instance / "instructions/fragments.json", "instruction fragments")},
        "dependencies": {"selections": read_json(instance / "dependencies/selections.json", "dependency selections")},
    }


def resolve_dotted(data: object, dotted: str) -> object:
    current = data
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ConfigurationError(f"configuration key does not exist: {dotted}")
    return current
