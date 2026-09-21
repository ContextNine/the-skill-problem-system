#!/usr/bin/env python3
"""Manage the explicitly approved Worker Mac closed-display sleep fallback."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys
import tempfile
from typing import Any


LABEL = "com.ctx9.worker.prevent-system-sleep"
PLIST_NAME = f"{LABEL}.plist"
REMOTE_STAGING_PATH = f"/tmp/{PLIST_NAME}"


class ServiceError(RuntimeError):
    pass


def load_machine(path: Path, machine_id: str) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServiceError(f"cannot read registry {path}: {exc}") from exc
    matches = [item for item in registry.get("machines", []) if item.get("id") == machine_id]
    if len(matches) != 1:
        raise ServiceError(f"machine {machine_id!r} did not resolve exactly once")
    machine = matches[0]
    if machine.get("role") != "worker" or machine.get("platform") != "macos":
        raise ServiceError("sleep fallback requires a registered macOS worker")
    if machine.get("transport") != "ssh" or not isinstance(machine.get("ssh_alias"), str):
        raise ServiceError("sleep fallback currently requires a registered SSH worker")
    if not isinstance(machine.get("home"), str):
        raise ServiceError("worker home is missing")
    return machine


def plist_bytes() -> bytes:
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": ["/usr/bin/caffeinate", "-s"],
            "RunAtLoad": True,
            "KeepAlive": True,
            "ProcessType": "Background",
        },
        fmt=plistlib.FMT_XML,
        sort_keys=True,
    )


def target_prefix(machine: dict[str, Any]) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        str(machine["ssh_alias"]),
    ]


def run_target(
    machine: dict[str, Any],
    argv: list[str],
    *,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*target_prefix(machine), shlex.join(argv)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def target_paths(machine: dict[str, Any]) -> tuple[str, str]:
    launchagents = f"{machine['home']}/Library/LaunchAgents"
    return launchagents, f"{launchagents}/{PLIST_NAME}"


def target_uid(machine: dict[str, Any]) -> str:
    result = run_target(machine, ["id", "-u"])
    uid = result.stdout.strip()
    if result.returncode != 0 or not uid.isdigit():
        raise ServiceError("could not resolve the worker user ID")
    return uid


def target_digest(machine: dict[str, Any], path: str) -> str | None:
    result = run_target(machine, ["/usr/bin/shasum", "-a", "256", path])
    if result.returncode != 0:
        return None
    value = result.stdout.split(maxsplit=1)[0]
    return value if len(value) == 64 else None


def service_status(machine: dict[str, Any], desired_digest: str) -> dict[str, Any]:
    _, plist_path = target_paths(machine)
    uid = target_uid(machine)
    domain = f"gui/{uid}/{LABEL}"
    loaded = run_target(machine, ["launchctl", "print", domain]).returncode == 0
    process = run_target(machine, ["pgrep", "-f", "^/usr/bin/caffeinate -s$"]).returncode == 0
    assertions = run_target(machine, ["pmset", "-g", "assertions"])
    prevents_sleep = (
        assertions.returncode == 0
        and "PreventSystemSleep" in assertions.stdout
        and "caffeinate" in assertions.stdout
    )
    installed_digest = target_digest(machine, plist_path)
    return {
        "label": LABEL,
        "plist_path": plist_path,
        "installed": installed_digest == desired_digest,
        "loaded": loaded,
        "process_running": process,
        "prevent_system_sleep": prevents_sleep,
    }


def apply_service(machine: dict[str, Any], payload: bytes, digest: str) -> dict[str, Any]:
    launchagents, plist_path = target_paths(machine)
    existing_digest = target_digest(machine, plist_path)
    if existing_digest is not None and existing_digest != digest:
        raise ServiceError(f"refusing to replace unmanaged file at {plist_path}")

    with tempfile.TemporaryDirectory(prefix="ctx9-worker-sleep-") as temp_dir:
        local_path = Path(temp_dir) / PLIST_NAME
        local_path.write_bytes(payload)
        copied = subprocess.run(
            ["scp", "-q", str(local_path), f"{machine['ssh_alias']}:{REMOTE_STAGING_PATH}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
        )
    if copied.returncode != 0:
        raise ServiceError("could not stage the managed LaunchAgent")
    if target_digest(machine, REMOTE_STAGING_PATH) != digest:
        raise ServiceError("staged LaunchAgent checksum mismatch")
    if run_target(machine, ["/usr/bin/plutil", "-lint", REMOTE_STAGING_PATH]).returncode != 0:
        raise ServiceError("staged LaunchAgent failed plist validation")
    if run_target(machine, ["mkdir", "-p", launchagents]).returncode != 0:
        raise ServiceError("could not create the worker LaunchAgents folder")
    if run_target(machine, ["install", "-m", "600", REMOTE_STAGING_PATH, plist_path]).returncode != 0:
        raise ServiceError("could not install the managed LaunchAgent")

    uid = target_uid(machine)
    domain = f"gui/{uid}/{LABEL}"
    if run_target(machine, ["launchctl", "print", domain]).returncode == 0:
        run_target(machine, ["launchctl", "bootout", domain])
    bootstrapped = run_target(machine, ["launchctl", "bootstrap", f"gui/{uid}", plist_path])
    if bootstrapped.returncode != 0:
        raise ServiceError("launchd did not bootstrap the managed sleep service")
    if run_target(machine, ["launchctl", "kickstart", "-k", domain]).returncode != 0:
        raise ServiceError("launchd did not start the managed sleep service")
    run_target(machine, ["rm", "-f", REMOTE_STAGING_PATH])

    status = service_status(machine, digest)
    if not all(
        status[key]
        for key in ("installed", "loaded", "process_running", "prevent_system_sleep")
    ):
        raise ServiceError(f"managed sleep service verification failed: {status}")
    return status


def remove_service(machine: dict[str, Any], digest: str) -> dict[str, Any]:
    _, plist_path = target_paths(machine)
    existing_digest = target_digest(machine, plist_path)
    if existing_digest is not None and existing_digest != digest:
        raise ServiceError(f"refusing to remove unmanaged file at {plist_path}")
    uid = target_uid(machine)
    domain = f"gui/{uid}/{LABEL}"
    if run_target(machine, ["launchctl", "print", domain]).returncode == 0:
        run_target(machine, ["launchctl", "bootout", domain])
    if existing_digest is not None and run_target(machine, ["rm", "-f", plist_path]).returncode != 0:
        raise ServiceError("could not remove the managed LaunchAgent")
    return service_status(machine, digest)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("machine_id")
    parser.add_argument("--registry", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--remove", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        machine = load_machine(args.registry, args.machine_id)
        payload = plist_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if args.apply:
            result = {"mode": "apply", **apply_service(machine, payload, digest)}
        elif args.verify:
            result = {"mode": "verify", **service_status(machine, digest)}
        elif args.remove:
            result = {"mode": "remove", **remove_service(machine, digest)}
        else:
            _, plist_path = target_paths(machine)
            result = {
                "mode": "preview",
                "machine_id": args.machine_id,
                "label": LABEL,
                "plist_path": plist_path,
                "program_arguments": ["/usr/bin/caffeinate", "-s"],
                "sha256": digest,
            }
        print(json.dumps(result, indent=2))
        return 0
    except (ServiceError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
