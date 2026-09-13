#!/usr/bin/env python3
"""Manage fleet agent configuration, synchronization, updates, and packaging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from package_installer import InstallError, install, uninstall, verify
from package_export import ExportError, export as export_package, read_manifest, release_preflight
from package_layout import AGENTS_ROOT, ConfigurationError, active_instance_root, load_instance, resolve_dotted


VERSION = "0.2.9"
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
FLEET_COMMANDS = {
    "sync": SCRIPT_DIRECTORY / "sync_agents.py",
    "update": SCRIPT_DIRECTORY / "fleet_update.py",
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="fleet", description=__doc__)
    root.add_argument("--version", action="version", version=f"fleet {VERSION}")
    commands = root.add_subparsers(dest="command", required=True)
    config = commands.add_parser("config", help="inspect or validate installed instance configuration")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("path")
    get = config_commands.add_parser("get")
    get.add_argument("key")
    get.add_argument("--config-root", type=Path)
    validate = config_commands.add_parser("validate")
    validate.add_argument("--config-root", type=Path)
    for name in FLEET_COMMANDS:
        command = commands.add_parser(name, add_help=False)
        command.add_argument("args", nargs=argparse.REMAINDER)
    install_parser = commands.add_parser("install")
    install_parser.add_argument("--source", type=Path, default=AGENTS_ROOT)
    install_parser.add_argument("--home", type=Path, default=Path.home())
    install_parser.add_argument("--apply", action="store_true")
    install_parser.add_argument("--global-instructions", action="store_true")
    install_parser.add_argument("--claude-alias", action="store_true")
    install_parser.add_argument("--discovery-aliases", action="store_true")
    install_parser.add_argument("--machine-id")
    install_parser.add_argument("--code-root")
    install_parser.add_argument("--vault-root")
    install_parser.add_argument("--initialize-source", action="store_true")
    install_parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--home", type=Path, default=Path.home())
    verify_parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    uninstall_parser = commands.add_parser("uninstall")
    uninstall_parser.add_argument("--home", type=Path, default=Path.home())
    uninstall_parser.add_argument("--apply", action="store_true")
    uninstall_parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    export_parser = commands.add_parser("export")
    export_parser.add_argument("--destination", type=Path)
    export_parser.add_argument("--apply", action="store_true")
    release_parser = commands.add_parser("release")
    release_commands = release_parser.add_subparsers(dest="release_command", required=True)
    publish = release_commands.add_parser("publish")
    publish.add_argument("--destination", type=Path)
    publish.add_argument("--dry-run", action="store_true", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] in FLEET_COMMANDS:
        return subprocess.run([sys.executable, str(FLEET_COMMANDS[raw[0]]), *raw]).returncode
    args = parser().parse_args(raw)
    try:
        if args.command == "config":
            config_root = active_instance_root(getattr(args, "config_root", None))
            if args.config_command == "path":
                print(config_root)
                return 0
            instance = load_instance(config_root)
            if args.config_command == "validate":
                print(json.dumps({"ok": True, "config_root": str(config_root)}, indent=2))
                return 0
            value = resolve_dotted(instance, args.key)
            print(json.dumps(value, indent=2) if isinstance(value, (dict, list)) else str(value))
            return 0
        if args.command == "install":
            report = install(
                args.source,
                args.home,
                apply=args.apply,
                global_instructions=args.global_instructions,
                claude_alias=args.claude_alias,
                discovery_aliases=args.discovery_aliases,
                machine_id=args.machine_id,
                code_root=args.code_root,
                vault_root=args.vault_root,
                initialize_source=args.initialize_source,
            )
        elif args.command == "verify":
            report = verify(args.home)
        elif args.command == "uninstall":
            report = uninstall(args.home, apply=args.apply)
        elif args.command == "export":
            manifest = read_manifest()
            destination = args.destination or Path(str(manifest["default_export_root"]))
            report = export_package(destination, apply=args.apply)
        elif args.command == "release":
            manifest = read_manifest()
            destination = args.destination or Path(str(manifest["default_export_root"]))
            report = release_preflight(destination)
        else:
            raise InstallError(f"unsupported command: {args.command}")
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1
    except (ConfigurationError, ExportError, InstallError, OSError, ValueError) as exc:
        print(f"fleet: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
