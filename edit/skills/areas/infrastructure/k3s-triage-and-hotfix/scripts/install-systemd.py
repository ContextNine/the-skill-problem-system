#!/usr/bin/env python3
"""Install and manage the exact user units owned by K3s triage."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

SERVICE = "ctx9-k3s-triage-and-hotfix.service"
TIMER = "ctx9-k3s-triage-and-hotfix.timer"

SERVICE_TEXT = """[Unit]
Description=Collect K3s errors and investigate services with the configured coding agent
After=network-online.target

[Service]
Type=oneshot
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 %h/.agents/skills/k3s-triage-and-hotfix/scripts/triage.py run
TimeoutStartSec=2h
Nice=10

[Install]
WantedBy=default.target
"""

TIMER_TEXT = """[Unit]
Description=Run K3s error triage every 25 minutes

[Timer]
OnBootSec=3min
OnUnitInactiveSec=25min
AccuracySec=30s
Unit=ctx9-k3s-triage-and-hotfix.service

[Install]
WantedBy=timers.target
"""


def systemctl(*args: str, check: bool = True) -> None:
    subprocess.run(["systemctl", "--user", *args], check=check)


def paths() -> tuple[Path, Path]:
    root = Path.home() / ".config/systemd/user"
    return root / SERVICE, root / TIMER


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["install", "status", "run-once", "disable", "uninstall"])
    command = parser.parse_args().command
    service_path, timer_path = paths()
    if command == "install":
        service_path.parent.mkdir(parents=True, exist_ok=True)
        service_path.write_text(SERVICE_TEXT)
        timer_path.write_text(TIMER_TEXT)
        systemctl("daemon-reload")
        systemctl("enable", "--now", TIMER)
    elif command == "status":
        systemctl("status", TIMER, "--no-pager", check=False)
        systemctl("list-timers", TIMER, "--no-pager", check=False)
    elif command == "run-once":
        systemctl("start", SERVICE)
    elif command == "disable":
        systemctl("disable", "--now", TIMER, check=False)
    else:
        systemctl("disable", "--now", TIMER, check=False)
        for path in (service_path, timer_path):
            if path.exists() and path.read_text() in {SERVICE_TEXT, TIMER_TEXT}:
                path.unlink()
        systemctl("daemon-reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

