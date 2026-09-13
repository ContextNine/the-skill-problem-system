#!/usr/bin/env python3
"""Preview, install, and verify optional Linux worker watchdogs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
import tempfile
from typing import Any


REGISTRY_RELATIVE = Path(
    "_system/agents/edit/settings/fleet/machines.json"
)
ASSET_RELATIVE = Path(
    "_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/assets/linux-watchdogs"
)
WATCHDOGS = {
    "playwright-cli": {
        "files": (
            "playwright-cli-watchdog.py",
            "playwright-cli-wrapper",
            "playwright-cli-watchdog.service",
            "playwright-cli-watchdog.timer",
        ),
        "timer": "playwright-cli-watchdog.timer",
    }
}


class WatchdogError(RuntimeError):
    """A deterministic optional-watchdog failure."""


def run(
    argv: list[str], *, check: bool = True, timeout: int = 180
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
    )


def find_root(start: Path | None = None) -> Path:
    candidate = (start or Path(__file__)).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for parent in (candidate, *candidate.parents):
        if (parent / "AGENTS.md").is_file() and (parent / "_system/agents").is_dir():
            return parent
    raise WatchdogError("could not locate Vault root")


def load_registry(root: Path) -> dict[str, Any]:
    path = root / REGISTRY_RELATIVE
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise WatchdogError(f"private machine registry is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise WatchdogError(f"private machine registry is invalid: {error}") from error
    if not isinstance(value.get("machines"), list):
        raise WatchdogError("private machine registry has no machines array")
    return value


def require_primary(root: Path, registry: dict[str, Any]) -> None:
    result = run(["git", "-C", str(root), "config", "--get", "vault.machine-id"])
    actual = result.stdout.strip()
    expected = registry.get("primary_machine_id")
    if actual != expected:
        raise WatchdogError(
            f"run from registered primary {expected!r}; current machine is {actual!r}"
        )


def resolve_linux_worker(
    registry: dict[str, Any], machine_id: str, *, provision_disabled: bool
) -> dict[str, Any]:
    matches = [machine for machine in registry["machines"] if machine.get("id") == machine_id]
    if len(matches) != 1:
        raise WatchdogError(f"unknown exact machine id: {machine_id}")
    machine = matches[0]
    if machine.get("role") != "worker" or machine.get("platform") != "linux":
        raise WatchdogError(f"machine is not a Linux worker: {machine_id}")
    if machine.get("enabled") is not True and not provision_disabled:
        raise WatchdogError(
            f"disabled target requires --provision-disabled: {machine_id}"
        )
    if machine.get("transport") != "ssh" or not machine.get("ssh_alias"):
        raise WatchdogError(f"machine has no reviewed SSH alias: {machine_id}")
    home = str(machine.get("home", ""))
    if not PurePosixPath(home).is_absolute() or any(character.isspace() for character in home):
        raise WatchdogError(f"machine has unsafe or missing home path: {machine_id}")
    return machine


def ssh(machine: dict[str, Any], script: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = "exec /bin/bash -lc " + shlex.quote(script)
    return run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            str(machine["ssh_alias"]),
            command,
        ],
        check=check,
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asset_paths(root: Path, watchdog: str) -> dict[str, Path]:
    directory = root / ASSET_RELATIVE
    paths = {name: directory / name for name in WATCHDOGS[watchdog]["files"]}
    missing = [path for path in paths.values() if not path.is_file()]
    if missing:
        raise WatchdogError(f"watchdog asset is missing: {missing[0]}")
    return paths


def remote_facts(machine: dict[str, Any]) -> dict[str, str]:
    result = ssh(
        machine,
        r'''
set -u
printf 'home\t%s\n' "$HOME"
printf 'python\t%s\n' "$(command -v python3 || true)"
printf 'systemctl\t%s\n' "$(command -v systemctl || true)"
printf 'playwright\t%s\n' "$(command -v playwright-cli || true)"
printf 'playwright_real\t%s\n' "$(readlink -f "$HOME/.local/lib/node_modules/@playwright/cli/playwright-cli.js" 2>/dev/null || true)"
printf 'linger\t%s\n' "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)"
''',
    )
    facts: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("\t")
        if separator:
            facts[key] = value
    return facts


def validate_facts(machine: dict[str, Any], facts: dict[str, str]) -> None:
    expected_home = str(machine["home"])
    if facts.get("home") != expected_home:
        raise WatchdogError(
            f"remote home mismatch: expected {expected_home!r}, got {facts.get('home')!r}"
        )
    for command in ("python", "systemctl", "playwright_real"):
        if not facts.get(command):
            raise WatchdogError(f"remote prerequisite is missing: {command}")
    if facts.get("linger") != "yes":
        raise WatchdogError("Linux worker user lingering is not enabled")


def dry_run(root: Path, machine: dict[str, Any], watchdog: str) -> None:
    paths = asset_paths(root, watchdog)
    facts = remote_facts(machine)
    validate_facts(machine, facts)
    print(f"DRY RUN optional Linux watchdog {watchdog!r} -> {machine['id']}")
    print("  install guarded ~/.local/bin/playwright-cli")
    print("  install ~/.local/libexec/playwright-cli-watchdog")
    print("  enable user timer playwright-cli-watchdog.timer")
    print("  stale threshold: 3600 seconds; schedule: every 10 minutes")
    for name, path in paths.items():
        print(f"  asset {name}: sha256={digest(path)}")


def install(root: Path, machine: dict[str, Any], watchdog: str) -> None:
    paths = asset_paths(root, watchdog)
    facts = remote_facts(machine)
    validate_facts(machine, facts)
    stage_result = ssh(machine, 'mktemp -d "$HOME/.local/share/linux-watchdog-stage.XXXXXX"')
    stage = stage_result.stdout.strip()
    expected_prefix = f"{machine['home']}/.local/share/linux-watchdog-stage."
    if not stage.startswith(expected_prefix):
        raise WatchdogError(f"unexpected remote staging path: {stage!r}")
    try:
        for path in paths.values():
            run(["scp", "-q", str(path), f"{machine['ssh_alias']}:{stage}/{path.name}"])
        apply_script = f'''
set -euo pipefail
stage={shlex.quote(stage)}
home={shlex.quote(str(machine['home']))}
current="$home/.local/bin/playwright-cli"
real="$home/.local/lib/node_modules/@playwright/cli/playwright-cli.js"
marker='ctx9-playwright-cli-watchdog-v1'
if [ ! -f "$real" ]; then
  echo "real Playwright CLI entrypoint is missing: $real" >&2
  exit 1
fi
if [ -L "$current" ]; then
  resolved=$(readlink -f "$current")
  if [ "$resolved" != "$real" ]; then
    echo "refusing unexpected Playwright CLI symlink: $resolved" >&2
    exit 1
  fi
elif [ -f "$current" ]; then
  if ! grep -qF "$marker" "$current"; then
    echo "refusing unmanaged Playwright CLI file: $current" >&2
    exit 1
  fi
else
  echo "Playwright CLI command is missing: $current" >&2
  exit 1
fi
install -d -m 0700 "$home/.local/share/playwright-cli-watchdog"
install -d -m 0755 "$home/.local/bin" "$home/.local/libexec" "$home/.config/systemd/user"
if [ -L "$current" ] && [ ! -e "$home/.local/share/playwright-cli-watchdog/original-link" ]; then
  readlink "$current" > "$home/.local/share/playwright-cli-watchdog/original-link"
  chmod 0600 "$home/.local/share/playwright-cli-watchdog/original-link"
fi
install -m 0755 "$stage/playwright-cli-watchdog.py" "$home/.local/libexec/playwright-cli-watchdog"
if [ -L "$current" ]; then
  rm -f -- "$current"
fi
install -m 0755 "$stage/playwright-cli-wrapper" "$current"
install -m 0644 "$stage/playwright-cli-watchdog.service" "$home/.config/systemd/user/playwright-cli-watchdog.service"
install -m 0644 "$stage/playwright-cli-watchdog.timer" "$home/.config/systemd/user/playwright-cli-watchdog.timer"
systemctl --user daemon-reload
systemctl --user enable --now playwright-cli-watchdog.timer
systemctl --user start playwright-cli-watchdog.service
'''
        ssh(machine, apply_script)
    finally:
        ssh(machine, f"rm -rf -- {shlex.quote(stage)}", check=False)


def verify(root: Path, machine: dict[str, Any], watchdog: str) -> None:
    paths = asset_paths(root, watchdog)
    expected = {name: digest(path) for name, path in paths.items()}
    home = str(machine["home"])
    verify_script = f'''
set -euo pipefail
home={shlex.quote(home)}
test -x "$home/.local/libexec/playwright-cli-watchdog"
grep -qF 'ctx9-playwright-cli-watchdog-v1' "$home/.local/bin/playwright-cli"
test "$(sha256sum "$home/.local/libexec/playwright-cli-watchdog" | cut -d' ' -f1)" = {shlex.quote(expected['playwright-cli-watchdog.py'])}
test "$(sha256sum "$home/.local/bin/playwright-cli" | cut -d' ' -f1)" = {shlex.quote(expected['playwright-cli-wrapper'])}
test "$(sha256sum "$home/.config/systemd/user/playwright-cli-watchdog.service" | cut -d' ' -f1)" = {shlex.quote(expected['playwright-cli-watchdog.service'])}
test "$(sha256sum "$home/.config/systemd/user/playwright-cli-watchdog.timer" | cut -d' ' -f1)" = {shlex.quote(expected['playwright-cli-watchdog.timer'])}
systemctl --user is-enabled playwright-cli-watchdog.timer
systemctl --user is-active playwright-cli-watchdog.timer
"$home/.local/libexec/playwright-cli-watchdog" --watchdog-self-check
"$home/.local/libexec/playwright-cli-watchdog" --watchdog-sweep --idle-seconds 3600 --dry-run
"$home/.local/bin/playwright-cli" --version
'''
    result = ssh(machine, verify_script)
    print(result.stdout, end="")
    print(f"verified optional Linux watchdog {watchdog!r} on {machine['id']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--watchdog", required=True, choices=sorted(WATCHDOGS))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--provision-disabled", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and args.verify:
        raise WatchdogError("choose --apply or --verify, not both")
    root = find_root()
    registry = load_registry(root)
    require_primary(root, registry)
    machine = resolve_linux_worker(
        registry, args.target, provision_disabled=args.provision_disabled
    )
    if args.verify:
        verify(root, machine, args.watchdog)
    elif args.apply:
        install(root, machine, args.watchdog)
        verify(root, machine, args.watchdog)
    else:
        dry_run(root, machine, args.watchdog)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (WatchdogError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            detail = error.stderr.strip() or error.stdout.strip() or str(error)
        else:
            detail = str(error)
        print(f"error: {detail}", file=sys.stderr)
        raise SystemExit(1)
