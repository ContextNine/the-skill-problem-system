#!/usr/bin/env python3
"""Provision and authorize dedicated per-machine fleet-shell SSH identities."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile


MACHINE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]+$")
IDENTITY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
KEY_TYPE = "ssh-ed25519"
RESERVED_SSH_FILES = {"authorized_keys", "config", "known_hosts"}


class FleetShellError(RuntimeError):
    pass


def validate_machine_id(value: str) -> str:
    if not MACHINE_ID_RE.fullmatch(value):
        raise FleetShellError(f"invalid machine id: {value!r}")
    return value


def validate_identity_path(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    ssh_root = (Path.home() / ".ssh").resolve(strict=False)
    if (
        resolved.parent != ssh_root
        or not IDENTITY_NAME_RE.fullmatch(resolved.name)
        or resolved.name in RESERVED_SSH_FILES
        or resolved.name.endswith(".pub")
    ):
        raise FleetShellError(f"fleet-shell identity must be a direct child of {ssh_root}")
    return resolved


def parse_public_key(raw: str) -> tuple[str, str]:
    fields = raw.strip().split()
    if len(fields) < 2 or fields[0] != KEY_TYPE:
        raise FleetShellError("fleet-shell public key must be one ssh-ed25519 record")
    try:
        decoded = base64.b64decode(fields[1], validate=True)
    except ValueError as exc:
        raise FleetShellError("fleet-shell public key data is invalid") from exc
    digest = base64.b64encode(hashlib.sha256(decoded).digest()).decode().rstrip("=")
    return f"{fields[0]} {fields[1]}", f"SHA256:{digest}"


def public_key_report(machine_id: str, identity: Path) -> dict[str, object]:
    private_exists = identity.is_file()
    public_path = Path(f"{identity}.pub")
    public_exists = public_path.is_file()
    if private_exists != public_exists:
        raise FleetShellError(f"incomplete fleet-shell keypair: {identity}")
    if not private_exists:
        return {
            "machine_id": machine_id,
            "identity_file": str(identity),
            "ready": False,
            "fingerprint": None,
        }
    _, fingerprint = parse_public_key(public_path.read_text(encoding="utf-8"))
    return {
        "machine_id": machine_id,
        "identity_file": str(identity),
        "ready": True,
        "fingerprint": fingerprint,
    }


def native_agent_socket() -> str | None:
    current = os.environ.get("SSH_AUTH_SOCK")
    if current and Path(current).is_socket():
        return current
    if platform.system() == "Darwin":
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/com.openssh.ssh-agent"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        match = re.search(r"(?m)^\s*path\s*=\s*(\S+/Listeners)\s*$", result.stdout)
        if match and Path(match.group(1)).is_socket():
            return match.group(1)
    for candidate in (
        Path(f"/run/user/{os.getuid()}/keyring/ssh"),
        Path(f"/run/user/{os.getuid()}/gnupg/S.gpg-agent.ssh"),
    ):
        if candidate.is_socket():
            return str(candidate)
    return None


def has_empty_passphrase(identity: Path) -> bool:
    result = subprocess.run(
        ["ssh-keygen", "-y", "-P", "", "-f", str(identity)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def load_protected_identity(identity: Path) -> None:
    agent = native_agent_socket()
    if not agent:
        raise FleetShellError("no reviewed native SSH agent is available")
    environment = dict(os.environ)
    environment["SSH_AUTH_SOCK"] = agent
    command = ["ssh-add"]
    if platform.system() == "Darwin":
        command.append("--apple-use-keychain")
    command.append(str(identity))
    subprocess.run(command, check=True, env=environment)


def provision(machine_id: str, identity: Path, *, apply: bool) -> dict[str, object]:
    report = public_key_report(machine_id, identity)
    report["mode"] = "apply" if apply else "dry-run"
    if not apply:
        report["action"] = "none" if report["ready"] else "would-generate-protected-key"
        return report
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise FleetShellError("protected key generation requires a real terminal")
    if not shutil.which("ssh-keygen") or not shutil.which("ssh-add"):
        raise FleetShellError("ssh-keygen and ssh-add are required")

    generated = not report["ready"]
    if generated:
        identity.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        identity.parent.chmod(0o700)
        subprocess.run(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-a",
                "100",
                "-f",
                str(identity),
                "-C",
                f"ctx9-fleet-shell:{machine_id}",
            ],
            check=True,
        )
        identity.chmod(0o600)
        Path(f"{identity}.pub").chmod(0o644)

    if has_empty_passphrase(identity):
        if generated:
            identity.unlink(missing_ok=True)
            Path(f"{identity}.pub").unlink(missing_ok=True)
        raise FleetShellError("fleet-shell private key must use a non-empty passphrase")

    load_protected_identity(identity)

    report = public_key_report(machine_id, identity)
    report.update(
        {
            "mode": "apply",
            "action": (
                "generated-and-loaded-protected-key"
                if generated
                else "loaded-existing-protected-key"
            ),
        }
    )
    return report


def marker_lines(machine_id: str) -> tuple[str, str]:
    return (
        f"# BEGIN ctx9 fleet shell: {machine_id}",
        f"# END ctx9 fleet shell: {machine_id}",
    )


def managed_block(content: str, machine_id: str) -> tuple[int, int, list[str]] | None:
    begin, end = marker_lines(machine_id)
    lines = content.splitlines()
    starts = [index for index, line in enumerate(lines) if line == begin]
    ends = [index for index, line in enumerate(lines) if line == end]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise FleetShellError(f"invalid managed authorized_keys block for {machine_id}")
    return starts[0], ends[0], lines


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def authorize(
    source_machine_id: str,
    authorized_keys: Path,
    public_key_file: Path,
    expected_fingerprint: str,
    *,
    mode: str,
) -> dict[str, object]:
    if not FINGERPRINT_RE.fullmatch(expected_fingerprint):
        raise FleetShellError("expected fingerprint must be an OpenSSH SHA256 fingerprint")
    normalized_key, actual_fingerprint = parse_public_key(
        public_key_file.read_text(encoding="utf-8")
    )
    if actual_fingerprint != expected_fingerprint:
        raise FleetShellError(
            f"public key fingerprint mismatch: expected {expected_fingerprint}, got {actual_fingerprint}"
        )
    content = authorized_keys.read_text(encoding="utf-8") if authorized_keys.is_file() else ""
    block = managed_block(content, source_machine_id)
    ready = False
    if block:
        start, end, lines = block
        key_lines = [line for line in lines[start + 1 : end] if line and not line.startswith("#")]
        if len(key_lines) != 1:
            raise FleetShellError(
                f"managed authorized_keys block for {source_machine_id} must contain one key"
            )
        existing_key, existing_fingerprint = parse_public_key(key_lines[0])
        if existing_fingerprint != expected_fingerprint or existing_key != normalized_key:
            raise FleetShellError(
                f"conflicting managed fleet-shell key for {source_machine_id}: {existing_fingerprint}"
            )
        ready = True

    report: dict[str, object] = {
        "source_machine_id": source_machine_id,
        "authorized_keys": str(authorized_keys),
        "fingerprint": expected_fingerprint,
        "ready": ready,
        "mode": mode,
    }
    if ready:
        report["action"] = "none"
        return report
    if mode == "verify":
        report["action"] = "missing"
        return report
    if mode == "dry-run":
        report["action"] = "would-add-managed-public-key"
        return report

    begin, end = marker_lines(source_machine_id)
    suffix = "" if not content or content.endswith("\n") else "\n"
    write_atomic(
        authorized_keys,
        f"{content}{suffix}{begin}\n{normalized_key} ctx9-fleet-shell:{source_machine_id}\n{end}\n",
    )
    report.update({"ready": True, "action": "added-managed-public-key"})
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    for action in ("provision", "inspect"):
        command = subparsers.add_parser(action)
        command.add_argument("--machine-id", required=True)
        command.add_argument("--identity-file", type=Path, required=True)
        if action == "provision":
            mode = command.add_mutually_exclusive_group(required=True)
            mode.add_argument("--dry-run", action="store_true")
            mode.add_argument("--apply", action="store_true")

    authorize_parser = subparsers.add_parser("authorize")
    authorize_parser.add_argument("--source-machine-id", required=True)
    authorize_parser.add_argument("--expected-fingerprint", required=True)
    authorize_parser.add_argument("--public-key-file", type=Path, required=True)
    authorize_parser.add_argument(
        "--authorized-keys",
        type=Path,
        default=Path.home() / ".ssh/authorized_keys",
    )
    mode = authorize_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action in {"provision", "inspect"}:
        machine_id = validate_machine_id(args.machine_id)
        identity = validate_identity_path(args.identity_file)
        report = (
            public_key_report(machine_id, identity)
            if args.action == "inspect"
            else provision(machine_id, identity, apply=args.apply)
        )
        if args.action == "inspect":
            report["mode"] = "inspect"
            report["action"] = "none" if report["ready"] else "missing"
    else:
        machine_id = validate_machine_id(args.source_machine_id)
        selected_mode = "apply" if args.apply else "verify" if args.verify else "dry-run"
        report = authorize(
            machine_id,
            args.authorized_keys.expanduser(),
            args.public_key_file.expanduser(),
            args.expected_fingerprint,
            mode=selected_mode,
        )
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] or report["mode"] == "dry-run" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FleetShellError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(json.dumps({"ready": False, "error": str(exc)}))
        raise SystemExit(2)
