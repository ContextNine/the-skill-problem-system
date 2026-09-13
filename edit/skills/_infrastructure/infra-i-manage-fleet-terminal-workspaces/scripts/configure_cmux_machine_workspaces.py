#!/usr/bin/env python3
"""Plan, apply, and verify Primary machine cmux fleet workspace layout."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


def inventory_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "_system/agents/edit/settings/fleet/machines.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("private machine registry not found from skill path")


INVENTORY_PATH = inventory_path()
INVENTORY = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def load_workspaces() -> list[dict[str, Any]]:
    workspaces: list[dict[str, Any]] = []
    for machine in INVENTORY.get("machines", []):
        terminal = machine.get("terminal_profile")
        if not machine.get("enabled") or not isinstance(terminal, dict):
            continue
        profile: dict[str, Any] = {
            "id": machine["id"],
            "title": machine["display_name"],
            "color": terminal["accent"],
            "description": terminal["cmux_description"],
            "transport": machine["transport"],
            "keep_titles": tuple(terminal.get("keep_titles", ["main"])),
        }
        if machine["transport"] == "ssh":
            profile["ssh_alias"] = machine["ssh_alias"]
            profile["remote_workmux"] = str(PurePosixPath(machine["home"]) / ".local/bin/workmux")
            if terminal.get("remote_path"):
                profile["remote_path"] = terminal["remote_path"]
        workspaces.append(profile)
    return workspaces


WORKSPACES = load_workspaces()
MARKER_START = "// >>> workmux compact sidebar >>>"
MARKER_END = "// <<< workmux compact sidebar <<<"
COMMANDS_MARKER_START = "// >>> workmux saved commands >>>"
COMMANDS_MARKER_END = "// <<< workmux saved commands <<<"
SIDEBAR_BLOCK = """  // >>> workmux compact sidebar >>>
  "sidebar": {
    "showNotificationMessage": false,
    "showWorkspaceDescription": false,
    "showBranchDirectory": false,
    "showLog": false,
    "showPorts": false,
    "branchLayout": "inline",
    "pathLastSegmentOnly": true,
    "stackBranchDirectory": false,
    "hideAllDetails": true
  },
  // <<< workmux compact sidebar <<<"""
RECONNECT_HELPER_NAME = "workmux-cmux-attach"
RECONNECT_AGENT_LABEL = "com.ctx9.workmux-cmux-attach"


def select_profiles(targets: list[str] | None = None) -> list[dict[str, Any]]:
    if not targets:
        return WORKSPACES
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    by_id = {str(profile["id"]): profile for profile in WORKSPACES}
    for target in targets:
        if target not in by_id:
            raise ValueError(f"unknown enabled terminal profile id: {target}")
        if target not in seen:
            selected.append(by_id[target])
            seen.add(target)
    return selected


def run(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check, timeout=120)


def cmux(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["cmux", *args], check=check)


def flatten_workspaces(tree: dict[str, Any]) -> list[dict[str, Any]]:
    return [workspace for window in tree.get("windows", []) for workspace in window.get("workspaces", [])]


def surfaces(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    return [surface for pane in workspace.get("panes", []) for surface in pane.get("surfaces", [])]


def choose_surface(workspace: dict[str, Any], preferred_titles: tuple[str, ...]) -> dict[str, Any] | None:
    candidates = surfaces(workspace)
    for title in preferred_titles:
        for surface in candidates:
            if surface.get("title") == title and surface.get("type") == "terminal":
                return surface
    return next((surface for surface in candidates if surface.get("type") == "terminal"), None)


def plan_layout(tree: dict[str, Any]) -> list[dict[str, Any]]:
    existing = flatten_workspaces(tree)
    actions: list[dict[str, Any]] = []
    migration_titles = {profile["title"] + " workmux migration" for profile in WORKSPACES if profile["transport"] == "ssh"}
    for profile in WORKSPACES:
        matches = [workspace for workspace in existing if workspace.get("title") == profile["title"]]
        if len(matches) > 1:
            raise ValueError(f"duplicate cmux workspace: {profile['title']}")
        if not matches:
            actions.append({"action": "create-workspace", "profile": profile})
            continue
        workspace = matches[0]
        keep = choose_surface(workspace, profile["keep_titles"])
        if keep is None:
            actions.append({"action": "create-surface", "workspace": workspace["ref"], "profile": profile})
        else:
            actions.append({"action": "retain-surface", "workspace": workspace["ref"], "surface": keep["ref"], "profile": profile})
            for extra in surfaces(workspace):
                if extra["ref"] != keep["ref"]:
                    actions.append({"action": "close-surface", "workspace": workspace["ref"], "surface": extra["ref"], "title": extra.get("title")})
    for workspace in existing:
        if workspace.get("title") == "Machines":
            actions.append({"action": "close-workspace", "workspace": workspace["ref"], "title": "Machines"})
        elif workspace.get("title") in migration_titles:
            actions.append({"action": "resume-migration", "workspace": workspace["ref"], "title": workspace.get("title")})
        elif workspace.get("title") not in {profile["title"] for profile in WORKSPACES}:
            actions.append({"action": "unexpected-workspace", "workspace": workspace["ref"], "title": workspace.get("title")})
    return actions


def replace_marker_block(text: str, start_marker: str, end_marker: str, block: str) -> str | None:
    start = text.find(start_marker)
    end = text.find(end_marker)
    if (start == -1) != (end == -1) or (start != -1 and end < start):
        raise ValueError(f"malformed marker block: {start_marker}")
    if start != -1:
        start = text.rfind("\n", 0, start) + 1
        end += len(end_marker)
        return text[:start] + block + text[end:]
    return None


def insert_after_schema_version(text: str, block: str) -> str:
    match = re.search(r'(?m)^([ \t]*"schemaVersion"[ \t]*:[ \t]*1[ \t]*,[ \t]*)$', text)
    if not match:
        raise ValueError("cmux schemaVersion 1 line not found")
    return text[: match.end()] + "\n" + block + text[match.end() :]


def saved_commands_block(home: Path | None = None) -> str:
    root = home or Path.home()
    close = '/opt/homebrew/bin/cmux close-workspace --workspace "$CMUX_WORKSPACE_ID" >/dev/null 2>&1'
    reconnect = f"{root}/.local/bin/{RECONNECT_HELPER_NAME}; status=$?; {close}; exit $status"
    open_warp = f"/usr/bin/open 'warp://launch/Machine%20Workspaces'; status=$?; {close}; exit $status"

    def item(name: str, description: str, keywords: list[str], workspace: str, surface: str, command: str) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "keywords": keywords,
            "workspace": {
                "name": workspace,
                "cwd": str(root),
                "layout": {
                    "pane": {
                        "surfaces": [
                            {
                                "type": "terminal",
                                "name": surface,
                                "command": command,
                                "focus": True,
                            }
                        ]
                    }
                },
            },
        }

    values = [
        item(
            "Reconnect machine tmux",
            "Reconnect managed remote cmux surfaces to durable workmux sessions",
            ["ssh", "tmux", "workmux", "machines"],
            "Workmux Reconnect",
            "reconnect",
            reconnect,
        ),
        item(
            "Open Warp Machine Workspaces",
            "Open Warp's managed machine launch configuration",
            ["warp", "machines", "workspace"],
            "Open Warp Machines",
            "open-warp",
            open_warp,
        ),
    ]
    payload = json.dumps(values, indent=4, ensure_ascii=False)
    indented = "\n".join("  " + line for line in payload.splitlines())
    return (
        f"  {COMMANDS_MARKER_START}\n"
        f'  "commands": {indented.lstrip()},\n'
        f"  {COMMANDS_MARKER_END}"
    )


def update_cmux_json(text: str, home: Path | None = None) -> str:
    sidebar = replace_marker_block(text, MARKER_START, MARKER_END, SIDEBAR_BLOCK)
    updated = sidebar if sidebar is not None else insert_after_schema_version(text, SIDEBAR_BLOCK)
    command_block = saved_commands_block(home)
    commands = replace_marker_block(updated, COMMANDS_MARKER_START, COMMANDS_MARKER_END, command_block)
    if commands is not None:
        return commands
    if re.search(r'(?m)^[ \t]*"commands"[ \t]*:', updated):
        raise ValueError("unmanaged top-level cmux commands already exist")
    return insert_after_schema_version(updated, command_block)


def atomic_update(path: Path, text: str, stamp: str, mode: int = 0o644) -> Path | None:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current == text:
        if path.exists() and path.stat().st_mode & 0o777 != mode:
            path.chmod(mode)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = Path(str(path) + ".backup-" + stamp)
    if path.exists():
        shutil.copy2(path, backup)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.chmod(mode)
    temporary.replace(path)
    return backup if backup.exists() else None


def reconnect_helper_asset() -> Path:
    return Path(__file__).parent.parent / "assets/terminal-workspaces" / RECONNECT_HELPER_NAME


def reconnect_helper_path() -> Path:
    return Path.home() / ".local/bin" / RECONNECT_HELPER_NAME


def runtime_config_path() -> Path:
    return Path.home() / ".config/workmux/machines.json"


def runtime_config_text() -> str:
    return json.dumps(INVENTORY, indent=2, ensure_ascii=False) + "\n"


def reconnect_agent_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{RECONNECT_AGENT_LABEL}.plist"


def install_reconnect_helper(stamp: str) -> None:
    helper = reconnect_helper_path()
    helper.parent.mkdir(parents=True, exist_ok=True)
    atomic_update(helper, reconnect_helper_asset().read_text(encoding="utf-8"), stamp, 0o755)
    atomic_update(runtime_config_path(), runtime_config_text(), stamp, 0o600)


def disable_reconnect_agent(stamp: str) -> Path | None:
    agent = reconnect_agent_path()
    domain = f"gui/{run(['id', '-u']).stdout.strip()}"
    cmux_agent = f"{domain}/{RECONNECT_AGENT_LABEL}"
    run(["launchctl", "bootout", cmux_agent], check=False)
    if not agent.exists():
        return None
    backup = Path(str(agent) + ".backup-" + stamp)
    shutil.copy2(agent, backup)
    agent.unlink()
    return backup


def verify_reconnect_policy() -> list[str]:
    errors: list[str] = []
    helper = reconnect_helper_path()
    runtime = runtime_config_path()
    agent = reconnect_agent_path()
    if not helper.exists() or helper.read_bytes() != reconnect_helper_asset().read_bytes():
        errors.append("Primary machine: cmux workmux reconnect helper differs")
    elif helper.stat().st_mode & 0o777 != 0o755:
        errors.append("Primary machine: cmux workmux reconnect helper mode differs")
    if not runtime.exists() or runtime.read_text(encoding="utf-8") != runtime_config_text():
        errors.append("Primary machine: workmux runtime machine config differs")
    elif runtime.stat().st_mode & 0o777 != 0o600:
        errors.append("Primary machine: workmux runtime machine config mode differs")
    if agent.exists():
        errors.append("Primary machine: cmux workmux reconnect LaunchAgent plist still exists")
    domain = f"gui/{run(['id', '-u']).stdout.strip()}/{RECONNECT_AGENT_LABEL}"
    if run(["launchctl", "print", domain], check=False).returncode == 0:
        errors.append("Primary machine: cmux workmux reconnect LaunchAgent is loaded")
    return errors


def current_tree() -> dict[str, Any]:
    return json.loads(cmux("tree", "--all", "--json").stdout)


def find_workspace(tree: dict[str, Any], title: str) -> dict[str, Any]:
    matches = [workspace for workspace in flatten_workspaces(tree) if workspace.get("title") == title]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {title} workspace, found {len(matches)}")
    return matches[0]


def create_workspace(profile: dict[str, Any], title: str | None = None) -> None:
    workspace_title = title or profile["title"]
    if profile["transport"] == "local":
        cmux("new-workspace", "--name", workspace_title, "--command", f"exec workmux {profile['id']}", "--focus", "false")
    else:
        remote_command = [profile["remote_workmux"], profile["id"]]
        if profile.get("remote_path"):
            remote_command = ["/usr/bin/env", "PATH=" + profile["remote_path"], *remote_command]
        cmux(
            "ssh",
            profile["ssh_alias"],
            "--name",
            workspace_title,
            "--no-focus",
            "--ssh-option",
            "RequestTTY=force",
            "--",
            *remote_command,
        )
    for _ in range(20):
        time.sleep(0.25)
        try:
            find_workspace(current_tree(), workspace_title)
            return
        except RuntimeError:
            continue
    raise RuntimeError(f"cmux did not create workspace {workspace_title}")


def attachment_command(profile: dict[str, Any]) -> str:
    if profile["transport"] == "local":
        return f"workmux {profile['id']}"
    command = f"{profile['remote_workmux']} {profile['id']}"
    if profile.get("remote_path"):
        return f"/usr/bin/env PATH={profile['remote_path']} {command}"
    return command


def session_windows(profile: dict[str, Any]) -> list[str] | None:
    script = (
        'PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"; export PATH; '
        f"tmux list-windows -t '={profile['id']}' -F '#I:#W' 2>/dev/null"
    )
    if profile["transport"] == "local":
        result = run(["/bin/sh", "-lc", script], check=False)
    else:
        result = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", profile["ssh_alias"], script], check=False)
    return result.stdout.splitlines() if result.returncode == 0 else None


def session_btop_process(profile: dict[str, Any]) -> str | None:
    script = (
        'PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"; export PATH; '
        f"tmux display-message -p -t '{profile['id']}:0.0' '#{{pane_current_command}}' 2>/dev/null"
    )
    if profile["transport"] == "local":
        result = run(["/bin/sh", "-lc", script], check=False)
    else:
        result = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", profile["ssh_alias"], script], check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def session_btop_is_managed(profile: dict[str, Any]) -> bool:
    return session_btop_process(profile) in {"btop", "sleep"}


def read_surface_screen(workspace_ref: str, surface_ref: str) -> str:
    result = cmux("read-screen", "--workspace", workspace_ref, "--surface", surface_ref, check=False)
    return result.stdout if result.returncode == 0 else ""


def screen_has_tmux_status(profile: dict[str, Any], screen: str) -> bool:
    return all(token in screen for token in (profile["id"], "0:btop", "1:shell", "CPU", "MEM"))


def screen_has_shell_prompt(screen: str) -> bool:
    return any(re.search(r"(?:[$#%>❯]|➜)\s*$", line) for line in screen.splitlines()[-8:])


def wait_for_shell(workspace_ref: str, surface_ref: str) -> None:
    for _ in range(40):
        if screen_has_shell_prompt(read_surface_screen(workspace_ref, surface_ref)):
            return
        time.sleep(0.25)
    raise RuntimeError("cmux surface did not reach a shell prompt")


def attach_surface(profile: dict[str, Any], workspace_ref: str, surface_ref: str) -> None:
    if screen_has_tmux_status(profile, read_surface_screen(workspace_ref, surface_ref)):
        return
    wait_for_shell(workspace_ref, surface_ref)
    for _ in range(3):
        cmux("send-key", "--workspace", workspace_ref, "--surface", surface_ref, "ctrl+c", check=False)
        cmux("send-key", "--workspace", workspace_ref, "--surface", surface_ref, "ctrl+u", check=False)
        cmux("send", "--workspace", workspace_ref, "--surface", surface_ref, "   exec " + attachment_command(profile))
        cmux("send-key", "--workspace", workspace_ref, "--surface", surface_ref, "enter")
        for _ in range(30):
            if screen_has_tmux_status(profile, read_surface_screen(workspace_ref, surface_ref)):
                return
            time.sleep(0.2)
    raise RuntimeError(f"current cmux surface failed tmux attachment on {profile['title']}")


def wait_for_session(profile: dict[str, Any]) -> None:
    for _ in range(40):
        windows = session_windows(profile)
        if windows and "0:btop" in windows and "1:shell" in windows and session_btop_is_managed(profile):
            return
        time.sleep(0.5)
    raise RuntimeError(f"workmux session failed verification on {profile['title']}")


def wait_for_managed_surface(profile: dict[str, Any], workspace_title: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for _ in range(40):
        try:
            workspace = find_workspace(current_tree(), workspace_title)
        except RuntimeError:
            time.sleep(0.25)
            continue
        keep = choose_surface(workspace, profile["keep_titles"])
        if keep and screen_has_tmux_status(profile, read_surface_screen(workspace["ref"], keep["ref"])):
            return workspace, keep
        time.sleep(0.25)
    raise RuntimeError(f"durable workmux command failed on {workspace_title}")


def configure_workspace_metadata(profile: dict[str, Any], workspace_ref: str) -> None:
    cmux("workspace-action", "--workspace", workspace_ref, "--action", "pin")
    cmux("workspace-action", "--workspace", workspace_ref, "--action", "set-color", "--color", profile["color"])
    cmux("workspace-action", "--workspace", workspace_ref, "--action", "set-description", "--description", profile["description"])


def migrate_remote_workspace(profile: dict[str, Any], workspace: dict[str, Any]) -> None:
    keep = choose_surface(workspace, profile["keep_titles"])
    if keep is None:
        raise RuntimeError(f"cannot migrate {profile['title']}: no terminal surface")
    current_screen = read_surface_screen(workspace["ref"], keep["ref"])
    if not screen_has_tmux_status(profile, current_screen) and not screen_has_shell_prompt(current_screen):
        raise RuntimeError(f"cannot migrate {profile['title']}: current surface is not idle or managed")
    migration_title = profile["title"] + " workmux migration"
    migrations = [item for item in flatten_workspaces(current_tree()) if item.get("title") == migration_title]
    if len(migrations) > 1:
        raise RuntimeError(f"duplicate migration workspaces: {migration_title}")
    if migrations:
        stale = migrations[0]
        stale_surface = choose_surface(stale, profile["keep_titles"])
        stale_screen = read_surface_screen(stale["ref"], stale_surface["ref"]) if stale_surface else ""
        if not screen_has_tmux_status(profile, stale_screen):
            if stale.get("pinned"):
                cmux("workspace-action", "--workspace", stale["ref"], "--action", "unpin")
            cmux("workspace", "close", stale["ref"])
            migrations = []
    if not migrations:
        create_workspace(profile, migration_title)
    replacement, replacement_surface = wait_for_managed_surface(profile, migration_title)
    cmux("rename-tab", "--workspace", replacement["ref"], "--surface", replacement_surface["ref"], "--title", "main")
    wait_for_session(profile)
    configure_workspace_metadata(profile, replacement["ref"])
    if workspace.get("pinned"):
        cmux("workspace-action", "--workspace", workspace["ref"], "--action", "unpin")
    cmux("workspace", "close", workspace["ref"])
    cmux("workspace", "rename", replacement["ref"], "--title", profile["title"])


def configure_profile(profile: dict[str, Any]) -> None:
    tree = current_tree()
    created = False
    try:
        workspace = find_workspace(tree, profile["title"])
    except RuntimeError:
        create_workspace(profile)
        created = True
        workspace = find_workspace(current_tree(), profile["title"])
    if profile["transport"] == "ssh":
        if created:
            workspace, _ = wait_for_managed_surface(profile, profile["title"])
            wait_for_session(profile)
            configure_workspace_metadata(profile, workspace["ref"])
        elif workspace.get("description") != profile["description"]:
            migrate_remote_workspace(profile, workspace)
        else:
            cmux("workspace", "reconnect", "--workspace", workspace["ref"])
            time.sleep(1)
        workspace = find_workspace(current_tree(), profile["title"])
    keep = choose_surface(workspace, profile["keep_titles"])
    if keep is None:
        cmux("new-surface", "--type", "terminal", "--workspace", workspace["ref"], "--focus", "false")
        workspace = find_workspace(current_tree(), profile["title"])
        keep = choose_surface(workspace, profile["keep_titles"])
    if keep is None:
        raise RuntimeError(f"no terminal surface in {profile['title']}")
    cmux("rename-tab", "--workspace", workspace["ref"], "--surface", keep["ref"], "--title", "main")
    attach_surface(profile, workspace["ref"], keep["ref"])
    wait_for_session(profile)
    workspace = find_workspace(current_tree(), profile["title"])
    for extra in surfaces(workspace):
        if extra["ref"] != keep["ref"]:
            cmux("close-surface", "--workspace", workspace["ref"], "--surface", extra["ref"])
    configure_workspace_metadata(profile, workspace["ref"])


def verify_layout(
    tree: dict[str, Any], profiles: list[dict[str, Any]] | None = None
) -> list[str]:
    errors: list[str] = []
    workspaces = flatten_workspaces(tree)
    if [workspace.get("title") for workspace in workspaces] != [profile["title"] for profile in WORKSPACES]:
        errors.append("workspace order/titles differ")
    for profile in profiles or WORKSPACES:
        matches = [workspace for workspace in workspaces if workspace.get("title") == profile["title"]]
        if len(matches) != 1:
            errors.append(f"{profile['title']}: expected one workspace")
            continue
        workspace = matches[0]
        items = surfaces(workspace)
        if not workspace.get("pinned"):
            errors.append(f"{profile['title']}: not pinned")
        if profile["transport"] == "ssh" and workspace.get("description") != profile["description"]:
            errors.append(f"{profile['title']}: durable remote-command marker missing")
        if len(items) != 1 or items[0].get("title") != "main":
            errors.append(f"{profile['title']}: expected one main surface")
        windows = session_windows(profile)
        if not windows or "0:btop" not in windows or "1:shell" not in windows:
            errors.append(f"{profile['title']}: workmux session missing base windows")
        elif not session_btop_is_managed(profile):
            errors.append(f"{profile['title']}: 0:btop pane is not in managed btop/idle state")
        if len(items) == 1 and not screen_has_tmux_status(profile, read_surface_screen(workspace["ref"], items[0]["ref"])):
            errors.append(f"{profile['title']}: main surface is not attached to managed tmux status")
    return errors


def topology_sync_script() -> Path:
    return Path(__file__).with_name("sync_terminal_profiles.py")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    result.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="MACHINE_ID",
        help="configure or verify only an exact enabled machine profile",
    )
    result.add_argument("--config", type=Path, default=Path.home() / ".config/cmux/cmux.json")
    return result


def main() -> int:
    args = parser().parse_args()
    profiles = select_profiles(args.target)
    tree = current_tree()
    actions = plan_layout(tree)
    print("mode=" + ("apply" if args.apply else "verify" if args.verify else "dry-run"))
    for action in actions:
        print(json.dumps(action, default=str, sort_keys=True))
    if not args.apply:
        if args.verify:
            errors = verify_layout(tree, profiles) + verify_reconnect_policy()
            for error in errors:
                print("FAIL " + error)
            return 1 if errors else 0
        return 0
    unexpected = [action for action in actions if action["action"] == "unexpected-workspace"]
    if unexpected:
        raise RuntimeError("unexpected cmux workspaces: " + ", ".join(action["title"] for action in unexpected))
    for profile in profiles:
        profile_check = run(
            [
                sys.executable,
                str(topology_sync_script()),
                "--target",
                str(profile["id"]),
                "--verify",
            ],
            check=False,
        )
        if profile_check.returncode != 0:
            raise RuntimeError(
                f"terminal profile verification failed for {profile['id']}; "
                "cmux layout unchanged\n"
                + profile_check.stdout
                + profile_check.stderr
            )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    current_config = args.config.read_text(encoding="utf-8")
    atomic_update(args.config, update_cmux_json(current_config), stamp)
    install_reconnect_helper(stamp)
    backup = disable_reconnect_agent(stamp)
    if backup:
        print("backup " + str(backup))
    cmux("config", "set", "sidebar-font-size", "12")
    cmux("config", "set", "surface-tab-bar-font-size", "11")
    cmux("config", "doctor")
    cmux("reload-config")
    for profile in profiles:
        configure_profile(profile)
    tree = current_tree()
    machines = [workspace for workspace in flatten_workspaces(tree) if workspace.get("title") == "Machines"]
    for workspace in machines:
        cmux("close-workspace", "--workspace", workspace["ref"])
    tree = current_tree()
    ordered = [find_workspace(tree, profile["title"])["ref"] for profile in WORKSPACES]
    cmux("reorder-workspaces", "--order", ",".join(ordered))
    errors = verify_layout(current_tree(), profiles) + verify_reconnect_policy()
    for error in errors:
        print("FAIL " + error)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
