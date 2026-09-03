#!/usr/bin/env python3
"""Install Primary machine SOPS age identities on a reviewed SSH host without displaying them."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path, PurePosixPath
import shlex
import stat
import subprocess
import sys


def run(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=600,
    )


def ssh_command(host: str, command: str) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        host,
        "sh -lc " + shlex.quote(command),
    ]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def source_recipients(path: Path) -> tuple[str, ...]:
    result = run(["age-keygen", "-y", str(path)])
    recipients = tuple(
        line.strip() for line in result.stdout.splitlines() if line.strip().startswith("age1")
    )
    if not recipients:
        raise RuntimeError("source contains no age identities")
    if len(recipients) != len(set(recipients)):
        raise RuntimeError("source contains duplicate age identities")
    return recipients


def validate_source(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"source key missing: {path}")
    directory_mode = stat.S_IMODE(path.parent.stat().st_mode)
    if directory_mode & 0o077:
        raise PermissionError(
            f"source key directory permissions must be 0700 or stricter: {oct(directory_mode)}"
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(f"source key permissions must be 0600 or stricter: {oct(mode)}")


def validate_repo_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = PurePosixPath(value)
    if not path.is_absolute():
        raise ValueError("--verify-repo must be an absolute target path")
    return str(path)


def remote_hash(host: str) -> str | None:
    command = (
        'target="$HOME/.sops/key.txt"; '
        'test -f "$target" || exit 3; '
        'if command -v sha256sum >/dev/null 2>&1; then sha256sum "$target"; '
        'elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$target"; '
        "else exit 4; fi"
    )
    result = run(ssh_command(host, command), check=False)
    if result.returncode == 3:
        return None
    if result.returncode != 0:
        raise RuntimeError("target cannot hash existing SOPS key")
    fields = result.stdout.split()
    if not fields:
        raise RuntimeError("target returned no SOPS key digest")
    return fields[0]


def install_key(host: str, source: Path, *, replace: bool) -> None:
    temporary = ".sops/key.txt.enroll-new"
    run(
        ssh_command(
            host,
            'install -d -m 0700 "$HOME/.sops"; '
            'test ! -e "$HOME/.sops/key.txt.enroll-new"',
        )
    )
    run(["scp", "-q", str(source), f"{host}:~/{temporary}"])
    backup_suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    activate = 'chmod 0600 "$HOME/.sops/key.txt.enroll-new"; '
    if replace:
        activate += (
            'if test -f "$HOME/.sops/key.txt"; then '
            f'cp -p "$HOME/.sops/key.txt" "$HOME/.sops/key.txt.backup-{backup_suffix}"; fi; '
        )
    activate += 'mv "$HOME/.sops/key.txt.enroll-new" "$HOME/.sops/key.txt"'
    run(ssh_command(host, activate))


def verify_target(host: str, recipients: tuple[str, ...], repo: str | None) -> None:
    quoted_recipients = " ".join(shlex.quote(value) for value in recipients)
    command = (
        "set -eu; "
        'test "$(stat -c %a "$HOME/.sops" 2>/dev/null || stat -f %Lp "$HOME/.sops")" = 700; '
        'test "$(stat -c %a "$HOME/.sops/key.txt" 2>/dev/null || stat -f %Lp "$HOME/.sops/key.txt")" = 600; '
        'actual=$(age-keygen -y "$HOME/.sops/key.txt"); '
        f"for recipient in {quoted_recipients}; do printf '%s\\n' \"$actual\" | grep -Fx -- \"$recipient\" >/dev/null; done"
    )
    if repo is not None:
        quoted_repo = shlex.quote(repo)
        command += (
            f"; test -d {quoted_repo}/.git; test -f {quoted_repo}/.sops.yaml; "
            "matched=0; "
            f"for recipient in {quoted_recipients}; do "
            f"if grep -F -- \"$recipient\" {quoted_repo}/.sops.yaml >/dev/null; then matched=1; fi; done; "
            'test "$matched" = 1; '
            f"encrypted=$(git -C {quoted_repo} ls-files '*.sops' '*.sops.*' | "
            "grep -v -E '(^|/)\\.sops\\.yaml$' | head -n 1); "
            'if test -n "$encrypted"; then '
            'case "$encrypted" in '
            '*.env*.sops) input_type=dotenv ;; '
            '*.yaml.sops|*.yml.sops) input_type=yaml ;; '
            '*.json.sops) input_type=json ;; '
            '*) input_type= ;; '
            'esac; '
            'if test -n "$input_type"; then '
            f'SOPS_AGE_KEY_FILE="$HOME/.sops/key.txt" sops --decrypt --input-type "$input_type" --output-type "$input_type" {quoted_repo}/"$encrypted" >/dev/null; '
            "else "
            f'SOPS_AGE_KEY_FILE="$HOME/.sops/key.txt" sops --decrypt {quoted_repo}/"$encrypted" >/dev/null; '
            "fi; fi"
        )
    run(ssh_command(host, command))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--host", required=True)
    result.add_argument("--source", type=Path, default=Path.home() / ".sops/key.txt")
    result.add_argument("--verify-repo")
    result.add_argument("--replace", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    source = args.source.expanduser()
    repo = validate_repo_path(args.verify_repo)
    validate_source(source)
    recipients = source_recipients(source)
    expected = digest(source)

    prerequisite = run(
        ssh_command(
            args.host,
            "command -v age-keygen >/dev/null && command -v sops >/dev/null",
        ),
        check=False,
    )
    if prerequisite.returncode != 0:
        raise RuntimeError("target requires age-keygen and sops")

    existing = remote_hash(args.host)
    if existing and existing != expected and not args.replace:
        raise RuntimeError("different target SOPS key exists; review and rerun with --replace")
    if existing != expected:
        install_key(args.host, source, replace=args.replace)

    if remote_hash(args.host) != expected:
        raise RuntimeError("post-install SOPS key digest mismatch")
    verify_target(args.host, recipients, repo)
    print(f"SOPS identities installed and verified: host={args.host} recipients={len(recipients)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, PermissionError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
