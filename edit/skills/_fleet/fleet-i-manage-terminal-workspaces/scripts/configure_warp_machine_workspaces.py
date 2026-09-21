#!/usr/bin/env python3
"""Plan, apply, and verify Primary machine Warp machine workspace configuration."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import json
from pathlib import Path
import shutil
import tempfile


HELPER_NAME = "workmux-warp-attach"
STARTUP_NAME = "workmux-warp-startup"
CONFIG_NAME = "machine_workspaces.yaml"
ALLOWED_WARP_COLORS = {
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
}
def inventory_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "_system/agents/edit/settings/fleet/machines.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("private machine registry not found from skill path")


INVENTORY = json.loads(inventory_path().read_text(encoding="utf-8"))
TERMINAL_PROFILES = [
    {
        "id": machine["id"],
        "title": machine["display_name"],
        "transport": machine["transport"],
        "warp_color": machine["terminal_profile"]["warp_color"],
    }
    for machine in INVENTORY.get("machines", [])
    if machine.get("enabled") and isinstance(machine.get("terminal_profile"), dict)
]
ORCHESTRATION = INVENTORY.get("terminal_orchestration", {})
LEGACY_HELPERS = tuple(ORCHESTRATION.get("legacy_warp_helpers", []))
MANAGED_MARKERS = tuple(profile["id"] for profile in TERMINAL_PROFILES)
LEGACY_MARKERS = tuple(ORCHESTRATION.get("legacy_warp_markers", []))
RC_BEGIN = "# >>> workmux Warp startup >>>"
RC_END = "# <<< workmux Warp startup <<<"


def helper_asset() -> Path:
    return Path(__file__).parent.parent / "assets/terminal-workspaces" / HELPER_NAME


def startup_asset() -> Path:
    return Path(__file__).parent.parent / "assets/terminal-workspaces" / STARTUP_NAME


def helper_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".local/bin" / HELPER_NAME


def startup_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".local/bin" / STARTUP_NAME


def zshrc_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".zshrc"


def marker_root(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".local/share/workmux/warp-launch"


def config_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".warp/launch_configurations" / CONFIG_NAME


def main_config_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".warp/launch_configurations/main_workspace_launch_config.yaml"


def settings_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".warp/settings.toml"


def runtime_config_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".config/workmux/machines.json"


def runtime_config_data() -> bytes:
    return (json.dumps(INVENTORY, indent=2, ensure_ascii=False) + "\n").encode()


def validate_profiles(profiles: list[dict[str, str]] | None = None) -> None:
    for profile in profiles or TERMINAL_PROFILES:
        color = profile.get("warp_color")
        if color not in ALLOWED_WARP_COLORS:
            raise ValueError(
                f"invalid Warp color for {profile.get('id')}: {color!r}; "
                f"expected one of {', '.join(sorted(ALLOWED_WARP_COLORS))}"
            )


def render_config(home: Path | None = None) -> str:
    validate_profiles()
    root = home or Path.home()
    helper = helper_path(root)
    markers = marker_root(root)
    rendered_tabs: list[str] = []
    for index, profile in enumerate(TERMINAL_PROFILES):
        command = f"{root}/.local/bin/workmux {profile['id']}" if profile["transport"] == "local" else f"{helper} {profile['id']}"
        focused = "\n          is_focused: true" if index == 0 else ""
        rendered_tabs.append(f'''      - title: "{profile['title']} \u00b7 main"
        color: {profile['warp_color']}
        layout:
          cwd: {markers}/{profile['id']}{focused}
          pane_mode: terminal
          commands:
            - exec: {command}''')
    return f'''# Warp Launch Configuration
# Canonical Warp-first workmux layout. Managed by configure_warp_machine_workspaces.py.
---
name: Machine Workspaces
active_window_index: 0
windows:
  - active_tab_index: 0
    tabs:
{chr(10).join(rendered_tabs)}
'''


def shell_block() -> str:
    return f'''{RC_BEGIN}
if [[ "${{TERM_PROGRAM:-}}" == "WarpTerminal" && -x "$HOME/.local/bin/{STARTUP_NAME}" ]]; then
  "$HOME/.local/bin/{STARTUP_NAME}" --shell-pid "$$" --cwd "$PWD" >/dev/null 2>&1 &!
fi
{RC_END}'''


def render_zshrc(current: str) -> str:
    begin_count = current.count(RC_BEGIN)
    end_count = current.count(RC_END)
    block = shell_block()
    if begin_count == end_count == 0:
        prefix = current.rstrip("\n")
        return (prefix + "\n\n" if prefix else "") + block + "\n"
    if begin_count != 1 or end_count != 1:
        raise ValueError("malformed workmux Warp startup block in .zshrc")
    begin = current.index(RC_BEGIN)
    end = current.index(RC_END, begin) + len(RC_END)
    return current[:begin] + block + current[end:]


def atomic_update(path: Path, data: bytes, stamp: str, mode: int) -> Path | None:
    current = path.read_bytes() if path.exists() else None
    if current == data:
        if path.stat().st_mode & 0o777 != mode:
            path.chmod(mode)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = Path(str(path) + ".backup-" + stamp)
    if path.exists():
        shutil.copy2(path, backup)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    temporary.chmod(mode)
    temporary.replace(path)
    return backup if backup.exists() else None


def archive_legacy(path: Path, stamp: str) -> Path:
    backup = Path(str(path) + ".backup-" + stamp)
    shutil.copy2(path, backup)
    path.unlink()
    return backup


def cleanup_legacy_markers(home: Path | None = None) -> list[str]:
    root = home or Path.home()
    notices: list[str] = []
    for name in LEGACY_MARKERS:
        path = marker_root(root) / name
        if not path.exists():
            continue
        try:
            path.rmdir()
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
            notices.append(f"preserved non-empty directory {path}")
    return notices


def vertical_tabs_enabled(path: Path) -> bool:
    if not path.exists():
        return False
    section = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
        elif section == "appearance.vertical_tabs" and line.replace(" ", "") == "enabled=true":
            return True
    return False


def render_settings(current: str) -> str:
    lines = current.splitlines()
    general_start: int | None = None
    general_end = len(lines)
    for index, raw_line in enumerate(lines):
        line = raw_line.split("#", 1)[0].strip()
        if line == "[general]":
            general_start = index
            continue
        if general_start is not None and index > general_start and line.startswith("[") and line.endswith("]"):
            general_end = index
            break
    if general_start is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(("[general]", "restore_session = false"))
    else:
        for index in range(general_start + 1, general_end):
            key = lines[index].split("#", 1)[0].split("=", 1)[0].strip()
            if key == "restore_session":
                lines[index] = "restore_session = false"
                break
        else:
            lines.insert(general_end, "restore_session = false")
    return "\n".join(lines) + "\n"


def session_restore_disabled(path: Path) -> bool:
    if not path.exists():
        return False
    return render_settings(path.read_text(encoding="utf-8")) == path.read_text(encoding="utf-8")


def differences(home: Path | None = None) -> list[str]:
    root = home or Path.home()
    found: list[str] = []
    helper = helper_path(root)
    if not helper.exists():
        found.append(f"missing {helper}")
    elif helper.read_bytes() != helper_asset().read_bytes():
        found.append(f"different {helper}")
    elif helper.stat().st_mode & 0o777 != 0o755:
        found.append(f"wrong mode {helper}")
    runtime = runtime_config_path(root)
    if not runtime.exists():
        found.append(f"missing {runtime}")
    elif runtime.read_bytes() != runtime_config_data():
        found.append(f"different {runtime}")
    elif runtime.stat().st_mode & 0o777 != 0o600:
        found.append(f"wrong mode {runtime}")
    startup = startup_path(root)
    if not startup.exists():
        found.append(f"missing {startup}")
    elif startup.read_bytes() != startup_asset().read_bytes():
        found.append(f"different {startup}")
    elif startup.stat().st_mode & 0o777 != 0o755:
        found.append(f"wrong mode {startup}")
    config = config_path(root)
    wanted = render_config(root).encode()
    if not config.exists():
        found.append(f"missing {config}")
    elif config.read_bytes() != wanted:
        found.append(f"different {config}")
    if not main_config_path(root).exists():
        found.append(f"missing preserved main config {main_config_path(root)}")
    if not vertical_tabs_enabled(settings_path(root)):
        found.append("Warp vertical tabs are not enabled")
    if not session_restore_disabled(settings_path(root)):
        found.append("Warp session restoration is not disabled")
    rc = zshrc_path(root)
    current_rc = rc.read_text(encoding="utf-8") if rc.exists() else ""
    try:
        if render_zshrc(current_rc) != current_rc:
            found.append(f"different {rc}")
    except ValueError as error:
        found.append(str(error))
    for name in MANAGED_MARKERS:
        path = marker_root(root) / name
        if not path.is_dir():
            found.append(f"missing directory {path}")
    for name in LEGACY_HELPERS:
        path = root / ".local/bin" / name
        if path.exists():
            found.append(f"obsolete {path}")
    return found


def apply(home: Path | None = None) -> tuple[list[Path], list[str]]:
    root = home or Path.home()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backups: list[Path] = []
    rc = zshrc_path(root)
    current_rc = rc.read_text(encoding="utf-8") if rc.exists() else ""
    settings = settings_path(root)
    current_settings = settings.read_text(encoding="utf-8") if settings.exists() else ""
    for path, data, mode in (
        (helper_path(root), helper_asset().read_bytes(), 0o755),
        (runtime_config_path(root), runtime_config_data(), 0o600),
        (startup_path(root), startup_asset().read_bytes(), 0o755),
        (config_path(root), render_config(root).encode(), 0o644),
        (rc, render_zshrc(current_rc).encode(), rc.stat().st_mode & 0o777 if rc.exists() else 0o644),
        (settings, render_settings(current_settings).encode(), settings.stat().st_mode & 0o777 if settings.exists() else 0o644),
    ):
        backup = atomic_update(path, data, stamp, mode)
        if backup:
            backups.append(backup)
    for name in MANAGED_MARKERS:
        (marker_root(root) / name).mkdir(parents=True, exist_ok=True)
    notices = cleanup_legacy_markers(root)
    for name in LEGACY_HELPERS:
        path = root / ".local/bin" / name
        if path.exists():
            backups.append(archive_legacy(path, stamp))
    return backups, notices


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    result.add_argument("--home", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    root = args.home or Path.home()
    print("mode=" + ("apply" if args.apply else "verify" if args.verify else "dry-run"))
    before = differences(root)
    for item in before:
        print(item)
    if args.apply:
        backups, notices = apply(root)
        for backup in backups:
            print(f"backup {backup}")
        for notice in notices:
            print(notice)
        after = differences(root)
        for item in after:
            print("FAIL " + item)
        return 1 if after else 0
    return 1 if args.verify and before else 0


if __name__ == "__main__":
    raise SystemExit(main())
