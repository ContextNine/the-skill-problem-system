"""Fleet entry points for existing workspace and terminal controllers."""

from __future__ import annotations

import argparse
import subprocess
import sys

from fleet_machine import DEFAULT_REGISTRY, load_registry, require_primary, skill_script


def main(argv: list[str]) -> int:
    group, *arguments = argv
    if group == "workspaces":
        script = skill_script("fleet-i-sync-code-workspaces", "sync_code_workspaces.py")
        return subprocess.run([sys.executable, str(script), *arguments]).returncode

    scripts = {
        "profiles": "sync_terminal_profiles.py",
        "cmux": "configure_cmux_machine_workspaces.py",
        "warp": "configure_warp_machine_workspaces.py",
    }
    parser = argparse.ArgumentParser(prog="fleet terminal", description="Manage fleet terminal profiles and primary-host layouts. Controllers preview by default; use --apply or --verify.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in scripts:
        commands.add_parser(name, add_help=False)
    if not arguments or arguments[0] in {"--help", "-h"}:
        parser.print_help()
        return 0
    if arguments[0] not in scripts:
        parser.error(f"unknown terminal command: {arguments[0]}")
    if not {"--help", "-h"}.intersection(arguments[1:]):
        require_primary(load_registry(DEFAULT_REGISTRY))
    script = skill_script("fleet-i-manage-terminal-workspaces", scripts[arguments[0]])
    return subprocess.run([sys.executable, str(script), *arguments[1:]]).returncode
