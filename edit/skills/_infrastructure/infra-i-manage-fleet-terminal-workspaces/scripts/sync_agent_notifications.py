#!/usr/bin/env python3
"""Manage enabled or disabled workmux agent notifications across the fleet."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import plistlib
import re
import shlex
import subprocess
import sys
from typing import Any

import sync_terminal_profiles as terminal


SCHEMA_VERSION = 1
LAUNCH_AGENT_LABEL = "com.ctx9.workmux-notifications"
TERMINAL_NOTIFIER = "/opt/homebrew/bin/terminal-notifier"
WARP_PROCESS = "/Applications/Warp.app/Contents/MacOS/stable"
WARP_BUNDLE_ID = "dev.warp.Warp-Stable"
WARP_ICON = "/Applications/Warp.app/Contents/Resources/AppIcon.icns"
WORKSPACES = {machine_id: profile["name"] for machine_id, profile in terminal.PROFILES.items()}


def tool_path(machine: dict[str, Any]) -> str:
    return str(PurePosixPath(machine["home"]) / ".local/bin/workmux-notify")


def config_path(machine: dict[str, Any]) -> str:
    return str(PurePosixPath(machine["home"]) / ".config/workmux/notifications.json")


def state_path(machine: dict[str, Any]) -> str:
    return str(PurePosixPath(machine["home"]) / ".local/state/workmux/notifications")


def hook_path(machine: dict[str, Any], agent: str) -> str:
    home = PurePosixPath(machine["home"])
    return str(home / (".codex/hooks.json" if agent == "codex" else ".claude/settings.json"))


def codex_config_path(machine: dict[str, Any]) -> str:
    return str(PurePosixPath(machine["home"]) / ".codex/config.toml")


def hook_command(machine: dict[str, Any], agent: str) -> str:
    return f"{tool_path(machine)} enqueue --agent {agent} --event stop"


def managed_hook(command: str) -> dict[str, Any]:
    return {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 5,
            }
        ],
    }


def hook_commands(group: Any) -> list[str]:
    if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
        return []
    return [
        str(item.get("command"))
        for item in group["hooks"]
        if isinstance(item, dict) and isinstance(item.get("command"), str)
    ]


def merge_stop_hook(document: dict[str, Any], command: str) -> dict[str, Any]:
    updated = json.loads(json.dumps(document))
    hooks = updated.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    stop = hooks.setdefault("Stop", [])
    if not isinstance(stop, list):
        raise ValueError("hooks.Stop must be an array")
    signature = "workmux-notify " + command.split("workmux-notify ", 1)[1]
    stop[:] = [group for group in stop if not any(signature in value for value in hook_commands(group))]
    stop.append(managed_hook(command))
    return updated


def has_exact_hook(document: dict[str, Any], command: str) -> bool:
    hooks = document.get("hooks")
    if not isinstance(hooks, dict) or not isinstance(hooks.get("Stop"), list):
        return False
    matches = [value for group in hooks["Stop"] for value in hook_commands(group) if value == command]
    return len(matches) == 1


def has_managed_stop_hook(document: dict[str, Any], agent: str) -> bool:
    hooks = document.get("hooks")
    if not isinstance(hooks, dict) or not isinstance(hooks.get("Stop"), list):
        return False
    signature = f"workmux-notify enqueue --agent {agent} --event stop"
    return any(signature in value for group in hooks["Stop"] for value in hook_commands(group))


def remove_managed_stop_hook(document: dict[str, Any], agent: str) -> dict[str, Any]:
    updated = json.loads(json.dumps(document))
    hooks = updated.get("hooks")
    if not isinstance(hooks, dict) or not isinstance(hooks.get("Stop"), list):
        return updated
    signature = f"workmux-notify enqueue --agent {agent} --event stop"
    hooks["Stop"] = [group for group in hooks["Stop"] if not any(signature in value for value in hook_commands(group))]
    return updated


def parse_notify_command(text: str) -> list[str] | None:
    matches = re.findall(r"(?m)^notify\s*=\s*(\[[^\n]*\])\s*$", text)
    if len(matches) > 1:
        raise ValueError("multiple Codex notify settings")
    if not matches:
        return None
    value = ast.literal_eval(matches[0])
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError("Codex notify setting must be string array")
    return value


def merge_notify_command(text: str, command: list[str]) -> str:
    line = "notify = " + json.dumps(command)
    matches = list(re.finditer(r"(?m)^notify\s*=\s*\[[^\n]*\]\s*$", text))
    if len(matches) > 1:
        raise ValueError("multiple Codex notify settings")
    if matches:
        match = matches[0]
        updated = text[:match.start()] + line + text[match.end():]
    else:
        updated = line + "\n" + text
    return updated if updated.endswith("\n") else updated + "\n"


def remove_notify_command(text: str) -> str:
    matches = list(re.finditer(r"(?m)^notify\s*=\s*\[[^\n]*\]\s*$", text))
    if len(matches) > 1:
        raise ValueError("multiple Codex notify settings")
    if not matches:
        return text
    match = matches[0]
    end = match.end() + (1 if match.end() < len(text) and text[match.end()] == "\n" else 0)
    updated = text[:match.start()] + text[end:]
    return updated if not updated or updated.endswith("\n") else updated + "\n"


def without_managed_notify(
    command: list[str] | None, managed: list[str], saved_passthrough: list[str] | None
) -> list[str] | None:
    if command == managed:
        return saved_passthrough
    if command is None:
        return None
    for index, value in enumerate(command[:-1]):
        if value != "--previous-notify":
            continue
        try:
            previous = json.loads(command[index + 1])
        except json.JSONDecodeError:
            continue
        if previous == managed:
            return command[:index] + command[index + 2:]
    return command


def set_notify_command(text: str, command: list[str] | None) -> str:
    return merge_notify_command(text, command) if command else remove_notify_command(text)


def render_config(
    machine: dict[str, Any], fleet: list[dict[str, Any]], codex_passthrough: list[str] | None = None
) -> bytes:
    sources: list[dict[str, Any]] = []
    if machine["id"] == "primary":
        for source in fleet:
            item = {
                "id": source["id"],
                "name": source["display_name"],
                "workspace": WORKSPACES[source["id"]],
                "transport": source["transport"],
                "tool": tool_path(source),
            }
            if source["transport"] == "ssh":
                item["ssh_alias"] = source["ssh_alias"] + "-mesh"
            sources.append(item)
    config = {
        "schema_version": SCHEMA_VERSION,
        "enabled": True,
        "machine": {
            "id": machine["id"],
            "name": machine["display_name"],
            "workspace": WORKSPACES[machine["id"]],
        },
        "sources": sources,
    }
    if machine["id"] == "primary":
        config["cmux_path"] = "/opt/homebrew/bin/cmux"
        config["warp"] = {
            "bundle_id": WARP_BUNDLE_ID,
            "icon": WARP_ICON,
            "process": WARP_PROCESS,
            "terminal_notifier": TERMINAL_NOTIFIER,
        }
    if codex_passthrough:
        config["codex_notify_passthrough"] = codex_passthrough
    return (json.dumps(config, indent=2, sort_keys=True) + "\n").encode()


def render_disabled_config(machine: dict[str, Any], codex_passthrough: list[str] | None = None) -> bytes:
    config: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "enabled": False,
        "machine": {
            "id": machine["id"],
            "name": machine["display_name"],
            "workspace": WORKSPACES[machine["id"]],
        },
        "sources": [],
    }
    if codex_passthrough:
        config["codex_notify_passthrough"] = codex_passthrough
    return (json.dumps(config, indent=2, sort_keys=True) + "\n").encode()


def launch_agent(machine: dict[str, Any]) -> tuple[str, bytes]:
    home = PurePosixPath(machine["home"])
    path = str(home / f"Library/LaunchAgents/{LAUNCH_AGENT_LABEL}.plist")
    logs = str(home / "Library/Logs")
    value = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [tool_path(machine), "poll"],
        "RunAtLoad": True,
        "StartInterval": 15,
        "ProcessType": "Background",
        "StandardOutPath": f"{logs}/workmux-notifications.log",
        "StandardErrorPath": f"{logs}/workmux-notifications.error.log",
    }
    return path, plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=False)


def load_document(host: terminal.Host, path: str) -> dict[str, Any]:
    raw = host.read(path)
    if raw is None:
        return {}
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def desired_documents(host: terminal.Host, machine: dict[str, Any]) -> list[tuple[str, bytes]]:
    documents: list[tuple[str, bytes]] = []
    codex_path = hook_path(machine, "codex")
    codex = remove_managed_stop_hook(load_document(host, codex_path), "codex")
    documents.append((codex_path, (json.dumps(codex, indent=2, sort_keys=True) + "\n").encode()))
    claude_path = hook_path(machine, "claude")
    claude = merge_stop_hook(load_document(host, claude_path), hook_command(machine, "claude"))
    documents.append((claude_path, (json.dumps(claude, indent=2, sort_keys=True) + "\n").encode()))
    return documents


def disabled_documents(host: terminal.Host, machine: dict[str, Any]) -> list[tuple[str, bytes]]:
    documents: list[tuple[str, bytes]] = []
    for agent in ("codex", "claude"):
        path = hook_path(machine, agent)
        document = remove_managed_stop_hook(load_document(host, path), agent)
        documents.append((path, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()))
    return documents


def bootstrap_launch_agent(host: terminal.Host, path: str) -> None:
    uid = host.command("id -u").stdout.strip()
    host.command(f"mkdir -p \"$HOME/Library/Logs\"; launchctl bootout gui/{uid}/{LAUNCH_AGENT_LABEL} >/dev/null 2>&1 || true; launchctl bootstrap gui/{uid} {path}")


def disable_launch_agent(host: terminal.Host, path: str, stamp: str) -> None:
    uid = host.command("id -u").stdout.strip()
    host.command(f"launchctl bootout gui/{uid}/{LAUNCH_AGENT_LABEL} >/dev/null 2>&1 || true")
    if host.read(path) is not None:
        host.command(f"mv {shlex.quote(path)} {shlex.quote(path + '.disabled-' + stamp)}")


def archive_notification_state(host: terminal.Host, path: str, stamp: str) -> None:
    quoted = shlex.quote(path)
    archived = shlex.quote(path + ".disabled-" + stamp)
    host.command(
        f"if test -d {quoted} && test -n \"$(find {quoted} -type f -print -quit)\"; "
        f"then mv {quoted} {archived}; fi"
    )


def launch_agent_loaded(host: terminal.Host) -> bool:
    uid = host.command("id -u").stdout.strip()
    return host.command(f"launchctl print gui/{uid}/{LAUNCH_AGENT_LABEL}", check=False).returncode == 0


def configure_machine(
    machine: dict[str, Any], fleet: list[dict[str, Any]], *, state: str, apply: bool, verify: bool, stamp: str
) -> bool:
    host = terminal.Host(machine)
    failures: list[str] = []
    python = host.command("python3 --version", check=False)
    if python.returncode != 0:
        failures.append("python3 missing")

    asset = terminal.skill_root() / "assets/terminal-workspaces/workmux-notify"
    existing_config = (host.read(codex_config_path(machine)) or b"").decode("utf-8")
    existing_notify = parse_notify_command(existing_config)
    managed_notify = [tool_path(machine), "codex-notify"]
    current_notifier_config = host.read(config_path(machine))
    saved_passthrough: list[str] | None = None
    if current_notifier_config:
        current_value = json.loads(current_notifier_config)
        candidate = current_value.get("codex_notify_passthrough") if isinstance(current_value, dict) else None
        if isinstance(candidate, list) and candidate and all(isinstance(item, str) for item in candidate):
            saved_passthrough = candidate
    if state == "enabled":
        passthrough = saved_passthrough if existing_notify == managed_notify else existing_notify
        wanted_codex_config = merge_notify_command(existing_config, managed_notify).encode()
        wanted_notifier_config = render_config(machine, fleet, passthrough)
    else:
        restored_notify = without_managed_notify(existing_notify, managed_notify, saved_passthrough)
        passthrough = saved_passthrough if existing_notify == managed_notify else None
        wanted_codex_config = set_notify_command(existing_config, restored_notify).encode()
        wanted_notifier_config = render_disabled_config(machine, passthrough)
    wanted: list[tuple[str, bytes, int]] = [
        (tool_path(machine), asset.read_bytes(), 0o755),
        (config_path(machine), wanted_notifier_config, 0o600),
        (codex_config_path(machine), wanted_codex_config, 0o600),
        *[(path, data, 0o600) for path, data in (
            desired_documents(host, machine)
            if state == "enabled"
            else disabled_documents(host, machine)
        )],
    ]
    if machine["id"] == "primary" and state == "enabled":
        path, data = launch_agent(machine)
        wanted.append((path, data, 0o644))

    if apply and machine["id"] == "primary" and state == "disabled":
        disable_launch_agent(host, launch_agent(machine)[0], stamp)

    for path, data, mode in wanted:
        actual = host.read(path)
        if actual == data:
            print(f"{machine['id']}: match {path}")
            continue
        print(f"{machine['id']}: {'missing' if actual is None else 'different'} {path}")
        if apply:
            host.deploy(path, data, mode, stamp)
            if host.read(path) != data:
                failures.append(f"post-install mismatch: {path}")
        elif verify:
            failures.append(f"config mismatch: {path}")

    if apply and state == "disabled" and not failures:
        archive_notification_state(host, state_path(machine), stamp)

    if apply and machine["id"] == "primary" and state == "enabled" and not failures:
        bootstrap_launch_agent(host, launch_agent(machine)[0])
    if (apply or verify) and machine["id"] == "primary":
        loaded = launch_agent_loaded(host)
        if state == "enabled" and not loaded:
            failures.append("LaunchAgent not loaded")
        if state == "disabled" and loaded:
            failures.append("LaunchAgent still loaded")
        if state == "disabled" and host.read(launch_agent(machine)[0]) is not None:
            failures.append("LaunchAgent plist still active")

    if apply or verify:
        claude = load_document(host, hook_path(machine, "claude"))
        has_claude_hook = has_managed_stop_hook(claude, "claude")
        if state == "enabled" and not has_claude_hook:
            failures.append("claude Stop hook missing")
        if state == "disabled" and has_claude_hook:
            failures.append("claude Stop hook still present")
        codex_toml = (host.read(codex_config_path(machine)) or b"").decode("utf-8")
        codex_notify = parse_notify_command(codex_toml)
        if state == "enabled" and codex_notify != managed_notify:
            failures.append("codex notify command missing")
        if state == "disabled" and without_managed_notify(codex_notify, managed_notify, None) != codex_notify:
            failures.append("codex notify command still chains workmux")
        status = host.command(f"{tool_path(machine)} status", check=False)
        if status.returncode != 0:
            failures.append("notifier status failed: " + status.stderr.strip())
        elif json.loads(status.stdout).get("enabled") != (state == "enabled"):
            failures.append("notifier enabled state mismatch")
        if state == "enabled" and machine["id"] == "primary" and host.command(f"test -x {TERMINAL_NOTIFIER}", check=False).returncode != 0:
            failures.append("terminal-notifier missing")

    for failure in failures:
        print(f"{machine['id']}: FAIL {failure}")
    return not failures


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--inventory", type=Path)
    result.add_argument("--target", action="append", default=[])
    result.add_argument("--state", choices=("enabled", "disabled"), default="disabled")
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    inventory = terminal.load_inventory(args.inventory or terminal.default_inventory())
    fleet = terminal.select_devices(inventory)
    machines = terminal.select_devices(inventory, set(args.target) if args.target else None)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print("mode=" + ("apply" if args.apply else "verify" if args.verify else "dry-run"))
    print("state=" + args.state)
    print("targets=" + ",".join(machine["id"] for machine in machines))
    okay = True
    for machine in machines:
        okay = configure_machine(machine, fleet, state=args.state, apply=args.apply, verify=args.verify, stamp=stamp) and okay
    return 0 if okay or (not args.apply and not args.verify) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
