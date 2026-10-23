#!/usr/bin/env python3
"""Install and manage the exact user units owned by the cluster wizard."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

SERVICE = "ctx9-k3s-cluster-wizard.service"
TIMER = "ctx9-k3s-cluster-wizard.timer"

SERVICE_TEXT = """[Unit]
Description=Audit and maintain the K3s cluster
After=network-online.target

[Service]
Type=oneshot
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 %h/.agents/skills/k3s-cluster-wizard/scripts/audit.py run
TimeoutStartSec=4h
Nice=10

[Install]
WantedBy=default.target
"""

TIMER_TEXT = """[Unit]
Description=Run the K3s cluster wizard daily

[Timer]
OnCalendar=*-*-* 00:00:00 Africa/Johannesburg
Persistent=true
AccuracySec=1min
Unit=ctx9-k3s-cluster-wizard.service

[Install]
WantedBy=timers.target
"""


def systemctl(*args: str, check: bool = True) -> None:
    subprocess.run(["systemctl", "--user", *args], check=check)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["install", "status", "run-once", "disable", "uninstall"])
    command = parser.parse_args().command
    root = Path.home() / ".config/systemd/user"
    service_path, timer_path = root / SERVICE, root / TIMER
    if command == "install":
        root.mkdir(parents=True, exist_ok=True)
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
        for path, expected in ((service_path, SERVICE_TEXT), (timer_path, TIMER_TEXT)):
            if path.exists() and path.read_text() == expected:
                path.unlink()
        systemctl("daemon-reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
