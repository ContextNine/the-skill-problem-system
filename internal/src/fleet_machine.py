#!/usr/bin/env python3
"""Register and access fleet machines without requiring a Vault."""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from package_layout import AGENTS_ROOT, SKILLS_ROOT, active_instance_root, installed_state_root
from package_installer import installed_source

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = AGENTS_ROOT
DEFAULT_REGISTRY = active_instance_root() / "fleet/machines.json"
DEFAULT_RUNTIME_DIR = Path.home() / ".cache/fleet-machine"
DEFAULT_MACHINE_ID_PATH = installed_state_root() / "machine-id"
VAULT_MACHINE_ID_PATH = Path.home() / ".config/vault/machine-id"
MACHINE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.:-]*[A-Za-z0-9])?$")
REGISTRY_SCHEMA_VERSION = 7
ACCESS_PROVIDERS = ("wireguard", "tailscale")


def skill_script(skill: str, script: str) -> Path:
    source = SKILLS_ROOT / "_fleet" / skill / "scripts" / script
    return source if source.is_file() else Path.home() / ".agents/skills" / skill / "scripts" / script


ACCESS_RENDERER = skill_script("fleet-i-onboard-machine", "render_ssh_access.py")
ACCESS_INSPECTOR = skill_script("fleet-i-onboard-machine", "inspect_machine_access.py")

class MachineError(RuntimeError):
    pass


def machine_label(machine: dict[str, Any]) -> str:
    return str(machine["display_name"])


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    try:
        data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MachineError(
            f"machine registry missing: {path}; initialize with `fleet machine init --id ID "
            "--display-name NAME --platform macos|linux --apply`"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MachineError(f"cannot read machine registry {path}: {exc}") from exc
    validate_registry(data)
    return data


def validate_registry(data: dict[str, Any]) -> None:
    if data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise MachineError(
            f"machine registry schema_version must be {REGISTRY_SCHEMA_VERSION}; "
            "run the documented registry migration"
        )
    machines = data.get("machines")
    if not isinstance(machines, list) or not machines:
        raise MachineError("machine registry has no machines")
    primary_machine_id = data.get("primary_machine_id")
    if not isinstance(primary_machine_id, str) or not primary_machine_id:
        raise MachineError("machine registry primary_machine_id is missing")
    seen: set[str] = set()
    for machine in machines:
        required = {"id", "display_name", "enabled", "transport", "home", "role", "platform"}
        missing = sorted(required - set(machine))
        if missing:
            raise MachineError(
                f"machine {machine.get('id', '<unknown>')} missing: {', '.join(missing)}"
            )
        machine_id = machine["id"]
        if not isinstance(machine_id, str) or not MACHINE_ID_RE.fullmatch(machine_id) or machine_id in seen:
            raise MachineError(f"invalid or duplicate machine id: {machine_id!r}")
        seen.add(machine_id)
        if machine["role"] not in {"primary", "worker"}:
            raise MachineError(f"unsupported role for {machine_id}")
        if machine["platform"] not in {"macos", "linux"}:
            raise MachineError(f"unsupported platform for {machine_id}")
        if machine["transport"] not in {"local", "ssh"}:
            raise MachineError(f"unsupported transport for {machine_id}")
        if machine["transport"] == "ssh" and not machine.get("ssh_alias"):
            raise MachineError(f"ssh_alias missing for {machine_id}")
        home = str(machine["home"])
        if not PurePosixPath(home).is_absolute() or any(char.isspace() for char in home):
            raise MachineError(f"unsafe home path for {machine_id}")
        if "wireguard_address" in machine:
            raise MachineError(
                f"legacy wireguard_address is not supported for {machine_id}; "
                "move the route under machine_access.providers.wireguard"
            )
        validate_machine_access(machine)
        validate_roots_and_vault(machine)
        validate_vnc(machine)
    if primary_machine_id not in seen:
        raise MachineError("primary_machine_id does not match a registered machine")
    primary = next(machine for machine in machines if machine["id"] == primary_machine_id)
    if primary["role"] != "primary":
        raise MachineError("primary_machine_id must reference a primary machine")
    if sum(machine["role"] == "primary" for machine in machines) != 1:
        raise MachineError("machine registry must contain exactly one primary machine")
    validate_vault_topology(data)


def validate_route_host(value: Any, *, label: str) -> str:
    host = str(value or "")
    if not host or not HOST_RE.fullmatch(host):
        raise MachineError(f"invalid {label}: {host!r}")
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host and not MACHINE_ID_RE.fullmatch(host):
            raise MachineError(f"invalid {label}: {host!r}")
    else:
        if parsed.is_unspecified or parsed.is_multicast:
            raise MachineError(f"invalid {label}: {host!r}")
    return host


def validate_machine_access(machine: dict[str, Any]) -> None:
    access = machine.get("machine_access")
    if access is None and machine["transport"] != "ssh":
        return
    if not isinstance(access, dict):
        raise MachineError(f"machine_access missing for {machine['id']}")
    provider = access.get("provider")
    if provider not in ACCESS_PROVIDERS:
        raise MachineError(f"machine_access provider missing or unsupported for {machine['id']}")
    if machine["transport"] == "ssh":
        ssh_user = access.get("ssh_user")
        if not isinstance(ssh_user, str) or not ssh_user or any(char.isspace() for char in ssh_user):
            raise MachineError(f"machine_access ssh_user invalid for {machine['id']}")
        identity_file = access.get("identity_file")
        if not isinstance(identity_file, str) or not identity_file.startswith("~/.ssh/"):
            raise MachineError(f"machine_access identity_file invalid for {machine['id']}")
        lan_host = access.get("lan_host")
        if lan_host is not None:
            validate_route_host(lan_host, label=f"LAN host for {machine['id']}")
    providers = access.get("providers")
    if not isinstance(providers, dict) or provider not in providers:
        raise MachineError(f"selected provider is not configured for {machine['id']}")
    for provider_name, provider_config in providers.items():
        if provider_name not in ACCESS_PROVIDERS or not isinstance(provider_config, dict):
            raise MachineError(f"invalid machine-access provider record for {machine['id']}")
        state = provider_config.get("state")
        if state not in {"pending", "configured"}:
            raise MachineError(f"invalid {provider_name} state for {machine['id']}")
        if state == "configured":
            validate_route_host(
                provider_config.get("host"),
                label=f"{provider_name} host for {machine['id']}",
            )
        elif "host" in provider_config:
            raise MachineError(f"pending {provider_name} route must not define host for {machine['id']}")
        desired = provider_config.get("desired_state")
        if desired is not None:
            if provider_name != "tailscale" or not isinstance(desired, dict):
                raise MachineError(f"invalid desired state for {provider_name} on {machine['id']}")
            if set(desired) != {"device_name", "accept_dns", "accept_routes", "tailscale_ssh"}:
                raise MachineError(f"incomplete Tailscale desired state for {machine['id']}")
            if desired["device_name"] != machine["id"]:
                raise MachineError(f"Tailscale device_name must equal machine ID for {machine['id']}")
            for field in ("accept_dns", "accept_routes", "tailscale_ssh"):
                if not isinstance(desired[field], bool):
                    raise MachineError(f"invalid Tailscale {field} for {machine['id']}")
    selected = providers[provider]
    if machine["enabled"] and selected.get("state") != "configured":
        raise MachineError(f"enabled machine has pending selected access for {machine['id']}")


def resolve_registered_root(home: str, value: object, *, optional: bool = False) -> PurePosixPath | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or "$" in value:
        raise MachineError(f"invalid registered root: {value!r}")
    if value == "~":
        result = PurePosixPath(home)
    elif value.startswith("~/"):
        result = PurePosixPath(home).joinpath(*PurePosixPath(value[2:]).parts)
    else:
        result = PurePosixPath(value)
    if not result.is_absolute() or ".." in result.parts or value.startswith("~") and not value.startswith("~/") and value != "~":
        raise MachineError(f"registered root does not resolve safely: {value!r}")
    return result


def validate_roots_and_vault(machine: dict[str, Any]) -> None:
    roots = machine.get("roots")
    vault = machine.get("vault")
    if not isinstance(roots, dict) or set(roots) != {"code", "vault"}:
        raise MachineError(f"machine {machine['id']} needs exactly Code and Vault roots")
    if not isinstance(vault, dict) or not {"enabled", "checkout_mode", "required"} <= set(vault):
        raise MachineError(f"machine {machine['id']} needs an explicit Vault policy")
    if set(vault) - {"enabled", "checkout_mode", "required", "remote_access"}:
        raise MachineError(f"machine {machine['id']} has unsupported Vault policy fields")
    if not isinstance(vault.get("enabled"), bool) or not isinstance(vault.get("required"), bool):
        raise MachineError(f"machine {machine['id']} Vault flags must be booleans")
    mode = vault.get("checkout_mode")
    if mode not in {"primary-external-git", "icloud-gitless", "remote-sshfs", "none"}:
        raise MachineError(f"machine {machine['id']} has an unsupported Vault checkout mode")
    code_root = resolve_registered_root(str(machine["home"]), roots.get("code"))
    vault_root = resolve_registered_root(str(machine["home"]), roots.get("vault"), optional=not vault["enabled"])
    if vault["enabled"] and vault_root is None:
        raise MachineError(f"machine {machine['id']} enables the Vault without a Vault root")
    if vault["enabled"] != vault["required"] or vault["enabled"] != (mode != "none"):
        raise MachineError(f"machine {machine['id']} has inconsistent Vault enablement")
    remote = vault.get("remote_access")
    if mode == "remote-sshfs":
        if (
            not isinstance(remote, dict)
            or set(remote) != {"source_machine_id", "writable"}
            or not isinstance(remote.get("source_machine_id"), str)
            or not remote["source_machine_id"]
            or not isinstance(remote.get("writable"), bool)
        ):
            raise MachineError(f"remote Vault client {machine['id']} needs source_machine_id and writable")
    elif remote is not None:
        if (
            mode not in {"primary-external-git", "icloud-gitless"}
            or not isinstance(remote, dict)
            or set(remote) != {"host_enabled"}
            or not isinstance(remote.get("host_enabled"), bool)
        ):
            raise MachineError(f"machine {machine['id']} has an invalid Vault host policy")
    if vault_root is not None and code_root is not None and (
        code_root == vault_root or code_root in vault_root.parents or vault_root in code_root.parents
    ):
        raise MachineError(f"machine {machine['id']} Vault and Code roots must not overlap")
    if machine["role"] == "primary" and vault["enabled"] and mode != "primary-external-git":
        raise MachineError(f"primary machine {machine['id']} needs primary-external-git Vault mode")
    if mode == "primary-external-git" and (
        machine["role"] != "primary" or machine["platform"] != "macos"
    ):
        raise MachineError(f"primary-external-git requires a macOS primary: {machine['id']}")
    if machine["role"] == "worker" and machine["platform"] == "macos" and vault["enabled"] and mode != "icloud-gitless":
        raise MachineError(f"macOS worker {machine['id']} needs icloud-gitless Vault mode")
    if machine["platform"] == "linux" and vault["enabled"] and (
        mode != "remote-sshfs" or machine["role"] != "worker" or machine["transport"] != "ssh"
    ):
        raise MachineError(f"Linux Vault access requires a remote-sshfs SSH worker: {machine['id']}")


def validate_vault_topology(data: dict[str, Any]) -> None:
    vault_git = data.get("vault_git")
    required = {"owner_machine_id", "refresh_owner_machine_id", "remote", "branch"}
    if not isinstance(vault_git, dict) or set(vault_git) != required:
        raise MachineError("vault_git needs owner_machine_id, refresh_owner_machine_id, remote, and branch")
    if not all(isinstance(vault_git.get(field), str) and vault_git[field] for field in ("remote", "branch")):
        raise MachineError("vault_git remote and branch must be non-empty strings")
    machines = {str(machine["id"]): machine for machine in data["machines"]}
    git_owners = [
        machine
        for machine in machines.values()
        if machine["enabled"] and machine["vault"]["checkout_mode"] == "primary-external-git"
    ]
    owner_id = vault_git.get("owner_machine_id")
    refresh_id = vault_git.get("refresh_owner_machine_id")
    if not git_owners:
        if owner_id is not None or refresh_id is not None:
            raise MachineError("Vault-free registries must use null Git and refresh owners")
    elif (
        len(git_owners) != 1
        or owner_id != git_owners[0]["id"]
        or refresh_id != owner_id
    ):
        raise MachineError("vault_git owners must identify the one enabled primary-external-git machine")
    for machine in machines.values():
        if not machine["enabled"] or machine["vault"]["checkout_mode"] != "remote-sshfs":
            continue
        source_id = machine["vault"]["remote_access"]["source_machine_id"]
        if source_id == machine["id"]:
            raise MachineError(f"remote Vault client cannot source itself: {machine['id']}")
        source = machines.get(source_id)
        if source is None or not source["enabled"]:
            raise MachineError(f"remote Vault source is missing or disabled for {machine['id']}: {source_id}")
        source_vault = source["vault"]
        source_remote = source_vault.get("remote_access")
        if (
            source["platform"] != "macos"
            or source["transport"] != "ssh"
            or source_vault["checkout_mode"] not in {"primary-external-git", "icloud-gitless"}
            or not source_vault["enabled"]
            or not source_vault["required"]
            or not isinstance(source_remote, dict)
            or source_remote.get("host_enabled") is not True
            or not source.get("ssh_alias")
        ):
            raise MachineError(f"remote Vault source is not an enabled iCloud SSH host: {source_id}")


def validate_vnc(machine: dict[str, Any]) -> None:
    vnc = machine.get("vnc")
    if vnc is None:
        return
    kind = vnc.get("kind")
    if kind == "native-url":
        if not str(vnc.get("url", "")).startswith("vnc://"):
            raise MachineError(f"invalid native VNC URL for {machine['id']}")
        return
    if kind != "ssh-novnc":
        raise MachineError(f"unsupported VNC kind for {machine['id']}")
    required = {"remote_host", "remote_port", "default_local_port", "health_path", "open_path"}
    missing = sorted(required - set(vnc))
    if missing:
        raise MachineError(f"VNC for {machine['id']} missing: {', '.join(missing)}")
    for field in ("remote_port", "default_local_port"):
        value = vnc[field]
        if not isinstance(value, int) or not 1 <= value <= 65535:
            raise MachineError(f"invalid VNC {field} for {machine['id']}")


def resolve_machine(registry: dict[str, Any], requested: str, *, enabled: bool = True) -> dict[str, Any]:
    needle = requested.casefold()
    matches = [
        machine
        for machine in registry["machines"]
        if machine["id"].casefold() == needle
        or machine["display_name"].casefold() == needle
    ]
    if not matches:
        raise MachineError(f"unknown machine: {requested}")
    machine = matches[0]
    if enabled and not machine["enabled"]:
        raise MachineError(f"machine disabled: {machine['id']}")
    return machine


def ssh_base(machine: dict[str, Any]) -> list[str]:
    if not machine.get("ssh_alias"):
        raise MachineError(f"machine has no SSH alias: {machine['id']}")
    return ["ssh", "-o", "ConnectTimeout=10", str(machine["ssh_alias"])]


def probe(machine: dict[str, Any]) -> tuple[bool, str]:
    if machine["id"] == current_machine_id():
        return True, "local"
    if not machine.get("ssh_alias"):
        return False, "no SSH alias configured"
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", str(machine["ssh_alias"]), "true"],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    if result.returncode == 0:
        return True, "reachable"
    detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unreachable"
    return False, detail


def status_record(machine: dict[str, Any]) -> dict[str, Any]:
    reachable, detail = probe(machine)
    return {
        "id": machine["id"],
        "display_name": machine["display_name"],
        "enabled": machine["enabled"],
        "transport": machine["transport"],
        "role": machine["role"],
        "platform": machine["platform"],
        "reachable": reachable,
        "detail": detail,
        "vnc": machine.get("vnc", {}).get("kind"),
        "vault_mode": machine.get("vault", {}).get("checkout_mode"),
        "vault_source": machine.get("vault", {}).get("remote_access", {}).get("source_machine_id"),
    }


def runtime_dir() -> Path:
    return Path(os.environ.get("FLEET_MACHINE_RUNTIME_DIR", DEFAULT_RUNTIME_DIR)).expanduser()


def runtime_paths(machine: dict[str, Any]) -> tuple[Path, Path]:
    base = runtime_dir()
    return base / f"{machine['id']}-vnc.sock", base / f"{machine['id']}-vnc.json"


def read_metadata(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def tunnel_active(machine: dict[str, Any], control: Path) -> bool:
    if not control.exists():
        return False
    result = subprocess.run(
        ["ssh", "-F", "/dev/null", "-S", str(control), "-O", "check", str(machine["ssh_alias"])],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )
    return result.returncode == 0


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        try:
            candidate.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(preferred: int) -> int:
    if port_available(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def wait_for_health(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    error = "no response"
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 500:
                    return
        except (OSError, URLError) as exc:
            error = str(exc)
        time.sleep(0.25)
    raise MachineError(f"VNC tunnel health timeout: {error}")


def open_url(url: str) -> None:
    command = "open" if platform.system() == "Darwin" else "xdg-open"
    if not shutil.which(command):
        raise MachineError(f"browser opener unavailable: {command}")
    result = subprocess.run([command, url], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise MachineError(result.stderr.strip() or f"failed to open {url}")


def ensure_tunnel(machine: dict[str, Any], requested_port: int | None) -> tuple[int, str, bool]:
    vnc = machine["vnc"]
    control, metadata_path = runtime_paths(machine)
    metadata = read_metadata(metadata_path)
    if metadata and tunnel_active(machine, control):
        active_port = int(metadata["local_port"])
        if requested_port is not None and requested_port != active_port:
            raise MachineError(
                f"VNC tunnel already uses local port {active_port}; stop it before choosing {requested_port}"
            )
        return active_port, str(metadata["url"]), True

    base = runtime_dir()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        control.unlink()
    except FileNotFoundError:
        pass
    try:
        metadata_path.unlink()
    except FileNotFoundError:
        pass

    preferred = requested_port or int(vnc["default_local_port"])
    if requested_port is not None and not port_available(requested_port):
        raise MachineError(f"requested local port occupied: {requested_port}")
    local_port = requested_port or choose_port(preferred)
    forward = f"127.0.0.1:{local_port}:{vnc['remote_host']}:{vnc['remote_port']}"
    result = subprocess.run(
        [
            "ssh", "-M", "-S", str(control), "-fNT",
            "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=10",
            "-L", forward, str(machine["ssh_alias"]),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    if result.returncode != 0:
        raise MachineError(result.stderr.strip() or "failed to create VNC tunnel")
    health_url = f"http://127.0.0.1:{local_port}{vnc['health_path']}"
    url = f"http://127.0.0.1:{local_port}{vnc['open_path']}"
    try:
        wait_for_health(health_url)
    except Exception:
        subprocess.run(
            ["ssh", "-F", "/dev/null", "-S", str(control), "-O", "exit", str(machine["ssh_alias"])],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        raise
    metadata_path.write_text(
        json.dumps(
            {"machine_id": machine["id"], "local_port": local_port, "url": url},
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    metadata_path.chmod(0o600)
    return local_port, url, False


def stop_tunnel(machine: dict[str, Any]) -> bool:
    control, metadata_path = runtime_paths(machine)
    active = tunnel_active(machine, control)
    if active:
        result = subprocess.run(
            ["ssh", "-F", "/dev/null", "-S", str(control), "-O", "exit", str(machine["ssh_alias"])],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        if result.returncode != 0:
            raise MachineError(result.stderr.strip() or "failed to stop VNC tunnel")
    for path in (metadata_path, control):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return active


def command_list(args: argparse.Namespace, registry: dict[str, Any]) -> int:
    records = [
        {
            "id": machine["id"],
            "display_name": machine["display_name"],
            "enabled": machine["enabled"],
            "transport": machine["transport"],
            "role": machine["role"],
            "platform": machine["platform"],
            "ssh_alias": machine.get("ssh_alias"),
            "vnc": machine.get("vnc", {}).get("kind"),
        }
        for machine in registry["machines"]
    ]
    if args.json:
        print(json.dumps(records, indent=2))
        return 0
    for record in records:
        state = "enabled" if record["enabled"] else "disabled"
        access = record["ssh_alias"] or "local"
        print(
            f"{record['id']:<12} {record['display_name']:<14} {record['role']:<7} "
            f"{record['platform']:<6} {state:<8} {access:<12} vnc={record['vnc'] or '-'}"
        )
    return 0


def write_registry(path: Path, payload: dict[str, Any], apply: bool) -> int:
    rendered = json.dumps(payload, indent=2) + "\n"
    if not apply:
        print(f"DRY RUN: write {path}")
        print(rendered, end="")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"wrote {path}")
    return 0


def primary_registry(machine_id: str, display_name: str, platform_name: str, code_root: str, vault_root: str | None) -> dict[str, Any]:
    if vault_root and platform_name != "macos":
        raise MachineError("a Vault Git-owning primary must run macOS")
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "primary_machine_id": machine_id,
        "vault_git": {
            "owner_machine_id": machine_id if vault_root else None,
            "refresh_owner_machine_id": machine_id if vault_root else None,
            "remote": "origin",
            "branch": "master",
        },
        "machines": [
            {
                "id": machine_id,
                "display_name": display_name,
                "enabled": True,
                "role": "primary",
                "platform": platform_name,
                "transport": "local",
                "home": str(Path.home()),
                "roots": {"code": code_root, "vault": vault_root},
                "vault": {"enabled": bool(vault_root), "checkout_mode": "primary-external-git" if vault_root else "none", "required": bool(vault_root)},
                "global_agents_eligible": True,
            }
        ],
    }


def tailscale_desired_state(machine_id: str) -> dict[str, Any]:
    return {
        "device_name": machine_id,
        "accept_dns": True,
        "accept_routes": False,
        "tailscale_ssh": False,
    }


def worker_record(
    *,
    machine_id: str,
    display_name: str,
    platform_name: str,
    home: str,
    ssh_user: str,
    provider: str,
    code_root: str,
    vault_root: str | None,
    vault_source: str | None = None,
    vault_writable: bool = True,
    lan_host: str | None = None,
    mesh_host: str | None = None,
    identity_file: str = "~/.ssh/codex_fleet_ed25519",
    operation: str = "new",
) -> dict[str, Any]:
    if platform_name == "linux" and bool(vault_root) != bool(vault_source):
        raise MachineError("Linux remote Vault registration needs both --vault-root and --vault-source")
    if platform_name == "macos" and vault_source:
        raise MachineError("macOS iCloud workers cannot use --vault-source")
    if platform_name == "linux" and vault_root:
        vault = {
            "enabled": True,
            "checkout_mode": "remote-sshfs",
            "required": True,
            "remote_access": {
                "source_machine_id": vault_source,
                "writable": vault_writable,
            },
        }
    else:
        vault = {
            "enabled": bool(vault_root),
            "checkout_mode": "icloud-gitless" if platform_name == "macos" and vault_root else "none",
            "required": bool(vault_root),
        }
    provider_config: dict[str, Any] = {"state": "pending"}
    if provider == "tailscale":
        provider_config["desired_state"] = tailscale_desired_state(machine_id)
    if mesh_host:
        provider_config = {"state": "configured", "host": mesh_host}
        if provider == "tailscale":
            provider_config["desired_state"] = tailscale_desired_state(machine_id)
    access: dict[str, Any] = {
        "provider": provider,
        "ssh_user": ssh_user,
        "identity_file": identity_file,
        "providers": {provider: provider_config},
    }
    if lan_host:
        access["lan_host"] = lan_host
    return {
        "id": machine_id,
        "display_name": display_name,
        "enabled": False,
        "role": "worker",
        "platform": platform_name,
        "transport": "ssh",
        "ssh_alias": machine_id,
        "home": home,
        "roots": {"code": code_root, "vault": vault_root},
        "vault": vault,
        "global_agents_eligible": False,
        "private_notes_path": (
            "skills/config/fleet-i-code-folder-and-computer-topology/"
            f"private/My Machines/{machine_id}.md"
        ),
        "onboarding": {"operation": operation},
        "machine_access": access,
    }


def command_init(args: argparse.Namespace) -> int:
    if args.registry.exists():
        raise MachineError(f"machine registry already exists: {args.registry}")
    payload = primary_registry(args.id, args.display_name, args.platform, args.code_root, args.vault_root)
    validate_registry(payload)
    return write_registry(args.registry, payload, args.apply)


def command_register_worker(args: argparse.Namespace, registry: dict[str, Any]) -> int:
    if any(machine["id"] == args.id for machine in registry["machines"]):
        raise MachineError(f"machine already registered: {args.id}")
    if args.ssh_alias != args.id:
        raise MachineError("canonical --ssh-alias must equal machine --id")
    registry["machines"].append(
        worker_record(
            machine_id=args.id,
            display_name=args.display_name,
            platform_name=args.platform,
            home=args.home,
            ssh_user=args.ssh_user,
            provider=args.provider,
            code_root=args.code_root,
            vault_root=args.vault_root,
            vault_source=args.vault_source,
            vault_writable=not args.vault_read_only,
            lan_host=args.lan_host,
            mesh_host=args.mesh_host,
            identity_file=args.identity_file,
            operation=args.operation,
        )
    )
    payload = json.loads(json.dumps(registry))
    validate_registry(payload)
    return write_registry(args.registry, payload, args.apply)


def command_identify(args: argparse.Namespace, registry: dict[str, Any]) -> int:
    machine = resolve_machine(registry, args.name, enabled=False)
    path = DEFAULT_MACHINE_ID_PATH
    if not args.apply:
        print(f"DRY RUN: write fleet identity {machine['id']} to {path}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(f"{machine['id']}\n", encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    vault = machine.get("vault", {})
    if vault.get("checkout_mode") in {"icloud-gitless", "remote-sshfs"}:
        VAULT_MACHINE_ID_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        VAULT_MACHINE_ID_PATH.write_text(f"{machine['id']}\n", encoding="utf-8")
        VAULT_MACHINE_ID_PATH.chmod(0o600)
    elif vault.get("checkout_mode") == "primary-external-git":
        vault_root = resolve_registered_root(str(machine["home"]), machine["roots"]["vault"])
        subprocess.run(["git", "-C", str(vault_root), "config", "--local", "vault.machine-id", str(machine["id"])], check=True)
    print(f"identified this machine as {machine['id']}")
    return 0

def command_status(args: argparse.Namespace, registry: dict[str, Any]) -> int:
    machines = (
        [resolve_machine(registry, args.name, enabled=False)]
        if args.name
        else registry["machines"]
    )
    records = [status_record(machine) for machine in machines]
    if args.json:
        print(json.dumps(records[0] if args.name else records, indent=2))
    else:
        for record in records:
            state = "reachable" if record["reachable"] else "unreachable"
            enabled = "enabled" if record["enabled"] else "disabled"
            print(f"{record['id']}: {state}, {enabled}, {record['detail']}")
    return 0 if all(record["reachable"] for record in records if record["enabled"]) else 1


def command_ssh(args: argparse.Namespace, registry: dict[str, Any]) -> int:
    machine = resolve_machine(registry, args.name)
    command = list(args.remote_command)
    argv = ssh_base(machine)
    if command:
        argv.extend(["--", *command])
    return subprocess.run(argv).returncode


def command_vnc(args: argparse.Namespace, registry: dict[str, Any]) -> int:
    machine = resolve_machine(registry, args.name)
    vnc = machine.get("vnc")
    if not vnc:
        raise MachineError(f"VNC not configured for machine: {machine['id']}")
    if vnc["kind"] == "native-url":
        if args.stop:
            print(f"{machine['id']}: native VNC has no managed tunnel")
            return 0
        if args.status:
            print(f"{machine['id']}: native VNC available at {vnc['url']}")
            return 0
        if not args.no_open:
            open_url(vnc["url"])
        print(vnc["url"])
        return 0

    control, metadata_path = runtime_paths(machine)
    if args.stop:
        was_active = stop_tunnel(machine)
        print(f"{machine['id']}: {'stopped' if was_active else 'inactive'}")
        return 0
    if args.status:
        metadata = read_metadata(metadata_path)
        if metadata and tunnel_active(machine, control):
            print(f"{machine['id']}: active {metadata['url']}")
            return 0
        print(f"{machine['id']}: inactive")
        return 1
    local_port, url, reused = ensure_tunnel(machine, args.local_port)
    if not args.no_open:
        open_url(url)
    print(f"{machine['id']}: {'reused' if reused else 'started'} local port {local_port}")
    print(url)
    return 0


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug if MACHINE_ID_RE.fullmatch(slug) else ""


def prompt_text(label: str, *, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{label}{suffix}: ").strip()
    except EOFError as exc:
        if default is not None:
            return default
        raise MachineError(f"input ended while asking for {label}") from exc
    return answer or (default or "")


def prompt_choice(label: str, choices: tuple[str, ...], *, default: str | None = None) -> str:
    if default is not None and default not in choices:
        raise ValueError(f"invalid prompt default: {default}")
    rendered = "/".join(choices)
    while True:
        answer = prompt_text(f"{label} ({rendered})", default=default).casefold()
        if answer in choices:
            return answer
        print(f"Choose exactly one of: {', '.join(choices)}", file=sys.stderr)


def prompt_yes_no(label: str, *, default: bool) -> bool:
    answer = prompt_text(label, default="Y" if default else "N").casefold()
    if answer in {"y", "yes"}:
        return True
    if answer in {"n", "no"}:
        return False
    print("Choose yes or no.", file=sys.stderr)
    return prompt_yes_no(label, default=default)


def current_platform() -> str:
    return "macos" if platform.system() == "Darwin" else "linux"


def portable_root(path: Path, home: Path) -> str:
    resolved = path.expanduser().resolve()
    home = home.expanduser().resolve()
    try:
        relative = resolved.relative_to(home)
    except ValueError:
        return str(resolved)
    return "~" if not relative.parts else "~/" + relative.as_posix()


def write_machine_note(root: Path, record: dict[str, Any], apply: bool) -> None:
    relative = Path(record["private_notes_path"])
    target = root / relative
    provider = record["machine_access"]["provider"]
    operation = record["onboarding"]["operation"]
    rendered = (
        "---\n"
        "type: machine\n"
        "status: onboarding\n"
        "---\n\n"
        "## Identity\n\n"
        f"- Machine ID and canonical SSH alias: `{record['id']}`\n"
        f"- Display name: {record['display_name']}\n"
        f"- Role: {record['platform']} worker\n"
        f"- Onboarding operation: {operation}\n"
        f"- Personal machine-access provider: {provider}\n"
        f"- Home: `{record['home']}`\n\n"
        "## Onboarding\n\n"
        "Follow [[shared-onboarding-and-acceptance]] and the matching role/provider routes "
        "from `$fleet-i-onboard-machine`. Keep this registry entry disabled until acceptance passes.\n"
    )
    if not apply:
        print(f"DRY RUN: write {target}")
        print(rendered, end="")
        return
    if target.exists():
        raise MachineError(f"machine note already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target}")


def onboarding_prompt(record: dict[str, Any]) -> str:
    role = "worker Mac" if record["platform"] == "macos" else "Linux worker"
    provider = record["machine_access"]["provider"].title()
    operation = record["onboarding"]["operation"]
    verb = {
        "new": "Set up",
        "rebuilt": "Rebuild",
        "replaced": "Replace",
        "recovered": "Recover",
    }[operation]
    return (
        f"$fleet-i-onboard-machine {verb} the disabled {role} "
        f"{record['id']} using {provider} for personal fleet access. "
        "Keep the canonical SSH alias stable, complete the selected provider and role acceptance, "
        "and enable the registry entry only after reboot and unattended inbound verification pass."
    )


def offer_codex_handoff(root: Path, request: str) -> None:
    print("\nCodex handoff request:\n")
    print(request)
    pbcopy = Path("/usr/bin/pbcopy")
    codex = shutil.which("codex")
    if not pbcopy.is_file() or not codex:
        print("Codex handoff not opened: pbcopy or Codex CLI is unavailable.")
        return
    login = subprocess.run(
        [codex, "login", "status"],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
    if login.returncode != 0:
        print("Codex handoff not opened: Codex CLI is not authenticated.")
        return
    subprocess.run([str(pbcopy)], input=request, text=True, check=True, timeout=10)
    subprocess.run([codex, "app", str(root)], check=True, timeout=30)
    print("Copied the editable request and opened Codex at the Fleet source; nothing was submitted.")


def command_setup(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve() if args.root else args.registry.parents[3]
    registry_exists = args.registry.exists()
    if registry_exists:
        registry = load_registry(args.registry)
        primary = resolve_machine(registry, registry["primary_machine_id"], enabled=False)
    else:
        primary_platform = current_platform()
        proposed_primary_id = slugify(socket.gethostname().split(".")[0]) or "primary"
        primary_id = prompt_text("Primary machine ID", default=proposed_primary_id)
        if not MACHINE_ID_RE.fullmatch(primary_id):
            raise MachineError("primary machine ID must use lower-kebab format")
        primary_display = prompt_text("Primary machine display name", default=primary_id)
        registry = primary_registry(
            primary_id,
            primary_display,
            primary_platform,
            "~/" + "Code",
            args.vault_root,
        )
        primary = registry["machines"][0]

    operation = prompt_choice(
        "Machine operation",
        ("new", "rebuilt", "replaced", "recovered"),
        default="new",
    )
    role = prompt_choice("Target role", ("macos", "linux"))
    display_name = prompt_text("Machine display name")
    if not display_name:
        raise MachineError("machine display name is required")
    proposed_id = slugify(display_name)
    machine_id = prompt_text("Machine ID and canonical SSH alias", default=proposed_id)
    if not MACHINE_ID_RE.fullmatch(machine_id):
        raise MachineError("machine ID must use lower-kebab format")
    if any(item["id"] == machine_id for item in registry["machines"]):
        raise MachineError(f"machine already registered: {machine_id}")
    note_path = (
        args.registry.parent.parent
        / "skills/config/fleet-i-code-folder-and-computer-topology/private/My Machines"
        / f"{machine_id}.md"
    )
    if note_path.exists():
        raise MachineError(f"machine note already exists: {note_path}")

    print("\nChoose the personal machine-access provider. Neither option is the default.")
    print("WireGuard requires an existing WireGuard network, such as a deployed Kubernetes Helm chart.")
    print("Tailscale uses its coordination service; authentication and account selection remain manual.")
    provider = prompt_choice("Machine-access provider", ACCESS_PROVIDERS)
    ssh_user = prompt_text("SSH user", default=getpass.getuser())
    home_default = f"/{'Users' if role == 'macos' else 'home'}/{ssh_user}"
    home = prompt_text("Target home directory", default=home_default)
    code_root = prompt_text("Code root", default="~/" + "Code")
    vault_root: str | None = None
    if primary["roots"].get("vault") and role == "macos" and prompt_yes_no("Join the existing Vault through iCloud?", default=True):
        vault_name = Path(primary["roots"]["vault"]).name
        vault_root = f"~/Library/Mobile Documents/iCloud~md~obsidian/Documents/{vault_name}"

    record = worker_record(
        machine_id=machine_id,
        display_name=display_name,
        platform_name=role,
        home=home,
        ssh_user=ssh_user,
        provider=provider,
        code_root=code_root,
        vault_root=vault_root,
        operation=operation,
    )
    payload = json.loads(json.dumps(registry))
    payload["machines"].append(record)
    validate_registry(payload)

    print("\nSetup preview:\n")
    print(json.dumps(record, indent=2))
    request = onboarding_prompt(record)
    if not args.apply:
        write_registry(args.registry, payload, False)
        write_machine_note(args.registry.parent.parent, record, False)
        print("\nCodex handoff request:\n")
        print(request)
        return 0
    if not args.yes and not prompt_yes_no("Apply this disabled machine registration?", default=False):
        print("Machine setup deferred; no registry or note changes were made.")
        print("\nCodex handoff request:\n")
        print(request)
        return 0

    write_registry(args.registry, payload, True)
    write_machine_note(args.registry.parent.parent, record, True)
    if not registry_exists:
        command_identify(argparse.Namespace(name=primary["id"], root=str(root), apply=True), payload)
    if args.no_codex:
        print("\nCodex handoff request:\n")
        print(request)
    elif prompt_yes_no("Open Codex and copy the editable request?", default=True):
        offer_codex_handoff(root, request)
    else:
        print("\nCodex handoff request:\n")
        print(request)
    return 0


def current_machine_id(root: Path = ROOT) -> str:
    try:
        value = DEFAULT_MACHINE_ID_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if not value:
        raise MachineError("current machine has no registered fleet identity; run `fleet machine identify ID`")
    return value


def require_primary(registry: dict[str, Any]) -> None:
    machine = resolve_machine(registry, current_machine_id())
    if machine["id"] != registry["primary_machine_id"]:
        raise MachineError("registry changes must run on the registered fleet primary")

def run_access_renderer(
    registry_path: Path,
    *,
    apply: bool,
    source_ids: list[str] | None = None,
) -> None:
    if not ACCESS_RENDERER.is_file():
        raise MachineError(f"SSH access renderer missing: {ACCESS_RENDERER}")
    registry = load_registry(registry_path)
    local_id = current_machine_id()
    if local_id != registry["primary_machine_id"]:
        raise MachineError("fleet SSH access must be rendered from the registered primary")
    selected_ids = source_ids or [
        str(machine["id"])
        for machine in registry["machines"]
        if machine.get("enabled")
    ]
    if not selected_ids:
        raise MachineError("no source machines selected for SSH access rendering")
    seen: set[str] = set()
    registry_text = registry_path.read_text(encoding="utf-8")
    renderer_source = ACCESS_RENDERER.read_text(encoding="utf-8")
    for source_id in selected_ids:
        if source_id in seen:
            continue
        seen.add(source_id)
        source = resolve_machine(registry, source_id, enabled=False)
        if not source.get("enabled"):
            raise MachineError(f"source machine {source_id} is disabled")
        mode = "--apply" if apply else "--dry-run"
        print(f"{mode.removeprefix('--').upper()} SSH access for {source_id}")
        renderer_args = [
            "--registry",
            "/dev/stdin" if source_id != local_id else str(registry_path),
            "--source-machine-id",
            source_id,
            mode,
        ]
        if source_id == local_id:
            executed = subprocess.run(
                [sys.executable, str(ACCESS_RENDERER), *renderer_args],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        else:
            if source.get("transport") != "ssh" or not source.get("ssh_alias"):
                raise MachineError(f"source machine {source_id} has no SSH transport")
            remote_command = shlex.join(["python3", "-c", renderer_source, *renderer_args])
            executed = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=10",
                    str(source["ssh_alias"]),
                    remote_command,
                ],
                input=registry_text,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        if executed.stdout:
            print(executed.stdout, end="")
        if executed.returncode != 0:
            detail = executed.stderr.strip().splitlines()[-1] if executed.stderr.strip() else "renderer failed"
            raise MachineError(f"SSH access render failed for {source_id}: {detail}")


def preview_access_renderer(payload: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory(prefix="vault-machine-access-") as temporary:
        registry_path = Path(temporary) / "machines.json"
        registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        run_access_renderer(registry_path, apply=False)


def command_access_configure(
    args: argparse.Namespace,
    registry: dict[str, Any],
) -> int:
    machine = resolve_machine(registry, args.name, enabled=False)
    access = machine["machine_access"]
    provider_config: dict[str, Any] = {
        "state": "configured",
        "host": validate_route_host(args.host, label=f"{args.provider} host"),
    }
    if args.client_variant:
        provider_config["client_variant"] = args.client_variant
    if args.provider == "tailscale":
        provider_config["desired_state"] = tailscale_desired_state(str(machine["id"]))
    previous = json.loads(json.dumps(registry))
    access["providers"][args.provider] = provider_config
    if args.lan_host:
        access["lan_host"] = validate_route_host(args.lan_host, label="LAN host")
    validate_registry(registry)
    if not args.apply:
        write_registry(args.registry, registry, False)
        preview_access_renderer(registry)
        return 0
    try:
        write_registry(args.registry, registry, True)
        run_access_renderer(args.registry, apply=True)
    except Exception:
        write_registry(args.registry, previous, True)
        run_access_renderer(args.registry, apply=True)
        raise
    print(
        f"configured {args.provider} for {machine['id']}; canonical provider remains {access['provider']}"
    )
    return 0


def fleet_identity(machine: dict[str, Any]) -> str:
    fleet_shell = machine.get("fleet_shell")
    identity_file = fleet_shell.get("identity_file") if isinstance(fleet_shell, dict) else None
    if not isinstance(identity_file, str) or not identity_file.startswith("~/.ssh/"):
        raise MachineError(f"fleet-shell identity missing for {machine['id']}")
    return identity_file


def route_probe_command(
    source: dict[str, Any],
    target: dict[str, Any],
    host: str | None,
) -> list[str]:
    access = target["machine_access"]
    command = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "StrictHostKeyChecking=yes",
    ]
    if host:
        command.extend(["-o", f"HostName={host}"])
    command.extend([
        "-o", f"User={access['ssh_user']}",
        "-o", f"IdentityFile={fleet_identity(source)}",
        "-o", "IdentitiesOnly=yes",
        str(target["ssh_alias"]),
        "true",
    ])
    return command


def remote_route_probe(source: dict[str, Any], command: list[str]) -> list[str]:
    remote_command = shlex.join(command)
    if source.get("platform") == "macos":
        agent_lookup = (
            'agent_socket=$(/bin/launchctl print "gui/$(id -u)/com.openssh.ssh-agent" '
            "2>/dev/null | grep 'path = /var/run/com.apple.launchd.*Listeners' | "
            "tr -d '\\t' | cut -d' ' -f3 | sed -n '1p'); "
            'test -S "$agent_socket"; '
            f'SSH_AUTH_SOCK="$agent_socket" {remote_command}'
        )
        remote_command = agent_lookup
    return [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        str(source["ssh_alias"]),
        remote_command,
    ]


def verify_from_sources(
    registry: dict[str, Any],
    target: dict[str, Any],
    *,
    host: str | None,
    phase: str,
) -> None:
    local_id = current_machine_id()
    sources = [
        source
        for source in registry["machines"]
        if source.get("enabled") and source.get("id") != target.get("id")
    ]
    if not sources:
        raise MachineError(f"no enabled source can verify {target['id']}")
    for source in sources:
        command = route_probe_command(source, target, host)
        executed_command = (
            command
            if source.get("id") == local_id
            else remote_route_probe(source, command)
        )
        result = subprocess.run(
            executed_command,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=25,
        )
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unreachable"
            raise MachineError(
                f"{phase} failed from {source['id']} to {target['id']}: {detail}"
            )


def verify_route(registry: dict[str, Any], machine: dict[str, Any], host: str) -> None:
    verify_from_sources(
        registry,
        machine,
        host=host,
        phase="new provider route verification before switch",
    )


def verify_canonical(registry: dict[str, Any], machine: dict[str, Any]) -> None:
    verify_from_sources(
        registry,
        machine,
        host=None,
        phase="canonical SSH verification after switch",
    )


def command_access_switch(args: argparse.Namespace, registry: dict[str, Any]) -> int:
    machine = resolve_machine(registry, args.name, enabled=False)
    access = machine["machine_access"]
    target = access["providers"].get(args.provider)
    if not isinstance(target, dict) or target.get("state") != "configured":
        raise MachineError(
            f"{args.provider} is not configured for {machine['id']}; run `fleet machine access configure` first"
        )
    previous = json.loads(json.dumps(registry))
    old_provider = access["provider"]
    access["provider"] = args.provider
    validate_registry(registry)
    if not args.apply:
        write_registry(args.registry, registry, False)
        preview_access_renderer(registry)
        print(f"DRY RUN: verify {args.provider} route, then canonical alias {machine['ssh_alias']}")
        return 0
    if not args.skip_verify:
        verify_route(registry, machine, str(target["host"]))
    try:
        write_registry(args.registry, registry, True)
        run_access_renderer(args.registry, apply=True)
        if not args.skip_verify:
            verify_canonical(registry, machine)
    except Exception:
        write_registry(args.registry, previous, True)
        run_access_renderer(args.registry, apply=True)
        raise MachineError(
            f"provider switch failed; restored {machine['id']} to {old_provider}"
        )
    print(
        f"switched {machine['id']} from {old_provider} to {args.provider}; "
        "the previous provider remains configured for rollback"
    )
    return 0


def command_access(args: argparse.Namespace, registry: dict[str, Any]) -> int:
    if args.access_action == "render":
        run_access_renderer(
            args.registry,
            apply=args.apply,
            source_ids=args.target or None,
        )
        return 0
    if args.access_action == "configure":
        return command_access_configure(args, registry)
    if args.access_action == "switch":
        return command_access_switch(args, registry)
    if args.access_action == "inspect":
        if not ACCESS_INSPECTOR.is_file():
            raise MachineError(f"machine-access inspector missing: {ACCESS_INSPECTOR}")
        command = [
            sys.executable,
            str(ACCESS_INSPECTOR),
            args.name,
            "--registry",
            str(args.registry),
            "--attempts",
            str(args.attempts),
        ]
        if args.provider:
            command.extend(["--provider", args.provider])
        return subprocess.run(command).returncode
    raise MachineError(f"unsupported access action: {args.access_action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fleet machine", description=__doc__)
    parser.add_argument("--registry", type=Path, default=None, help="machine registry override")
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("startup", help="manage this Mac's login actions", add_help=False)

    init_parser = subparsers.add_parser("init", help="create a private registry with this machine as primary")
    init_parser.add_argument("--id", required=True)
    init_parser.add_argument("--display-name", required=True)
    init_parser.add_argument("--platform", choices=("macos", "linux"), required=True)
    init_parser.add_argument("--code-root", default="~/" + "Code")
    init_parser.add_argument("--vault-root", help="optional macOS Vault root")
    init_mode = init_parser.add_mutually_exclusive_group()
    init_mode.add_argument("--dry-run", action="store_true")
    init_mode.add_argument("--apply", action="store_true")

    setup_parser = subparsers.add_parser(
        "setup",
        help="prepare a disabled personal worker and an editable Codex onboarding handoff",
    )
    setup_parser.add_argument("--root", help=argparse.SUPPRESS)
    setup_parser.add_argument("--vault-root", help="optional Vault root when initializing the primary")
    setup_parser.add_argument("--yes", action="store_true", help="accept the registry preview")
    setup_parser.add_argument("--no-codex", action="store_true", help="print but do not open the Codex handoff")
    setup_mode = setup_parser.add_mutually_exclusive_group()
    setup_mode.add_argument("--dry-run", action="store_true")
    setup_mode.add_argument("--apply", action="store_true")

    worker_parser = subparsers.add_parser("register-worker", help="register an SSH worker")
    worker_parser.add_argument("--id", required=True)
    worker_parser.add_argument("--display-name", required=True)
    worker_parser.add_argument("--platform", choices=("macos", "linux"), required=True)
    worker_parser.add_argument("--ssh-alias", required=True)
    worker_parser.add_argument("--home", required=True)
    worker_parser.add_argument("--ssh-user", required=True)
    worker_parser.add_argument("--provider", choices=ACCESS_PROVIDERS, required=True)
    worker_parser.add_argument("--lan-host")
    worker_parser.add_argument("--mesh-host")
    worker_parser.add_argument("--identity-file", default="~/.ssh/codex_fleet_ed25519")
    worker_parser.add_argument(
        "--operation",
        choices=("new", "rebuilt", "replaced", "recovered"),
        default="new",
    )
    worker_parser.add_argument("--code-root", default="~/" + "Code")
    worker_parser.add_argument("--vault-root")
    worker_parser.add_argument("--vault-source")
    worker_parser.add_argument("--vault-read-only", action="store_true")
    worker_mode = worker_parser.add_mutually_exclusive_group()
    worker_mode.add_argument("--dry-run", action="store_true")
    worker_mode.add_argument("--apply", action="store_true")

    identify_parser = subparsers.add_parser("identify", help="store this machine's Fleet and optional Vault identity")
    identify_parser.add_argument("name")
    identify_mode = identify_parser.add_mutually_exclusive_group()
    identify_mode.add_argument("--dry-run", action="store_true")
    identify_mode.add_argument("--apply", action="store_true")

    list_parser = subparsers.add_parser("list", help="list reviewed machines")
    list_parser.add_argument("--json", action="store_true")

    status_parser = subparsers.add_parser("status", help="probe machine reachability")
    status_parser.add_argument("name", nargs="?")
    status_parser.add_argument("--json", action="store_true")

    ssh_parser = subparsers.add_parser("ssh", help="open SSH or forward a command")
    ssh_parser.add_argument("name")
    ssh_parser.add_argument("remote_command", nargs=argparse.REMAINDER)

    vnc_parser = subparsers.add_parser("vnc", help="open or manage VNC access")
    vnc_parser.add_argument("name")
    vnc_parser.add_argument("--no-open", action="store_true")
    vnc_parser.add_argument("--local-port", type=int)
    mode = vnc_parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--stop", action="store_true")

    access_parser = subparsers.add_parser("access", help="configure, render, or switch canonical access")
    access_subparsers = access_parser.add_subparsers(dest="access_action", required=True)

    configure_parser = access_subparsers.add_parser(
        "configure",
        help="store a verified provider route without changing the canonical provider",
    )
    configure_parser.add_argument("name")
    configure_parser.add_argument("provider", choices=ACCESS_PROVIDERS)
    configure_parser.add_argument("--host", required=True)
    configure_parser.add_argument("--lan-host")
    configure_parser.add_argument("--client-variant")
    configure_mode = configure_parser.add_mutually_exclusive_group()
    configure_mode.add_argument("--dry-run", action="store_true")
    configure_mode.add_argument("--apply", action="store_true")

    switch_parser = access_subparsers.add_parser(
        "switch",
        help="verify and atomically switch the canonical provider with rollback",
    )
    switch_parser.add_argument("name")
    switch_parser.add_argument("provider", choices=ACCESS_PROVIDERS)
    switch_parser.add_argument("--skip-verify", action="store_true")
    switch_mode = switch_parser.add_mutually_exclusive_group()
    switch_mode.add_argument("--dry-run", action="store_true")
    switch_mode.add_argument("--apply", action="store_true")

    render_parser = access_subparsers.add_parser(
        "render",
        help="render source-aware managed SSH includes across the enabled fleet",
    )
    render_parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="source machine ID to render; repeatable (default: every enabled machine)",
    )
    render_mode = render_parser.add_mutually_exclusive_group()
    render_mode.add_argument("--dry-run", action="store_true")
    render_mode.add_argument("--apply", action="store_true")

    inspect_parser = access_subparsers.add_parser(
        "inspect",
        help="report sanitized latency and selected-provider path evidence",
    )
    inspect_parser.add_argument("name")
    inspect_parser.add_argument("--provider", choices=ACCESS_PROVIDERS)
    inspect_parser.add_argument("--attempts", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "startup":
        import fleet_startup
        return fleet_startup.main(raw[1:])
    args = build_parser().parse_args(raw)
    if hasattr(args, "apply"):
        args.apply = not args.dry_run
    mutates_registry = args.action in {"init", "setup", "register-worker"} or (
        args.action == "access" and args.access_action in {"configure", "switch", "render"}
    )
    if args.registry is None:
        if mutates_registry:
            if DEFAULT_REGISTRY.is_file():
                require_primary(load_registry(DEFAULT_REGISTRY))
            source = installed_source(Path.home()) or (ROOT if (ROOT / "edit/settings").is_dir() else None)
            if source is None:
                raise MachineError("registry changes require the editable Fleet source on the primary")
            args.registry = source / "edit/settings/fleet/machines.json"
        else:
            args.registry = DEFAULT_REGISTRY
            if DEFAULT_REGISTRY.is_file():
                installed_registry = load_registry(DEFAULT_REGISTRY)
                identity = DEFAULT_MACHINE_ID_PATH.read_text(encoding="utf-8").strip() if DEFAULT_MACHINE_ID_PATH.is_file() else ""
                if identity == installed_registry["primary_machine_id"]:
                    source = installed_source(Path.home())
                    editable = source / "edit/settings/fleet/machines.json" if source else DEFAULT_REGISTRY
                    if editable.is_file():
                        args.registry = editable
    if mutates_registry and args.registry.exists():
        require_primary(load_registry(args.registry))
    if args.action == "init":
        return command_init(args)
    if args.action == "setup":
        return command_setup(args)
    registry = load_registry(args.registry)
    if args.action == "register-worker":
        return command_register_worker(args, registry)
    if args.action == "identify":
        return command_identify(args, registry)
    if args.action == "access":
        return command_access(args, registry)
    return {
        "list": command_list,
        "status": command_status,
        "ssh": command_ssh,
        "vnc": command_vnc,
    }[args.action](args, registry)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (MachineError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
