#!/usr/bin/env python3
"""Guard Playwright CLI activity and reap exact stale daemon sessions."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from typing import Any


MANAGED_MARKER = "ctx9-playwright-cli-watchdog-v1"
SESSION_COMMAND_EXCLUSIONS = {
    "close-all",
    "install",
    "install-browser",
    "kill-all",
    "list",
    "show",
}


def real_cli_path(home: Path) -> Path:
    return (
        home
        / ".local/lib/node_modules/@playwright/cli/playwright-cli.js"
    )


def playwright_package_path(home: Path) -> Path:
    return (
        home
        / ".local/lib/node_modules/@playwright/cli/node_modules/playwright/package.json"
    )


def daemon_base(home: Path) -> Path:
    cache = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
    return cache / "ms-playwright/daemon"


def find_workspace(start: Path) -> Path | None:
    current = start.resolve()
    for _ in range(10):
        if (current / ".playwright").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def workspace_hash(home: Path, cwd: Path) -> str:
    source = find_workspace(cwd) or playwright_package_path(home).resolve()
    return hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:16]


def session_name(argv: list[str]) -> str:
    explicit: str | None = None
    for index, value in enumerate(argv):
        if value.startswith("-s="):
            explicit = value.partition("=")[2]
        elif value.startswith("--session="):
            explicit = value.partition("=")[2]
        elif value in {"-s", "--session"} and index + 1 < len(argv):
            explicit = argv[index + 1]
    value = explicit or os.environ.get("PLAYWRIGHT_CLI_SESSION") or "default"
    if not value or value in {".", ".."} or any(character in value for character in "/\\\0"):
        raise ValueError(f"unsafe Playwright CLI session name: {value!r}")
    return value


def command_name(argv: list[str]) -> str | None:
    skip_next = False
    for value in argv:
        if skip_next:
            skip_next = False
            continue
        if value in {"-s", "--session"}:
            skip_next = True
            continue
        if value.startswith("-"):
            continue
        return value
    return None


def session_file(home: Path, cwd: Path, name: str) -> Path:
    return daemon_base(home) / workspace_hash(home, cwd) / f"{name}.session"


def touch_if_present(path: Path) -> None:
    if path.is_file():
        os.utime(path, None)


def run_guarded_cli(argv: list[str]) -> int:
    home = Path.home()
    cli = real_cli_path(home)
    node = home / ".local/bin/node"
    if not cli.is_file():
        print(f"Playwright CLI entrypoint is missing: {cli}", file=sys.stderr)
        return 1
    if not node.exists():
        print(f"Managed Node entrypoint is missing: {node}", file=sys.stderr)
        return 1

    command = command_name(argv)
    tracked = command is not None and command not in SESSION_COMMAND_EXCLUSIONS
    path: Path | None = None
    lock = None
    if tracked:
        try:
            path = session_file(home, Path.cwd(), session_name(argv))
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        if path.is_file():
            lock = path.open("rb")
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            touch_if_present(path)

    try:
        completed = subprocess.run([str(node), str(cli), *argv], check=False)
        return completed.returncode
    finally:
        if path is not None:
            touch_if_present(path)
        if lock is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()


def read_session(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def matching_daemon_pids(path: Path) -> list[int]:
    expected = f"--daemon-session={path.resolve()}"
    matches: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        parts = cmdline(int(entry.name))
        if "run-cli-server" in parts and expected in parts:
            matches.append(int(entry.name))
    return matches


def request_graceful_stop(config: dict[str, Any]) -> bool:
    socket_path = config.get("socketPath")
    version = config.get("version")
    if not isinstance(socket_path, str) or not socket_path:
        return False
    if not isinstance(version, str) or not version:
        return False
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5)
    try:
        client.connect(socket_path)
        message = {
            "id": 1,
            "method": "stop",
            "params": {},
            "version": version,
        }
        client.sendall((json.dumps(message) + "\n").encode("utf-8"))
        client.recv(4096)
        return True
    except OSError:
        return False
    finally:
        client.close()


def wait_for_exit(pids: list[int], seconds: float) -> list[int]:
    deadline = time.monotonic() + seconds
    remaining = pids
    while remaining and time.monotonic() < deadline:
        remaining = [pid for pid in remaining if Path(f"/proc/{pid}").exists()]
        if remaining:
            time.sleep(0.2)
    return remaining


def signal_exact_daemons(pids: list[int], selected_signal: signal.Signals) -> None:
    for pid in pids:
        try:
            process_group = os.getpgid(pid)
            if process_group == pid:
                os.killpg(process_group, selected_signal)
            else:
                os.kill(pid, selected_signal)
        except (ProcessLookupError, PermissionError):
            continue


def cleanup_session_file(path: Path, config: dict[str, Any]) -> None:
    cli = config.get("cli")
    persistent = isinstance(cli, dict) and cli.get("persistent") is True
    socket_path = config.get("socketPath")
    if isinstance(socket_path, str) and socket_path:
        try:
            Path(socket_path).unlink()
        except FileNotFoundError:
            pass
    if not persistent:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def sweep(*, idle_seconds: int, dry_run: bool, base: Path | None = None) -> int:
    home = Path.home()
    root = base or daemon_base(home)
    now = time.time()
    stale: list[tuple[Path, dict[str, Any], int]] = []
    for path in sorted(root.glob("*/*.session")):
        config = read_session(path)
        if config is None:
            continue
        try:
            age = int(now - path.stat().st_mtime)
        except FileNotFoundError:
            continue
        if age >= idle_seconds:
            stale.append((path, config, age))

    for path, config, age in stale:
        try:
            lock = path.open("rb")
        except FileNotFoundError:
            continue
        try:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            config = read_session(path)
            if config is None:
                continue
            try:
                age = int(time.time() - path.stat().st_mtime)
            except FileNotFoundError:
                continue
            if age < idle_seconds:
                continue
            name = config.get("name") if isinstance(config.get("name"), str) else path.stem
            if dry_run:
                print(f"would close stale Playwright CLI session {name!r} idle={age}s file={path}")
                continue

            pids = matching_daemon_pids(path)
            request_graceful_stop(config)
            remaining = wait_for_exit(pids, 15)
            if remaining:
                signal_exact_daemons(remaining, signal.SIGTERM)
                remaining = wait_for_exit(remaining, 5)
            if remaining:
                signal_exact_daemons(remaining, signal.SIGKILL)
                remaining = wait_for_exit(remaining, 2)
            if remaining:
                print(
                    f"failed to stop exact Playwright CLI daemon(s) for {name!r}: {remaining}",
                    file=sys.stderr,
                )
                return 1
            cleanup_session_file(path, config)
            print(f"closed stale Playwright CLI session {name!r} idle={age}s")
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
    return 0


def self_check() -> int:
    home = Path.home()
    missing = [
        path
        for path in (real_cli_path(home), playwright_package_path(home), home / ".local/bin/node")
        if not path.exists()
    ]
    if missing:
        for path in missing:
            print(f"missing prerequisite: {path}", file=sys.stderr)
        return 1
    print(f"{MANAGED_MARKER} ready")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--watchdog-sweep", action="store_true")
    parser.add_argument("--watchdog-self-check", action="store_true")
    parser.add_argument("--idle-seconds", type=int, default=3600)
    parser.add_argument("--dry-run", action="store_true")
    known, remaining = parser.parse_known_args()
    if known.watchdog_self_check:
        return self_check()
    if known.watchdog_sweep:
        if known.idle_seconds < 60:
            print("idle threshold must be at least 60 seconds", file=sys.stderr)
            return 2
        return sweep(idle_seconds=known.idle_seconds, dry_run=known.dry_run)
    return run_guarded_cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
