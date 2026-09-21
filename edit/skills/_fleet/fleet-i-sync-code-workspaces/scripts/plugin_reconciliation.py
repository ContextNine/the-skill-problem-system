#!/usr/bin/env python3
"""Reconcile primary-installed Codex plugins without copying host-local caches or auth."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import platform as host_platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Any


STATE_RELATIVE = Path("Code/.workspace-sync/plugin-state.json")
LEGACY_STATE_RELATIVE = Path("Code/.ctx9/workspace-bootstrap/plugin-state.json")
MARKETPLACE_MANIFEST = Path(".agents/plugins/marketplace.json")
TOML_TABLE_HEADER = re.compile(r"^\s*(\[{1,2})(.+?)(\]{1,2})\s*(?:#.*)?$")
INSTALL_FAILURE = "installation-failed"


class PluginReconciliationError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def output(process: subprocess.CompletedProcess[str]) -> str:
    return process.stdout.strip()


def error_text(process: subprocess.CompletedProcess[str]) -> str:
    value = (process.stderr or process.stdout).strip()
    return value.splitlines()[-1][:500] if value else "command failed"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def command_json(command: list[str]) -> dict[str, Any]:
    process = run(command)
    if process.returncode != 0:
        raise PluginReconciliationError(f"{' '.join(command[:4])} failed: {error_text(process)}")
    try:
        value = json.loads(output(process))
    except json.JSONDecodeError as exc:
        raise PluginReconciliationError(f"{' '.join(command[:4])} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise PluginReconciliationError(f"{' '.join(command[:4])} did not return a JSON object")
    return value


def codex_command() -> str:
    command = shutil.which("codex")
    if not command:
        raise PluginReconciliationError("Codex CLI is not available on PATH")
    return command


def git_head(path: Path) -> str | None:
    process = run(["git", "-C", str(path), "rev-parse", "HEAD"])
    value = output(process)
    return value if process.returncode == 0 and re.fullmatch(r"[0-9a-fA-F]{40}", value) else None


def git_root(path: Path) -> Path | None:
    process = run(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    return Path(output(process)).resolve() if process.returncode == 0 and output(process) else None


def validate_marketplace_root(path: Path) -> None:
    manifest = path / MARKETPLACE_MANIFEST
    if not path.is_dir() or not manifest.is_file():
        raise PluginReconciliationError(f"marketplace manifest is missing: {manifest}")
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginReconciliationError(f"marketplace manifest is invalid: {manifest}: {exc}") from exc
    if not isinstance(value, dict):
        raise PluginReconciliationError(f"marketplace manifest is not a JSON object: {manifest}")


def runtime_marketplace(name: str, source: dict[str, object] | None, source_home: Path) -> bool:
    if name.startswith("openai-") or source is None:
        return True
    raw = source.get("source") if isinstance(source, dict) else None
    if not isinstance(raw, str):
        return False
    path = Path(raw).expanduser()
    runtime_roots = (
        source_home / ".cache/codex-runtimes",
        source_home / ".codex/.tmp/bundled-marketplaces",
        source_home / ".codex/.tmp/plugins",
    )
    resolved = path.resolve()
    return any(root.resolve() == resolved or root.resolve() in resolved.parents for root in runtime_roots)


def marketplace_source(record: dict[str, object], marketplace: dict[str, object] | None) -> dict[str, object] | None:
    direct = record.get("marketplaceSource")
    if isinstance(direct, dict):
        return direct
    fallback = marketplace.get("marketplaceSource") if isinstance(marketplace, dict) else None
    return fallback if isinstance(fallback, dict) else None


def build_desired_inventory(source_home: Path, source_code_root: Path) -> dict[str, object]:
    """Read installed primary plugins and normalize only portable source facts."""
    command = codex_command()
    version = run([command, "--version"])
    if version.returncode != 0 or not output(version):
        raise PluginReconciliationError(f"cannot determine Codex CLI version: {error_text(version)}")
    marketplace_value = command_json([command, "plugin", "marketplace", "list", "--json"])
    plugin_value = command_json([command, "plugin", "list", "--json"])
    marketplaces = marketplace_value.get("marketplaces")
    installed = plugin_value.get("installed")
    if not isinstance(marketplaces, list) or not isinstance(installed, list):
        raise PluginReconciliationError("Codex plugin JSON is missing marketplaces or installed plugins")
    marketplace_by_name = {
        str(item["name"]): item
        for item in marketplaces
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    normalized: list[dict[str, object]] = []
    source_code_root = source_code_root.expanduser().resolve()
    for raw in installed:
        if not isinstance(raw, dict):
            raise PluginReconciliationError("Codex installed plugin entry is not an object")
        plugin_id = raw.get("pluginId")
        name = raw.get("name")
        marketplace_name = raw.get("marketplaceName")
        version_value = raw.get("version")
        if not all(isinstance(value, str) and value for value in (plugin_id, name, marketplace_name, version_value)):
            raise PluginReconciliationError("Codex installed plugin entry lacks portable identity fields")
        marketplace = marketplace_by_name.get(marketplace_name)
        source = marketplace_source(raw, marketplace)
        plugin: dict[str, object] = {
            "plugin_id": plugin_id,
            "name": name,
            "marketplace": marketplace_name,
            "version": version_value,
            "enabled": bool(raw.get("enabled")),
            "authentication_policy": str(raw.get("authPolicy") or "UNKNOWN"),
        }
        if runtime_marketplace(marketplace_name, source, source_home):
            plugin["source_type"] = "runtime"
        elif source and source.get("sourceType") == "git" and isinstance(source.get("source"), str):
            root_value = marketplace.get("root") if isinstance(marketplace, dict) else None
            if not isinstance(root_value, str):
                raise PluginReconciliationError(f"Git marketplace {marketplace_name} has no local snapshot root")
            root = Path(root_value).expanduser().resolve()
            validate_marketplace_root(root)
            revision = git_head(root)
            if not revision:
                raise PluginReconciliationError(f"Git marketplace {marketplace_name} has no resolved revision")
            plugin.update({"source_type": "git", "source": source["source"], "revision": revision})
        elif source and source.get("sourceType") == "local" and isinstance(source.get("source"), str):
            marketplace_root = Path(str(source["source"])).expanduser().resolve()
            repository_root = git_root(marketplace_root)
            if repository_root is None:
                raise PluginReconciliationError(
                    f"unsupported local marketplace {marketplace_name}: source is not a registered Git repository"
                )
            try:
                repository_relative = repository_root.relative_to(source_code_root)
                marketplace_relative = marketplace_root.relative_to(repository_root)
            except ValueError as exc:
                raise PluginReconciliationError(
                    f"unsupported local marketplace {marketplace_name}: source is outside the primary Code root"
                ) from exc
            validate_marketplace_root(marketplace_root)
            revision = git_head(repository_root)
            if not revision:
                raise PluginReconciliationError(f"local marketplace {marketplace_name} has no Git revision")
            plugin.update(
                {
                    "source_type": "local-repository",
                    "repository_relative_path": repository_relative.as_posix(),
                    "marketplace_subpath": marketplace_relative.as_posix(),
                    "revision": revision,
                }
            )
        else:
            raise PluginReconciliationError(f"unsupported marketplace source for {plugin_id}")
        normalized.append(plugin)
    return {
        "schema_version": 1,
        "source_cli_version": output(version),
        "generated_at": utc_now(),
        "plugins": sorted(normalized, key=lambda item: str(item["plugin_id"])),
    }


def validate_inventory(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise PluginReconciliationError("plugin inventory needs schema_version 1")
    plugins = value.get("plugins")
    if not isinstance(plugins, list):
        raise PluginReconciliationError("plugin inventory has no plugins list")
    seen: set[str] = set()
    marketplace_sources: dict[str, tuple[object, ...]] = {}
    for plugin in plugins:
        if not isinstance(plugin, dict):
            raise PluginReconciliationError("plugin inventory entry is not an object")
        required = {"plugin_id", "name", "marketplace", "version", "enabled", "source_type", "authentication_policy"}
        missing = sorted(required - set(plugin))
        if missing:
            raise PluginReconciliationError(f"plugin inventory entry is missing: {', '.join(missing)}")
        plugin_id = str(plugin["plugin_id"])
        if plugin_id in seen:
            raise PluginReconciliationError(f"duplicate desired plugin: {plugin_id}")
        seen.add(plugin_id)
        source_type = plugin["source_type"]
        if source_type == "git":
            identity = (source_type, plugin.get("source"), plugin.get("revision"))
        elif source_type == "local-repository":
            relative = PurePosixPath(str(plugin.get("repository_relative_path") or ""))
            subpath = PurePosixPath(str(plugin.get("marketplace_subpath") or "."))
            if relative.is_absolute() or not relative.parts or ".." in relative.parts or subpath.is_absolute() or ".." in subpath.parts:
                raise PluginReconciliationError(f"plugin {plugin_id} has an unsafe local repository path")
            identity = (source_type, relative.as_posix(), subpath.as_posix(), plugin.get("revision"))
        elif source_type == "runtime":
            identity = (source_type,)
        else:
            raise PluginReconciliationError(f"plugin {plugin_id} has unsupported source_type {source_type!r}")
        marketplace = str(plugin["marketplace"])
        prior = marketplace_sources.setdefault(marketplace, identity)
        if prior != identity:
            raise PluginReconciliationError(f"desired marketplace {marketplace} has conflicting sources")
    return value


def desired_marketplaces(inventory: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for plugin in inventory["plugins"]:
        if plugin["source_type"] == "runtime":
            continue
        result.setdefault(str(plugin["marketplace"]), plugin)
    return result


def read_marketplaces(command: str) -> dict[str, dict[str, object]]:
    marketplaces = command_json([command, "plugin", "marketplace", "list", "--json"]).get("marketplaces")
    if not isinstance(marketplaces, list):
        raise PluginReconciliationError("target Codex marketplace JSON has an unexpected schema")
    return {
        str(item["name"]): item
        for item in marketplaces
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def configured_marketplaces(home: Path) -> dict[str, dict[str, object]]:
    """Inspect registration metadata even when Codex cannot load a broken snapshot."""
    config_path = home / ".codex/config.toml"
    text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    result: dict[str, dict[str, object]] = {}
    for table, lines in split_toml_sections(text):
        if not table or not table.startswith("marketplaces."):
            continue
        raw_name = table.removeprefix("marketplaces.")
        try:
            name_value = json.loads(raw_name) if raw_name.startswith('"') else raw_name
        except json.JSONDecodeError:
            continue
        if not isinstance(name_value, str) or not name_value:
            continue
        values: dict[str, str] = {}
        for line in lines[1:]:
            key, separator, raw_value = line.partition("=")
            if not separator:
                continue
            key = key.strip()
            raw_value = raw_value.strip()
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, str):
                values[key] = parsed
        source_type = values.get("source_type")
        source = values.get("source")
        if source_type not in {"git", "local"} or not source:
            continue
        root = (
            home / ".codex/.tmp/marketplaces" / name_value
            if source_type == "git"
            else Path(source).expanduser()
        )
        result[name_value] = {
            "name": name_value,
            "root": str(root),
            "marketplaceSource": {"sourceType": source_type, "source": source},
            "configuredRevision": values.get("last_revision"),
        }
    return result


def inspect_marketplaces(command: str, home: Path) -> tuple[dict[str, dict[str, object]], str | None]:
    try:
        return read_marketplaces(command), None
    except PluginReconciliationError as exc:
        configured = configured_marketplaces(home)
        if not configured:
            raise
        return configured, str(exc)


def read_plugins(command: str) -> dict[str, dict[str, object]]:
    plugins = command_json([command, "plugin", "list", "--json"]).get("installed")
    if not isinstance(plugins, list):
        raise PluginReconciliationError("target Codex plugin JSON has an unexpected schema")
    return {
        str(item["pluginId"]): item
        for item in plugins
        if isinstance(item, dict) and isinstance(item.get("pluginId"), str)
    }


def available_plugin_ids(marketplaces: dict[str, dict[str, object]]) -> set[str]:
    """Return plugin IDs actually published by this target's marketplace snapshots."""
    available: set[str] = set()
    for marketplace_name, marketplace in marketplaces.items():
        root_value = marketplace.get("root")
        if not isinstance(root_value, str):
            continue
        manifest = Path(root_value).expanduser() / MARKETPLACE_MANIFEST
        try:
            value = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries = value.get("plugins") if isinstance(value, dict) else None
        if not isinstance(entries, list):
            continue
        for entry in entries:
            name = entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str) and name:
                available.add(f"{name}@{marketplace_name}")
    return available


def current_codex_state(command: str) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    return read_marketplaces(command), read_plugins(command)


def target_local_marketplace(home: Path, desired: dict[str, object]) -> Path:
    repository = PurePosixPath(str(desired["repository_relative_path"]))
    subpath = PurePosixPath(str(desired.get("marketplace_subpath") or "."))
    return home.joinpath("Code", *repository.parts, *(() if subpath.as_posix() == "." else subpath.parts))


def marketplace_health(
    name: str,
    desired: dict[str, object],
    current: dict[str, dict[str, object]],
    home: Path,
) -> tuple[bool, str]:
    record = current.get(name)
    if not record:
        return False, "marketplace is not registered"
    root_value = record.get("root")
    if not isinstance(root_value, str):
        return False, "marketplace has no snapshot root"
    root = Path(root_value).expanduser()
    source = record.get("marketplaceSource")
    source = source if isinstance(source, dict) else {}
    if desired["source_type"] == "git":
        if source.get("sourceType") != "git" or source.get("source") != desired.get("source"):
            return False, "marketplace Git source differs"
        expected_root = root
    else:
        expected_root = target_local_marketplace(home, desired)
        if source.get("sourceType") != "local" or Path(str(source.get("source") or "")).expanduser() != expected_root:
            return False, "marketplace local source differs"
    try:
        validate_marketplace_root(expected_root)
    except PluginReconciliationError as exc:
        return False, str(exc)
    revision_root = git_root(expected_root) or expected_root
    if git_head(revision_root) != desired.get("revision"):
        return False, "marketplace revision differs"
    return True, "marketplace source, manifest, and revision match"


def git_marketplace_access(source: str) -> tuple[bool, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_ASKPASS": "/usr/bin/false",
            "SSH_ASKPASS_REQUIRE": "never",
            "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=10",
        }
    )
    process = run(["git", "ls-remote", source], env=environment)
    return (True, "Git marketplace is reachable") if process.returncode == 0 else (
        False,
        f"Git marketplace is unreachable: {error_text(process)}",
    )


def preflight(
    inventory: dict[str, object],
    home: Path,
    planned_repositories: set[str],
) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    try:
        command = codex_command()
        version = run([command, "--version"])
        if version.returncode != 0:
            raise PluginReconciliationError(f"Codex CLI version check failed: {error_text(version)}")
        current, marketplace_error = inspect_marketplaces(command, home)
        try:
            read_plugins(command)
            plugin_cache_detail = "plugin inventory is readable"
        except PluginReconciliationError as exc:
            repairable = any(
                not marketplace_health(name, desired, current, home)[0]
                for name, desired in desired_marketplaces(inventory).items()
            )
            if not repairable:
                raise
            plugin_cache_detail = f"plugin inventory is unreadable until the desired marketplace is repaired: {exc}"
        checks.append({"kind": "codex", "status": "ready", "detail": output(version)})
        if marketplace_error:
            checks.append(
                {
                    "kind": "marketplace-cache",
                    "status": "ready",
                    "detail": f"CLI marketplace inspection is blocked; config metadata is sufficient for repair: {marketplace_error}",
                }
            )
        checks.append({"kind": "plugin-cache", "status": "ready", "detail": plugin_cache_detail})
        for name, desired in desired_marketplaces(inventory).items():
            if desired["source_type"] == "git":
                reachable, detail = git_marketplace_access(str(desired["source"]))
                checks.append({"kind": "marketplace", "marketplace": name, "status": "ready" if reachable else "blocked", "detail": detail})
            else:
                relative = str(desired["repository_relative_path"])
                target = target_local_marketplace(home, desired)
                available_after_sync = relative in planned_repositories
                if not target.exists() and not available_after_sync:
                    checks.append(
                        {
                            "kind": "marketplace",
                            "marketplace": name,
                            "status": "blocked",
                            "detail": f"target-local marketplace repository is absent and not selected for sync: {relative}",
                        }
                    )
                else:
                    checks.append(
                        {
                            "kind": "marketplace",
                            "marketplace": name,
                            "status": "ready",
                            "detail": f"target-local marketplace will use Code/{relative}",
                        }
                    )
    except PluginReconciliationError as exc:
        checks.append({"kind": "codex", "status": "blocked", "detail": str(exc)})
    return {"ok": all(check["status"] == "ready" for check in checks), "checks": checks}


def run_json_action(command: list[str]) -> None:
    command_json(command)


def replace_marketplace(command: str, name: str, desired: dict[str, object], home: Path, current: dict[str, dict[str, object]]) -> None:
    if desired["source_type"] == "git":
        source = str(desired["source"])
        revision = str(desired["revision"])
        with tempfile.TemporaryDirectory(prefix=f"codex-marketplace-{name}-") as temporary:
            checkout = Path(temporary) / "checkout"
            cloned = run(["git", "clone", "--filter=blob:none", "--no-checkout", source, str(checkout)])
            if cloned.returncode != 0:
                raise PluginReconciliationError(f"cannot download marketplace {name}: {error_text(cloned)}")
            if run(["git", "-C", str(checkout), "cat-file", "-e", f"{revision}^{{commit}}"]).returncode != 0:
                fetched = run(["git", "-C", str(checkout), "fetch", "origin", revision])
                if fetched.returncode != 0:
                    raise PluginReconciliationError(f"cannot fetch marketplace revision {revision}: {error_text(fetched)}")
            checked_out = run(["git", "-C", str(checkout), "checkout", "--detach", revision])
            if checked_out.returncode != 0:
                raise PluginReconciliationError(f"cannot check out marketplace revision {revision}: {error_text(checked_out)}")
            validate_marketplace_root(checkout)
        add_command = [command, "plugin", "marketplace", "add", source, "--ref", revision, "--json"]
    else:
        target = target_local_marketplace(home, desired)
        validate_marketplace_root(target)
        revision_root = git_root(target) or target
        if git_head(revision_root) != desired.get("revision"):
            raise PluginReconciliationError(f"target-local marketplace {name} is not at desired revision")
        add_command = [command, "plugin", "marketplace", "add", str(target), "--json"]
    if name in current:
        try:
            run_json_action([command, "plugin", "marketplace", "remove", name, "--json"])
        except PluginReconciliationError:
            remove_toml_table(home / ".codex/config.toml", f"marketplaces.{name}")
    run_json_action(add_command)
    refreshed = read_marketplaces(command)
    healthy, detail = marketplace_health(name, desired, refreshed, home)
    if not healthy:
        raise PluginReconciliationError(f"marketplace {name} failed verification: {detail}")


def split_toml_sections(text: str) -> list[tuple[str | None, list[str]]]:
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.splitlines():
        match = TOML_TABLE_HEADER.match(line)
        if match and len(match.group(1)) == len(match.group(3)):
            sections.append((match.group(2).strip(), [line]))
        else:
            sections[-1][1].append(line)
    return sections


def remove_toml_table(config_path: Path, table_prefix: str) -> None:
    text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    rendered = [
        line
        for name, lines in split_toml_sections(text)
        if not (name == table_prefix or (name and name.startswith(f"{table_prefix}.")))
        for line in lines
    ]
    if config_path.is_file():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = config_path.with_name(f"{config_path.name}.backup-plugin-{stamp}-{os.getpid()}")
        shutil.copy2(config_path, backup)
    atomic_write(config_path, "\n".join(rendered).rstrip() + "\n")


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def set_plugin_enabled(config_path: Path, plugin_id: str, enabled: bool) -> None:
    text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    table_name = f"plugins.{json.dumps(plugin_id)}"
    sections = split_toml_sections(text)
    found = False
    rendered: list[str] = []
    for name, lines in sections:
        if name != table_name:
            rendered.extend(lines)
            continue
        found = True
        replaced = False
        for line in lines:
            if re.match(r"^\s*enabled\s*=", line):
                if not replaced:
                    rendered.append(f"enabled = {'true' if enabled else 'false'}")
                    replaced = True
            else:
                rendered.append(line)
        if not replaced:
            rendered.append(f"enabled = {'true' if enabled else 'false'}")
    if not found:
        if rendered and rendered[-1] != "":
            rendered.append("")
        rendered.extend([f"[{table_name}]", f"enabled = {'true' if enabled else 'false'}"])
    atomic_write(config_path, "\n".join(rendered).rstrip() + "\n")


def runtime_state_path(home: Path, *, migrate: bool) -> Path:
    state_root = (home / STATE_RELATIVE).parent
    legacy_root = (home / LEGACY_STATE_RELATIVE).parent
    for label, path in (("plugin state", state_root), ("legacy plugin state", legacy_root)):
        if path.is_symlink():
            raise PluginReconciliationError(f"{label} cannot be a symlink: {path}")
        if path.exists() and not path.is_dir():
            raise PluginReconciliationError(f"{label} is not a directory: {path}")
    if state_root.exists() and legacy_root.exists():
        raise PluginReconciliationError(
            f"both workspace sync state directories exist; resolve without merging: {legacy_root}, {state_root}"
        )
    if migrate and legacy_root.exists():
        legacy_root.rename(state_root)
        try:
            legacy_root.parent.rmdir()
        except OSError:
            pass
    if migrate and state_root.exists():
        state_root.chmod(0o700)
    if not migrate and legacy_root.exists():
        return legacy_root / "plugin-state.json"
    return state_root / "plugin-state.json"


def load_state(home: Path, *, migrate: bool = False) -> dict[str, object]:
    path = runtime_state_path(home, migrate=migrate)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema_version": 1, "managed_plugins": {}, "managed_marketplaces": {}}
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginReconciliationError(f"plugin ownership state is invalid: {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise PluginReconciliationError(f"plugin ownership state has an unsupported schema: {path}")
    return value


def write_state(home: Path, inventory: dict[str, object], installed: dict[str, dict[str, object]]) -> None:
    verified_at = utc_now()
    managed_plugins = {
        str(plugin["plugin_id"]): {
            "marketplace": plugin["marketplace"],
            "desired_revision": plugin.get("revision"),
            "installed_revision": plugin.get("revision"),
            "version": installed[str(plugin["plugin_id"])].get("version"),
            "last_successful_verification": verified_at,
        }
        for plugin in inventory["plugins"]
        if str(plugin["plugin_id"]) in installed
    }
    managed_marketplaces = {
        name: {"source_type": desired["source_type"], "revision": desired.get("revision")}
        for name, desired in desired_marketplaces(inventory).items()
    }
    path = runtime_state_path(home, migrate=True)
    atomic_write(
        path,
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": verified_at,
                "managed_plugins": managed_plugins,
                "managed_marketplaces": managed_marketplaces,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    path.parent.chmod(0o700)
    path.chmod(0o600)


def paper_status(platform_name: str) -> tuple[str, str]:
    architecture = host_platform.machine().lower()
    if platform_name == "macos" and architecture in {"x86_64", "amd64"}:
        return "unsupported-platform", "Paper Desktop has no supported macOS Intel build"
    try:
        with socket.create_connection(("127.0.0.1", 29979), timeout=0.25):
            return "installed-and-ready", "Paper Desktop MCP is listening on 127.0.0.1:29979"
    except OSError:
        return "installed-runtime-unavailable", "plugin is installed; Paper Desktop must be logged in with a file open"


def readiness(plugin: dict[str, object], platform_name: str) -> tuple[str, str]:
    if plugin["plugin_id"] == "paper-desktop@paper":
        return paper_status(platform_name)
    policy = str(plugin.get("authentication_policy") or "UNKNOWN")
    if policy not in {"NONE", "NOT_REQUIRED"}:
        return "installed-authentication-required", f"authentication remains machine-local ({policy})"
    return "installed-and-ready", "plugin is installed and enabled state matches"


def reconcile(payload: dict[str, object]) -> dict[str, object]:
    inventory = validate_inventory(payload.get("inventory"))
    home = Path(str(payload.get("home") or "")).expanduser().resolve()
    if home != Path.home().resolve():
        raise PluginReconciliationError(f"target home mismatch: expected {home}, process home is {Path.home()}")
    platform_name = str(payload.get("platform") or "")
    if platform_name not in {"macos", "linux"}:
        raise PluginReconciliationError(f"unsupported target platform: {platform_name}")
    planned = payload.get("planned_repositories")
    planned_repositories = {str(value) for value in planned} if isinstance(planned, list) else set()
    preflight_report = preflight(inventory, home, planned_repositories)
    if bool(payload.get("preflight_only")) or not preflight_report["ok"]:
        return {
            "ok": bool(preflight_report["ok"]),
            "ready": bool(preflight_report["ok"]),
            "applied": False,
            "mode": "preflight",
            "preflight": preflight_report,
            "marketplaces": [],
            "plugins": [],
        }
    command = codex_command()
    apply = bool(payload.get("apply"))
    current_marketplaces, _ = inspect_marketplaces(command, home)
    installed: dict[str, dict[str, object]] = {}
    ownership = load_state(home, migrate=apply)
    marketplace_results: list[dict[str, object]] = []
    plugin_results: list[dict[str, object]] = []
    fatal = False

    for name, desired in desired_marketplaces(inventory).items():
        healthy, detail = marketplace_health(name, desired, current_marketplaces, home)
        if healthy:
            marketplace_results.append({"marketplace": name, "status": "match", "detail": detail})
            continue
        if not apply:
            marketplace_results.append({"marketplace": name, "status": "planned-repair", "detail": detail})
            continue
        try:
            replace_marketplace(command, name, desired, home, current_marketplaces)
            marketplace_results.append({"marketplace": name, "status": "repaired", "detail": "validated replacement installed"})
            current_marketplaces = read_marketplaces(command)
        except PluginReconciliationError as exc:
            fatal = True
            marketplace_results.append({"marketplace": name, "status": INSTALL_FAILURE, "detail": str(exc)})

    try:
        installed = read_plugins(command)
    except PluginReconciliationError as exc:
        if not apply and any(result["status"] == "planned-repair" for result in marketplace_results):
            return {
                "ok": True,
                "ready": False,
                "applied": False,
                "mode": "preview",
                "preflight": preflight_report,
                "marketplaces": marketplace_results,
                "plugins": [
                    {
                        "plugin_id": str(plugin["plugin_id"]),
                        "status": (
                            "planned-reinstall"
                            if any(
                                result["marketplace"] == plugin["marketplace"]
                                and result["status"] == "planned-repair"
                                for result in marketplace_results
                            )
                            else "planned-verify"
                        ),
                        "detail": "plugin inventory will be verified after marketplace repair",
                    }
                    for plugin in inventory["plugins"]
                ],
                "state_path": str(runtime_state_path(home, migrate=False)),
            }
        return {
            "ok": False,
            "ready": False,
            "applied": False,
            "mode": "apply" if apply else "preview",
            "preflight": preflight_report,
            "marketplaces": marketplace_results,
            "plugins": [],
            "error": f"plugin inventory remains unreadable after marketplace reconciliation: {exc}",
        }

    desired_by_id = {str(plugin["plugin_id"]): plugin for plugin in inventory["plugins"]}
    target_available_plugins = available_plugin_ids(current_marketplaces)
    managed_before = ownership.get("managed_plugins")
    managed_before = managed_before if isinstance(managed_before, dict) else {}
    for plugin_id in sorted(set(managed_before) - set(desired_by_id)):
        if plugin_id not in installed:
            plugin_results.append({"plugin_id": plugin_id, "status": "removed", "detail": "previously managed plugin is already absent"})
            continue
        if not apply:
            plugin_results.append({"plugin_id": plugin_id, "status": "planned-remove", "detail": "removed from primary desired state"})
            continue
        try:
            run_json_action([command, "plugin", "remove", plugin_id, "--json"])
            plugin_results.append({"plugin_id": plugin_id, "status": "removed", "detail": "removed from primary desired state"})
            _, installed = current_codex_state(command)
        except PluginReconciliationError as exc:
            fatal = True
            plugin_results.append({"plugin_id": plugin_id, "status": INSTALL_FAILURE, "detail": str(exc)})

    for plugin_id, desired in desired_by_id.items():
        current = installed.get(plugin_id)
        source_ready = desired["source_type"] == "runtime" or any(
            result["marketplace"] == desired["marketplace"] and result["status"] in {"match", "repaired"}
            for result in marketplace_results
        )
        marketplace_repaired = any(
            result["marketplace"] == desired["marketplace"] and result["status"] == "repaired"
            for result in marketplace_results
        )
        matches = not marketplace_repaired and bool(
            current
            and current.get("version") == desired["version"]
            and bool(current.get("enabled")) == bool(desired["enabled"])
        )
        requires_install = bool(
            current is None
            or current.get("version") != desired["version"]
            or marketplace_repaired
        )
        if (
            desired["source_type"] == "runtime"
            and requires_install
            and plugin_id not in target_available_plugins
        ):
            preserved = "; existing installation was preserved" if current else ""
            plugin_results.append(
                {
                    "plugin_id": plugin_id,
                    "status": "unsupported-platform",
                    "detail": (
                        f"plugin is not published by target runtime marketplace "
                        f"{desired['marketplace']}{preserved}"
                    ),
                }
            )
            continue
        if not source_ready:
            fatal = True
            plugin_results.append({"plugin_id": plugin_id, "status": INSTALL_FAILURE, "detail": "marketplace source is unavailable"})
            continue
        if not matches and not apply:
            action = "planned-install" if current is None else "planned-update"
            plugin_results.append({"plugin_id": plugin_id, "status": action, "detail": "installed version or enabled state differs"})
            continue
        if not matches and apply:
            try:
                if current and (current.get("version") != desired["version"] or marketplace_repaired):
                    run_json_action([command, "plugin", "remove", plugin_id, "--json"])
                if current is None or current.get("version") != desired["version"] or marketplace_repaired:
                    run_json_action([command, "plugin", "add", plugin_id, "--json"])
                set_plugin_enabled(home / ".codex/config.toml", plugin_id, bool(desired["enabled"]))
                current_marketplaces, installed = current_codex_state(command)
                current = installed.get(plugin_id)
                if not current or current.get("version") != desired["version"] or bool(current.get("enabled")) != bool(desired["enabled"]):
                    raise PluginReconciliationError("post-install JSON verification differs from desired state")
            except PluginReconciliationError as exc:
                fatal = True
                plugin_results.append({"plugin_id": plugin_id, "status": INSTALL_FAILURE, "detail": str(exc)})
                continue
        status, detail = readiness(desired, platform_name)
        plugin_results.append({"plugin_id": plugin_id, "status": status, "detail": detail})

    managed_marketplaces = ownership.get("managed_marketplaces")
    managed_marketplaces = managed_marketplaces if isinstance(managed_marketplaces, dict) else {}
    desired_marketplace_names = set(desired_marketplaces(inventory))
    if apply and not fatal:
        current_marketplaces, installed = current_codex_state(command)
        for name in sorted(set(managed_marketplaces) - desired_marketplace_names):
            in_use = any(plugin.get("marketplaceName") == name for plugin in installed.values())
            if in_use:
                marketplace_results.append({"marketplace": name, "status": "preserved", "detail": "target-local plugin still uses marketplace"})
            elif name in current_marketplaces:
                try:
                    run_json_action([command, "plugin", "marketplace", "remove", name, "--json"])
                    marketplace_results.append({"marketplace": name, "status": "removed", "detail": "no installed plugin uses marketplace"})
                except PluginReconciliationError as exc:
                    fatal = True
                    marketplace_results.append({"marketplace": name, "status": INSTALL_FAILURE, "detail": str(exc)})
        if not fatal:
            _, installed = current_codex_state(command)
            write_state(home, inventory, installed)

    changes_pending = any(
        result["status"].startswith("planned-")
        for result in [*marketplace_results, *plugin_results]
    )
    ready = not fatal and not changes_pending and all(
        result["status"] == "installed-and-ready"
        for result in plugin_results
        if result["plugin_id"] in desired_by_id
    )
    return {
        "ok": not fatal,
        "ready": ready,
        "applied": apply and not fatal,
        "mode": "apply" if apply else "preview",
        "preflight": preflight_report,
        "marketplaces": marketplace_results,
        "plugins": plugin_results,
        "state_path": str(runtime_state_path(home, migrate=False)),
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise PluginReconciliationError("plugin reconciliation payload must be an object")
        json.dump(reconcile(payload), sys.stdout)
        sys.stdout.write("\n")
        return 0
    except (OSError, PluginReconciliationError, TypeError, ValueError) as exc:
        json.dump({"ok": False, "ready": False, "applied": False, "error": str(exc)[:1000]}, sys.stdout)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
