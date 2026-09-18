#!/usr/bin/env python3
"""Provision and operate registered full-Vault SSHFS access.

The same reviewed file is used as the primary-side controller, the Linux client,
and the macOS iCloud host helper. Configuration contains topology; this file does
not contain machine names, homes, aliases, or Vault paths.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable
import uuid


MANAGED_MARKER = "ctx9-vault-access.managed"
CLIENT_CONFIG = Path.home() / ".config/vault/remote-access.json"
HOST_CONFIG = Path.home() / ".config/vault/remote-access-host.json"
MACHINE_ID = Path.home() / ".config/vault/machine-id"
INSTALL_ROOT = Path.home() / ".local/share/vault-access"
INSTALLED_SCRIPT = INSTALL_ROOT / "remote_vault_access.py"
LAUNCHER = Path.home() / ".local/bin/vault"
SYSTEMD_UNIT = Path.home() / ".config/systemd/user/vault-remote.service"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class AccessError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AccessError(f"{label} missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AccessError(f"{label} invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise AccessError(f"{label} must be an object: {path}")
    return value


def atomic_write(path: Path, value: object, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run(command: list[str], *, timeout: float = 30, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise AccessError(f"command failed ({shlex.join(command)}): {detail}")
    return result


def ssh_command(alias: str, remote_argv: list[str], *, timeout: float = 30, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            alias,
            shlex.join(remote_argv),
        ],
        timeout=timeout,
        check=check,
    )


def expand_root(home: str, value: object) -> str:
    if not isinstance(value, str) or not value or "$" in value:
        raise AccessError(f"unsafe registered root: {value!r}")
    if value == "~":
        path = PurePosixPath(home)
    elif value.startswith("~/"):
        path = PurePosixPath(home).joinpath(*PurePosixPath(value[2:]).parts)
    else:
        path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        raise AccessError(f"unsafe registered root: {value!r}")
    return path.as_posix()


def find_registry() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "_system/agents/edit/settings/fleet/machines.json"
        if candidate.is_file():
            return candidate
    installed = Path.home() / ".agents/settings/fleet/machines.json"
    if installed.is_file():
        return installed
    raise AccessError("machine registry not found; pass --registry")


def load_registry(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    registry = read_json(path, "machine registry")
    if registry.get("schema_version") != 7:
        raise AccessError("remote Vault access requires machine registry schema_version 7")
    raw_machines = registry.get("machines")
    if not isinstance(raw_machines, list):
        raise AccessError("machine registry has no machines")
    machines = {
        str(machine.get("id")): machine
        for machine in raw_machines
        if isinstance(machine, dict) and isinstance(machine.get("id"), str)
    }
    return registry, machines


def remote_client_topology(
    registry: dict[str, Any], machines: dict[str, dict[str, Any]], machine_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    client = machines.get(machine_id)
    if not client or not client.get("enabled"):
        raise AccessError(f"remote Vault client is missing or disabled: {machine_id}")
    vault = client.get("vault")
    if (
        client.get("platform") != "linux"
        or client.get("transport") != "ssh"
        or not isinstance(vault, dict)
        or vault.get("checkout_mode") != "remote-sshfs"
        or not vault.get("enabled")
    ):
        raise AccessError(f"machine is not a registered remote-sshfs client: {machine_id}")
    remote = vault.get("remote_access")
    source_id = remote.get("source_machine_id") if isinstance(remote, dict) else None
    source = machines.get(str(source_id))
    source_vault = source.get("vault") if source else None
    source_remote = source_vault.get("remote_access") if isinstance(source_vault, dict) else None
    if (
        not source
        or not source.get("enabled")
        or source.get("platform") != "macos"
        or source.get("transport") != "ssh"
        or not source.get("ssh_alias")
        or not isinstance(source_vault, dict)
        or source_vault.get("checkout_mode") not in {"primary-external-git", "icloud-gitless"}
        or not source_vault.get("enabled")
        or not isinstance(source_remote, dict)
        or source_remote.get("host_enabled") is not True
    ):
        raise AccessError(f"remote Vault source is not an enabled iCloud host: {source_id}")
    vault_git = registry.get("vault_git")
    if not isinstance(vault_git, dict) or not vault_git.get("owner_machine_id"):
        raise AccessError("registry has no Vault Git owner")
    return client, source


def fileprovider_evaluate(path: Path) -> dict[str, Any]:
    result = run(["/usr/bin/fileproviderctl", "evaluate", str(path)], timeout=60)
    output = result.stdout + result.stderr
    fields: dict[str, bool] = {}
    for name in (
        "hasUnresolvedConflicts",
        "isDownloaded",
        "isDownloading",
        "isExcludedFromSync",
        "isKeepDownloaded",
        "isMostRecentVersionDownloaded",
        "isRecursivelyDownloaded",
        "isSyncPaused",
        "isUploaded",
        "isUploading",
    ):
        match = re.search(rf"\b{name}\s*=\s*([01]);", output)
        if match:
            fields[name] = match.group(1) == "1"
    required = {
        "hasUnresolvedConflicts",
        "isDownloaded",
        "isDownloading",
        "isExcludedFromSync",
        "isMostRecentVersionDownloaded",
        "isSyncPaused",
        "isUploaded",
        "isUploading",
    }
    known = result.returncode == 0 and required <= set(fields)
    return {
        "known": known,
        "path": str(path),
        "fields": fields,
        "detail": "evaluated" if known else (result.stderr.strip() or "unrecognized File Provider output"),
    }


def brctl_status() -> dict[str, Any]:
    result = run(["/usr/bin/brctl", "status", "com~apple~CloudDocs"], timeout=60)
    output = ANSI_RE.sub("", result.stdout + result.stderr)
    last_sync = None
    match = re.search(r"last-sync:([^,}]+)", output)
    if match:
        last_sync = match.group(1).strip()
    caught_up = bool(re.search(r"\bcaught-up\b", output))
    idle = "client:idle" in output
    known = result.returncode == 0 and "containers matching" in output and last_sync is not None
    return {
        "known": known,
        "caught_up": caught_up,
        "idle": idle,
        "pending": known and not caught_up,
        "last_activity": last_sync,
        "detail": "caught up" if known and caught_up else (result.stderr.strip() or "container not caught up"),
    }


def first_materialization_problem(root: Path) -> tuple[str | None, str | None]:
    dataless = run(["/usr/bin/find", str(root), "-flags", "+dataless", "-print", "-quit"], timeout=120)
    dataless_path = dataless.stdout.strip().splitlines()[0] if dataless.returncode == 0 and dataless.stdout.strip() else None
    conflicts = run(
        [
            "/usr/bin/find",
            str(root),
            "-type",
            "f",
            "(",
            "-iname",
            "*conflicted copy*",
            "-o",
            "-iname",
            "*conflict copy*",
            ")",
            "-print",
            "-quit",
        ],
        timeout=120,
    )
    conflict_path = conflicts.stdout.strip().splitlines()[0] if conflicts.returncode == 0 and conflicts.stdout.strip() else None
    return dataless_path, conflict_path


def icloud_health(root: Path, paths: Iterable[Path] = ()) -> dict[str, Any]:
    root_state = fileprovider_evaluate(root)
    container = brctl_status()
    dataless, conflict = first_materialization_problem(root)
    path_states = [fileprovider_evaluate(path) for path in paths if path.exists() or path.is_symlink()]
    all_states = [root_state, *path_states]
    known = root.is_dir() and all(item["known"] for item in all_states) and container["known"]
    pending_paths = [
        item["path"]
        for item in all_states
        if not item["known"]
        or item["fields"].get("isUploading")
        or not item["fields"].get("isUploaded")
        or not item["fields"].get("isMostRecentVersionDownloaded")
    ]
    root_fields = root_state["fields"]
    access_ready = bool(
        known
        and not dataless
        and not conflict
        and not any(item["fields"].get("hasUnresolvedConflicts") for item in all_states)
        and not any(item["fields"].get("isSyncPaused") for item in all_states)
        and not any(item["fields"].get("isExcludedFromSync") for item in all_states)
        and root_fields.get("isDownloaded")
        and root_fields.get("isRecursivelyDownloaded")
        and root_fields.get("isKeepDownloaded")
        and root_fields.get("isMostRecentVersionDownloaded")
    )
    healthy = bool(
        access_ready
        and not pending_paths
        and container["caught_up"]
    )
    state = "healthy" if healthy else "unknown" if not known else "paused" if any(
        item["fields"].get("isSyncPaused") for item in all_states
    ) else "conflict" if conflict or any(
        item["fields"].get("hasUnresolvedConflicts") for item in all_states
    ) else "dataless" if dataless else "uploading" if pending_paths else "downloading" if not root_fields.get(
        "isRecursivelyDownloaded"
    ) else "caught-up-pending" if not container["caught_up"] else "degraded"
    return {
        "healthy": healthy,
        "access_ready": access_ready,
        "state": state,
        "root": root_state,
        "container": container,
        "dataless_path": dataless,
        "conflict_path": conflict,
        "pending_paths": pending_paths,
        "failed_path_count": sum(not item["known"] for item in all_states),
        "last_icloud_activity": container.get("last_activity"),
    }


def host_config(path: Path | None = None) -> dict[str, Any]:
    config = read_json(path or HOST_CONFIG, "remote Vault host configuration")
    required = {"schema_version", "role", "machine_id", "vault_root"}
    if config.get("schema_version") != 1 or config.get("role") != "host" or not required <= set(config):
        raise AccessError("remote Vault host configuration is incomplete")
    return config


def client_config(path: Path | None = None) -> dict[str, Any]:
    config = read_json(path or CLIENT_CONFIG, "remote Vault client configuration")
    required = {
        "schema_version",
        "role",
        "machine_id",
        "mount_root",
        "source_machine_id",
        "source_alias",
        "source_root",
        "source_helper",
        "writable",
        "git_owner_machine_id",
    }
    if config.get("schema_version") != 1 or config.get("role") != "client" or not required <= set(config):
        raise AccessError("remote Vault client configuration is incomplete")
    return config


def host_status(config: dict[str, Any], *, full_health: bool = True) -> dict[str, Any]:
    root = Path(str(config["vault_root"])).expanduser()
    health = icloud_health(root) if full_health else {"healthy": None, "state": "not-checked"}
    return {
        "ok": bool(health.get("access_ready")) if full_health else True,
        "machine_id": config["machine_id"],
        "vault_root": str(root),
        "icloud": health,
    }


def host_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="remote-vault-host")
    parser.add_argument("--config", type=Path, default=HOST_CONFIG)
    sub = parser.add_subparsers(dest="action", required=True)
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    config = host_config(args.config)
    result = host_status(config)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


def host_call(config: dict[str, Any], argv: list[str], *, timeout: int = 360) -> dict[str, Any]:
    remote = ["python3", str(config["source_helper"]), "host", *argv, "--json"]
    result = ssh_command(str(config["source_alias"]), remote, timeout=timeout)
    if result.returncode != 0:
        raise AccessError(result.stderr.strip() or result.stdout.strip() or "Vault host command failed")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AccessError("Vault host returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise AccessError("Vault host returned an invalid response")
    return value


def mount_record(config: dict[str, Any]) -> dict[str, Any]:
    mount_root = Path(str(config["mount_root"]))
    findmnt = run(["findmnt", "--json", "--target", str(mount_root), "--output", "TARGET,SOURCE,FSTYPE,OPTIONS"])
    record: dict[str, Any] | None = None
    if findmnt.returncode == 0:
        try:
            filesystems = json.loads(findmnt.stdout).get("filesystems", [])
            record = filesystems[0] if filesystems else None
        except (json.JSONDecodeError, AttributeError, IndexError):
            record = None
    options = str(record.get("options", "")).split(",") if record else []
    expected_source = f"{config['source_alias']}:{config['source_root']}"
    sentinel = mount_root / "AGENTS.md"
    exact_mount = bool(record and record.get("target") == str(mount_root))
    healthy = bool(
        exact_mount
        and str(record.get("fstype", "")).startswith("fuse.sshfs")
        and record.get("source") == expected_source
        and "rw" in options
        and sentinel.is_file()
        and os.access(mount_root, os.R_OK | os.W_OK | os.X_OK)
    )
    return {
        "mounted": exact_mount,
        "healthy": healthy,
        "read_write": exact_mount and "rw" in options,
        "target": record.get("target") if exact_mount else str(mount_root),
        "source": record.get("source") if exact_mount else None,
        "fstype": record.get("fstype") if exact_mount else None,
        "options": options if exact_mount else [],
        "sentinel": str(sentinel),
    }


def mount_service(config: dict[str, Any]) -> int:
    mount_root = Path(str(config["mount_root"]))
    mount_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if shutil.which("sshfs") is None:
        raise AccessError("sshfs is missing; converge the approved remote-vault dependency")
    options = [
        "reconnect",
        "ServerAliveInterval=15",
        "ServerAliveCountMax=3",
        "ConnectTimeout=10",
        "cache=no",
        "entry_timeout=1",
        "attr_timeout=1",
        "negative_timeout=0",
        "idmap=user",
    ]
    if not config.get("writable"):
        options.append("ro")
    source = f"{config['source_alias']}:{config['source_root']}"
    os.execvp("sshfs", ["sshfs", "-f", source, str(mount_root), "-o", ",".join(options)])
    return 1


def systemctl(*arguments: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(["systemctl", "--user", *arguments], timeout=60, check=check)


def access_mount(config: dict[str, Any], timeout: int) -> dict[str, Any]:
    before = mount_record(config)
    if not before["healthy"]:
        systemctl("daemon-reload", check=True)
        systemctl("start", "vault-remote.service", check=True)
    deadline = time.monotonic() + timeout
    state = mount_record(config)
    while not state["healthy"] and time.monotonic() < deadline:
        time.sleep(1)
        state = mount_record(config)
    if not state["healthy"]:
        journal = run(["journalctl", "--user", "-u", "vault-remote.service", "-n", "20", "--no-pager"])
        raise AccessError("SSHFS mount did not become healthy: " + (journal.stdout.strip() or "no journal detail"))
    host = host_call(config, ["status"])
    if host.get("machine_id") != config["source_machine_id"] or not host.get("icloud", {}).get("access_ready"):
        raise AccessError("mounted source host identity or Vault state is not safe to access")
    return {"ok": True, "mount": state, "host": host}


def access_unmount(config: dict[str, Any]) -> dict[str, Any]:
    mount_root = str(config["mount_root"])
    state = mount_record(config)
    if state["mounted"]:
        result = run(["fusermount3", "-u", mount_root], timeout=60)
        if result.returncode != 0:
            raise AccessError(result.stderr.strip() or "graceful SSHFS unmount refused")
    systemctl("stop", "vault-remote.service")
    return {"ok": True, "mount": mount_record(config)}


def client_status(config: dict[str, Any], *, include_host: bool = True) -> dict[str, Any]:
    mount = mount_record(config)
    ssh = ssh_command(str(config["source_alias"]), ["true"], timeout=15)
    host: dict[str, Any] | None = None
    host_error: str | None = None
    if include_host and ssh.returncode == 0:
        try:
            host = host_call(config, ["status"])
        except AccessError as exc:
            host_error = str(exc)
    ready = bool(
        ssh.returncode == 0
        and mount["healthy"]
        and host
        and host.get("machine_id") == config["source_machine_id"]
        and host.get("icloud", {}).get("access_ready")
    )
    return {
        "ok": ready,
        "machine_id": config["machine_id"],
        "mode": "remote-sshfs",
        "ssh": {"healthy": ssh.returncode == 0, "detail": ssh.stderr.strip()},
        "mount": mount,
        "host": host,
        "host_error": host_error,
    }


def delegate_content_command(config: dict[str, Any], argv: list[str]) -> int:
    state = client_status(config)
    if not state["ok"]:
        raise AccessError("remote Vault access is unhealthy; run `vault access doctor`")
    dispatcher = Path(str(config["mount_root"])) / "_system/commands/vault.py"
    if not dispatcher.is_file():
        raise AccessError(f"mounted Vault dispatcher is missing: {dispatcher}")
    os.execv(sys.executable, [sys.executable, str(dispatcher), *argv])
    return 1


def client_main(argv: list[str]) -> int:
    config = client_config()
    if not argv:
        raise AccessError("usage: vault root | vault access ... | vault COMMAND ...")
    if argv[0] == "root":
        print(config["mount_root"])
        return 0
    if argv[0] == "_mount_service":
        return mount_service(config)
    if argv[0] != "access":
        return delegate_content_command(config, argv)
    parser = argparse.ArgumentParser(prog="vault access")
    sub = parser.add_subparsers(dest="action", required=True)
    mount = sub.add_parser("mount")
    mount.add_argument("--timeout", type=int, default=60)
    sub.add_parser("unmount")
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    args = parser.parse_args(argv[1:])
    if args.action == "mount":
        result = access_mount(config, args.timeout)
    elif args.action == "unmount":
        result = access_unmount(config)
    elif args.action in {"status", "doctor"}:
        result = client_status(config)
    else:
        raise AccessError(f"unsupported access action: {args.action}")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


def generated_client_config(registry: dict[str, Any], client: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    vault_git = registry["vault_git"]
    return {
        "schema_version": 1,
        "role": "client",
        "machine_id": client["id"],
        "mount_root": expand_root(str(client["home"]), client["roots"]["vault"]),
        "source_machine_id": source["id"],
        "source_alias": source["ssh_alias"],
        "source_root": expand_root(str(source["home"]), source["roots"]["vault"]),
        "source_helper": str(PurePosixPath(str(source["home"])) / ".local/share/vault-access/remote_vault_access.py"),
        "writable": client["vault"]["remote_access"]["writable"],
        "git_owner_machine_id": vault_git["owner_machine_id"],
    }


def generated_host_config(source: dict[str, Any]) -> dict[str, Any]:
    source_root = expand_root(str(source["home"]), source["roots"]["vault"])
    return {
        "schema_version": 1,
        "role": "host",
        "machine_id": source["id"],
        "vault_root": source_root,
    }


def managed_launcher() -> str:
    return (
        "#!/bin/sh\n"
        f"# {MANAGED_MARKER}\n"
        "exec python3 \"$HOME/.local/share/vault-access/remote_vault_access.py\" \"$@\"\n"
    )


def managed_unit() -> str:
    return f"""# {MANAGED_MARKER}
[Unit]
Description=Registered remote iCloud Vault SSHFS mount
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/share/vault-access/remote_vault_access.py _mount_service
Restart=on-failure
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=default.target
"""


def backup_if_needed(path: Path, expected: bytes, apply: bool) -> str:
    if path.is_file() and not path.is_symlink() and path.read_bytes() == expected:
        return "match"
    if not apply:
        return "different" if path.exists() or path.is_symlink() else "missing"
    if path.exists() or path.is_symlink():
        backup = path.with_name(f"{path.name}.backup-{utc_now().strftime('%Y%m%dT%H%M%SZ')}")
        if backup.exists() or backup.is_symlink():
            raise AccessError(f"backup collision: {backup}")
        os.replace(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(expected)
            handle.flush()
            os.fsync(handle.fileno())
        mode = 0o755 if path.name in {"vault", "remote_vault_access.py"} else 0o600
        if path.name.endswith(".service"):
            mode = 0o644
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return "installed"


def managed_paths_for_role(role: str, config: dict[str, Any]) -> dict[Path, bytes]:
    files = {
        INSTALLED_SCRIPT: Path(__file__).read_bytes(),
        HOST_CONFIG if role == "host" else CLIENT_CONFIG: (json.dumps(config, indent=2, sort_keys=True) + "\n").encode(),
    }
    if role == "client":
        files[MACHINE_ID] = f"{config['machine_id']}\n".encode()
        files[LAUNCHER] = managed_launcher().encode()
        files[SYSTEMD_UNIT] = managed_unit().encode()
    return files


def install_local(role: str, config_path: Path, mode: str) -> dict[str, Any]:
    config = read_json(config_path, "staged remote Vault configuration")
    if config.get("role") != role:
        raise AccessError("staged configuration role mismatch")
    files = managed_paths_for_role(role, config)
    if mode == "remove":
        if role == "client":
            systemctl("disable", "--now", "vault-remote.service")
        removed: list[str] = []
        for path in files:
            if not (path.exists() or path.is_symlink()):
                continue
            if path.is_file() and (
                MANAGED_MARKER in path.read_text(encoding="utf-8", errors="ignore")
                or path in {CLIENT_CONFIG, HOST_CONFIG, MACHINE_ID}
            ):
                path.unlink()
                removed.append(str(path))
            else:
                raise AccessError(f"refusing to remove unmanaged path: {path}")
        return {"ok": True, "mode": mode, "removed": removed}
    apply = mode == "apply"
    results = {str(path): backup_if_needed(path, content, apply) for path, content in files.items()}
    if role == "client" and apply:
        Path(str(config["mount_root"])).mkdir(parents=True, exist_ok=True, mode=0o700)
        systemctl("daemon-reload", check=True)
    ready = all(status == "match" for status in results.values()) if mode == "verify" else True
    return {"ok": ready, "ready": ready, "mode": mode, "role": role, "files": results}


def controller_preflight(client: dict[str, Any], source: dict[str, Any], source_root: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for machine, label in ((client, "client_ssh"), (source, "source_ssh")):
        probe = ssh_command(str(machine["ssh_alias"]), ["true"], timeout=15)
        results[label] = probe.returncode == 0
    identity = ssh_command(
        str(source["ssh_alias"]),
        ["/bin/sh", "-c", "test -f \"$HOME/.config/vault/machine-id\" && cat \"$HOME/.config/vault/machine-id\""],
    )
    results["source_identity"] = identity.returncode == 0 and identity.stdout.strip() == source["id"]
    materialized = ssh_command(
        str(source["ssh_alias"]),
        [
            "/bin/sh",
            "-c",
            "root=$1; test -d \"$root\" && test -f \"$root/AGENTS.md\" && "
            "test -f \"$root/.git\" && ! git -C \"$root\" rev-parse --git-dir >/dev/null 2>&1 && "
            "test -z \"$(find \"$root\" -flags +dataless -print -quit 2>/dev/null)\"",
            "vault-preflight",
            source_root,
        ],
        timeout=180,
    )
    results["source_materialized_gitless"] = materialized.returncode == 0
    mesh = ssh_command(
        str(client["ssh_alias"]),
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", str(source["ssh_alias"]), "true"],
        timeout=30,
    )
    results["client_to_source_ssh"] = mesh.returncode == 0
    sshfs = ssh_command(str(client["ssh_alias"]), ["sshfs", "--version"], timeout=20)
    results["sshfs"] = sshfs.returncode == 0
    results["ready"] = all(results.values())
    return results


def remote_stage_install(alias: str, role: str, config: dict[str, Any], mode: str) -> dict[str, Any]:
    token = uuid.uuid4().hex[:10]
    remote_dir = f"/tmp/ctx9-vault-access-{role}-{token}"
    create = ssh_command(alias, ["mkdir", "-m", "700", remote_dir], check=True)
    del create
    with tempfile.TemporaryDirectory(prefix="vault-access-stage-") as directory:
        local = Path(directory)
        script = local / "remote_vault_access.py"
        config_path = local / "config.json"
        shutil.copy2(Path(__file__), script)
        atomic_write(config_path, config)
        scp = run(["scp", "-q", str(script), str(config_path), f"{alias}:{remote_dir}/"], timeout=60)
        if scp.returncode != 0:
            raise AccessError(scp.stderr.strip() or f"failed to stage remote Vault helper on {alias}")
    result = ssh_command(
        alias,
        [
            "python3",
            f"{remote_dir}/remote_vault_access.py",
            "install-local",
            "--role",
            role,
            "--config",
            f"{remote_dir}/config.json",
            f"--{mode}",
        ],
        timeout=120,
    )
    ssh_command(alias, ["rm", "-rf", remote_dir], timeout=30)
    if result.returncode != 0:
        raise AccessError(result.stderr.strip() or result.stdout.strip() or f"remote install failed on {alias}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AccessError(f"remote install returned invalid JSON on {alias}") from exc
    return value


def controller_acceptance(client: dict[str, Any], client_config_value: dict[str, Any]) -> dict[str, Any]:
    alias = str(client["ssh_alias"])
    mount = ssh_command(alias, [str(PurePosixPath(str(client["home"])) / ".local/bin/vault"), "access", "mount"], timeout=180)
    if mount.returncode != 0:
        raise AccessError(mount.stderr.strip() or mount.stdout.strip() or "remote Vault mount failed")
    root = str(client_config_value["mount_root"])
    structure = ssh_command(
        alias,
        [
            "/bin/sh",
            "-c",
            "root=$1; test -r \"$root/AGENTS.md\" && test -d \"$root/_library\" && "
            "test -d \"$root/_system\" && test -f \"$root/.git\" && "
            "! git -C \"$root\" rev-parse --git-dir >/dev/null 2>&1",
            "vault-acceptance",
            root,
        ],
        timeout=120,
    )
    doctor = ssh_command(alias, [str(PurePosixPath(str(client["home"])) / ".local/bin/vault"), "access", "doctor", "--json"], timeout=180)
    if structure.returncode != 0 or doctor.returncode != 0:
        raise AccessError(structure.stderr.strip() or doctor.stderr.strip() or "remote Vault structural acceptance failed")
    enable = ssh_command(alias, ["systemctl", "--user", "enable", "vault-remote.service"], timeout=30)
    if enable.returncode != 0:
        raise AccessError(enable.stderr.strip() or "failed to enable remote Vault mount service")
    return {"mount": json.loads(mount.stdout), "doctor": json.loads(doctor.stdout), "structure": True, "enabled": True}


def controller_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="remote-vault-access")
    parser.add_argument("machine_id")
    parser.add_argument("--registry", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--remove", action="store_true")
    args = parser.parse_args(argv)
    registry_path = args.registry or find_registry()
    registry, machines = load_registry(registry_path)
    client, source = remote_client_topology(registry, machines, args.machine_id)
    client_value = generated_client_config(registry, client, source)
    host_value = generated_host_config(source)
    preflight = controller_preflight(client, source, str(client_value["source_root"]))
    selected_mode = "remove" if args.remove else "verify" if args.verify else "apply" if args.apply else "preview"
    report: dict[str, Any] = {
        "schema_version": 1,
        "mode": selected_mode,
        "client": client["id"],
        "source": source["id"],
        "mount_root": client_value["mount_root"],
        "source_root": client_value["source_root"],
        "preflight": preflight,
    }
    if selected_mode == "preview":
        report["ready_to_apply"] = preflight["ready"]
    else:
        if selected_mode != "remove" and not preflight["ready"]:
            raise AccessError("remote Vault preflight failed: " + ", ".join(key for key, value in preflight.items() if key != "ready" and not value))
        if selected_mode == "remove":
            ssh_command(str(client["ssh_alias"]), [str(PurePosixPath(str(client["home"])) / ".local/bin/vault"), "access", "unmount"], timeout=120)
        report["host_install"] = remote_stage_install(str(source["ssh_alias"]), "host", host_value, selected_mode)
        report["client_install"] = remote_stage_install(str(client["ssh_alias"]), "client", client_value, selected_mode)
        if selected_mode == "apply":
            report["acceptance"] = controller_acceptance(client, client_value)
        report["ready"] = bool(
            selected_mode == "remove"
            or report["host_install"].get("ok") and report["client_install"].get("ok")
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ready", report.get("ready_to_apply", False)) else 2


def install_local_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="remote-vault-access install-local")
    parser.add_argument("--role", choices=("client", "host"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--remove", action="store_true")
    args = parser.parse_args(argv)
    selected = "apply" if args.apply else "verify" if args.verify else "remove"
    result = install_local(args.role, args.config, selected)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "controller":
        return controller_main(arguments[1:])
    if arguments and arguments[0] == "install-local":
        return install_local_main(arguments[1:])
    if arguments and arguments[0] == "host":
        return host_main(arguments[1:])
    return client_main(arguments)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AccessError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Vault access failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
