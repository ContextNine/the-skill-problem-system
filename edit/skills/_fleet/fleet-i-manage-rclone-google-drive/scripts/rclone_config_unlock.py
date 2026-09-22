#!/usr/bin/env python3
"""Create, inspect, or read one machine's Rclone config unlock."""

from __future__ import annotations

import argparse
import hmac
import json
import re
import secrets
import shutil
import subprocess
import sys
from typing import Any


SAFE_MACHINE_ID = re.compile(r"[a-z0-9][a-z0-9-]*")
SERVICE = "ctx9-rclone-config-unlock"
PROVIDER = "rclone-config-unlock"
RESOURCE = "codefoldersync-backups"


class UnlockError(RuntimeError):
    """A safe failure that never contains the protected value."""


def require_machine_id(machine_id: str) -> None:
    if not SAFE_MACHINE_ID.fullmatch(machine_id):
        raise ValueError("unsafe machine id")


def lookup_command(machine_id: str, platform: str) -> list[str]:
    require_machine_id(machine_id)
    if platform == "darwin":
        return [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            machine_id,
            "-s",
            SERVICE,
            "-w",
        ]
    if platform.startswith("linux"):
        executable = shutil.which("secret-tool") or "/usr/bin/secret-tool"
        return [
            executable,
            "lookup",
            "ctx9-provider",
            PROVIDER,
            "ctx9-resource",
            RESOURCE,
            "ctx9-machine",
            machine_id,
        ]
    raise ValueError("unsupported platform")


def store_command(machine_id: str, platform: str) -> list[str]:
    require_machine_id(machine_id)
    if platform == "darwin":
        return [
            "/usr/bin/security",
            "add-generic-password",
            "-a",
            machine_id,
            "-s",
            SERVICE,
            "-w",
        ]
    if platform.startswith("linux"):
        executable = shutil.which("secret-tool") or "/usr/bin/secret-tool"
        return [
            executable,
            "store",
            "--label=CodeFolderSync Rclone config unlock",
            "ctx9-provider",
            PROVIDER,
            "ctx9-resource",
            RESOURCE,
            "ctx9-machine",
            machine_id,
        ]
    raise ValueError("unsupported platform")


def read_secret(machine_id: str, platform: str = sys.platform) -> str | None:
    try:
        completed = subprocess.run(
            lookup_command(machine_id, platform),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        raise UnlockError("Rclone config unlock custody is unavailable") from error
    value = completed.stdout.rstrip("\r\n")
    if completed.returncode != 0 or not value:
        return None
    return value


def store_secret(machine_id: str, value: str, platform: str = sys.platform) -> None:
    command = store_command(machine_id, platform)
    # `security -w` prompts twice when the value is omitted. Keeping the value on
    # stdin prevents it from entering argv, shell history, or process listings.
    protected_input = f"{value}\n{value}\n" if platform == "darwin" else f"{value}\n"
    try:
        completed = subprocess.run(
            command,
            input=protected_input,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UnlockError("Rclone config unlock custody is unavailable") from error
    if completed.returncode != 0:
        raise UnlockError("Rclone config unlock could not be stored")


def inspect(machine_id: str, platform: str = sys.platform) -> dict[str, Any]:
    return {
        "credential_id": "rclone-config-unlock",
        "machine_id": machine_id,
        "available": read_secret(machine_id, platform) is not None,
        "custody": "keychain" if platform == "darwin" else "secret-service",
    }


def generate(machine_id: str, apply: bool, platform: str = sys.platform) -> dict[str, Any]:
    if read_secret(machine_id, platform) is not None:
        return {
            "credential_id": "rclone-config-unlock",
            "machine_id": machine_id,
            "status": "existing-unverified",
            "changed": False,
        }
    if not apply:
        return {
            "credential_id": "rclone-config-unlock",
            "machine_id": machine_id,
            "status": "planned",
            "changed": False,
            "apply_required": True,
        }
    value = secrets.token_urlsafe(48)
    store_secret(machine_id, value, platform)
    accepted = read_secret(machine_id, platform)
    if accepted is None or not hmac.compare_digest(value, accepted):
        raise UnlockError("Rclone config unlock round trip failed")
    return {
        "credential_id": "rclone-config-unlock",
        "machine_id": machine_id,
        "status": "created",
        "changed": True,
        "verified": True,
    }


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("read", "inspect", "generate"):
        command = subparsers.add_parser(name)
        command.add_argument("--machine-id", required=True)
        if name == "generate":
            command.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    try:
        require_machine_id(arguments.machine_id)
        if arguments.command == "read":
            value = read_secret(arguments.machine_id)
            if value is None:
                raise UnlockError("Rclone config unlock is unavailable")
            sys.stdout.write(value + "\n")
        elif arguments.command == "inspect":
            emit(inspect(arguments.machine_id))
        else:
            emit(generate(arguments.machine_id, arguments.apply))
    except (UnlockError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
