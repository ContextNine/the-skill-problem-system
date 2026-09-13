#!/usr/bin/env python3
"""Print one machine's Rclone config password from native protected custody."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys


SAFE_MACHINE_ID = re.compile(r"[a-z0-9][a-z0-9-]*")


def command_for(machine_id: str, platform: str) -> list[str]:
    if not SAFE_MACHINE_ID.fullmatch(machine_id):
        raise ValueError("unsafe machine id")
    if platform == "darwin":
        return [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            machine_id,
            "-s",
            "ctx9-rclone-config-unlock",
            "-w",
        ]
    if platform.startswith("linux"):
        executable = shutil.which("secret-tool") or "/usr/bin/secret-tool"
        return [
            executable,
            "lookup",
            "ctx9-provider",
            "rclone-config-unlock",
            "ctx9-resource",
            "codefoldersync-backups",
            "ctx9-machine",
            machine_id,
        ]
    raise ValueError("unsupported platform")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: rclone_config_unlock.py <machine-id>", file=sys.stderr)
        return 2
    try:
        command = command_for(sys.argv[1], sys.platform)
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except (OSError, ValueError):
        print("Rclone config unlock is unavailable", file=sys.stderr)
        return 1
    value = completed.stdout.rstrip("\r\n")
    if completed.returncode != 0 or not value:
        print("Rclone config unlock is unavailable", file=sys.stderr)
        return 1
    sys.stdout.write(value + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

