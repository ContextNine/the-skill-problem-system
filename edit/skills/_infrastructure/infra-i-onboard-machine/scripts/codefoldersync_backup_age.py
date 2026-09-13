#!/usr/bin/env python3
"""Generate and accept independent CodeFolderSync backup recovery identities."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any


SCHEMA_VERSION = 1
CREDENTIAL_ID = "codefoldersync-backup-age"
RECOVERY_MACHINES = frozenset({"mattbook", "wootbook"})
IDENTITY_RELATIVE_PATH = Path(".config/ctx9/codefoldersync/backup-recovery.agekey")
PURPOSE = "codefoldersync-backup-recovery-acceptance"
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SAFE_RECIPIENT = re.compile(r"^age1[0-9a-z]{20,}$")


class LifecycleError(RuntimeError):
    """A safe lifecycle precondition or acceptance invariant failed."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_machine_id(machine_id: str) -> str:
    if machine_id not in RECOVERY_MACHINES:
        expected = ", ".join(sorted(RECOVERY_MACHINES))
        raise LifecycleError(f"recovery machine must be one of: {expected}")
    return machine_id


def validate_fixture_id(fixture_id: str) -> str:
    if not SAFE_ID.fullmatch(fixture_id):
        raise LifecycleError("fixture ID must be a lowercase filesystem-safe identifier")
    return fixture_id


def validate_recipient(recipient: str) -> str:
    if not SAFE_RECIPIENT.fullmatch(recipient):
        raise LifecycleError("invalid age recipient")
    return recipient


def identity_path(home: Path | None = None) -> Path:
    root = (home or Path.home()).expanduser()
    if not root.is_absolute():
        raise LifecycleError("home path must be absolute")
    return root / IDENTITY_RELATIVE_PATH


def custody_path() -> str:
    return f"~/{IDENTITY_RELATIVE_PATH.as_posix()}"


def require_command(name: str) -> str:
    command = shutil.which(name)
    if command is None:
        raise LifecycleError(f"required command is unavailable: {name}")
    return command


def run_text(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise LifecycleError(f"command failed without exposing private output: {Path(argv[0]).name}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LifecycleError(f"command timed out: {Path(argv[0]).name}") from exc


def run_bytes(argv: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            argv,
            input=input_bytes,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise LifecycleError(f"command failed without exposing private output: {Path(argv[0]).name}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LifecycleError(f"command timed out: {Path(argv[0]).name}") from exc


def validate_private_directory(path: Path) -> None:
    if path.is_symlink():
        raise LifecycleError(f"custody directory must not be a symlink: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o700:
        raise LifecycleError(f"custody directory mode must be 0700, found {mode:04o}")


def ensure_private_directory(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise LifecycleError(f"custody parent is not a directory: {path}")
        validate_private_directory(path)
        return
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    validate_private_directory(path)


def validate_identity(path: Path) -> None:
    if path.is_symlink():
        raise LifecycleError("recovery identity must not be a symlink")
    try:
        metadata = path.stat()
    except FileNotFoundError as exc:
        raise LifecycleError("recovery identity is missing") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise LifecycleError("recovery identity must be a regular file")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode != 0o600:
        raise LifecycleError(f"recovery identity mode must be 0600, found {mode:04o}")
    validate_private_directory(path.parent)


def derive_recipient(path: Path) -> str:
    validate_identity(path)
    age_keygen = require_command("age-keygen")
    result = run_text([age_keygen, "-y", str(path)])
    recipients = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(recipients) != 1:
        raise LifecycleError("recovery identity must contain exactly one age identity")
    return validate_recipient(recipients[0])


def recipient_fingerprint(recipient: str) -> str:
    return sha256_bytes((validate_recipient(recipient) + "\n").encode())


def inspect_identity(machine_id: str, path: Path) -> dict[str, Any]:
    validate_machine_id(machine_id)
    if not path.exists() and not path.is_symlink():
        return {
            "schema_version": SCHEMA_VERSION,
            "credential_id": CREDENTIAL_ID,
            "machine_id": machine_id,
            "custody_path": custody_path(),
            "status": "missing",
            "accepted": False,
        }
    recipient = derive_recipient(path)
    return {
        "schema_version": SCHEMA_VERSION,
        "credential_id": CREDENTIAL_ID,
        "machine_id": machine_id,
        "custody_path": custody_path(),
        "identity_mode": "0600",
        "recipient": recipient,
        "recipient_sha256": recipient_fingerprint(recipient),
        "status": "existing-unverified",
        "accepted": False,
    }


def preview_generation(machine_id: str, path: Path) -> dict[str, Any]:
    report = inspect_identity(machine_id, path)
    if report["status"] == "missing":
        report["status"] = "ready-to-generate"
    return report


def generate_identity(machine_id: str, path: Path) -> dict[str, Any]:
    validate_machine_id(machine_id)
    if path.exists() or path.is_symlink():
        raise LifecycleError("recovery identity already exists; inspect and verify it, never overwrite it")
    ensure_private_directory(path.parent)
    age_keygen = require_command("age-keygen")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".backup-recovery.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        run_text([age_keygen, "-o", str(temporary)])
        temporary.chmod(0o600)
        validate_identity(temporary)
        os.link(temporary, path)
        path.chmod(0o600)
    except FileExistsError as exc:
        raise LifecycleError("recovery identity appeared concurrently; no file was overwritten") from exc
    finally:
        temporary.unlink(missing_ok=True)
    recipient = derive_recipient(path)
    return {
        "schema_version": SCHEMA_VERSION,
        "credential_id": CREDENTIAL_ID,
        "machine_id": machine_id,
        "custody_path": custody_path(),
        "identity_mode": "0600",
        "recipient": recipient,
        "recipient_sha256": recipient_fingerprint(recipient),
        "status": "generated-unverified",
        "accepted": False,
    }


def fixture_plaintext(fixture_id: str) -> bytes:
    value = {
        "fixture_id": validate_fixture_id(fixture_id),
        "purpose": PURPOSE,
        "schema_version": SCHEMA_VERSION,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def validate_output_parent(path: Path) -> None:
    if not path.is_absolute():
        raise LifecycleError("output path must be absolute")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise LifecycleError("output parent must be an existing real directory")
    mode = stat.S_IMODE(path.parent.stat().st_mode)
    if mode & 0o077:
        raise LifecycleError("output parent must not be accessible by group or other users")


def fixture_preview(fixture_id: str, recipients: list[str], output: Path) -> dict[str, Any]:
    validate_output_parent(output)
    if output.exists() or output.is_symlink():
        raise LifecycleError("fixture ciphertext output already exists")
    accepted = sorted({validate_recipient(value) for value in recipients})
    if len(accepted) != len(RECOVERY_MACHINES):
        raise LifecycleError("fixture requires two distinct recovery recipients")
    plaintext = fixture_plaintext(fixture_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "purpose": PURPOSE,
        "ciphertext_name": output.name,
        "plaintext_sha256": sha256_bytes(plaintext),
        "recipient_sha256": [recipient_fingerprint(value) for value in accepted],
        "status": "ready-to-create",
    }


def create_fixture(fixture_id: str, recipients: list[str], output: Path) -> dict[str, Any]:
    preview = fixture_preview(fixture_id, recipients, output)
    age = require_command("age")
    accepted = sorted({validate_recipient(value) for value in recipients})
    plaintext = fixture_plaintext(fixture_id)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    argv = [age, "--encrypt"]
    for recipient in accepted:
        argv.extend(["--recipient", recipient])
    argv.extend(["--output", str(temporary)])
    try:
        run_bytes(argv, input_bytes=plaintext)
        temporary.chmod(0o600)
        os.link(temporary, output)
        output.chmod(0o600)
    except FileExistsError as exc:
        raise LifecycleError("fixture output appeared concurrently; no file was overwritten") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return {
        **{key: value for key, value in preview.items() if key != "status"},
        "ciphertext_sha256": sha256_file(output),
        "status": "created",
    }


FIXTURE_KEYS = frozenset(
    {
        "schema_version",
        "fixture_id",
        "purpose",
        "ciphertext_name",
        "ciphertext_sha256",
        "plaintext_sha256",
        "recipient_sha256",
        "status",
    }
)


def load_fixture_manifest(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if set(value) != FIXTURE_KEYS or value.get("status") != "created":
        raise LifecycleError("fixture manifest has an unsupported shape")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("purpose") != PURPOSE:
        raise LifecycleError("fixture manifest policy mismatch")
    validate_fixture_id(str(value.get("fixture_id", "")))
    fingerprints = value.get("recipient_sha256")
    if not isinstance(fingerprints, list) or len(fingerprints) != len(RECOVERY_MACHINES):
        raise LifecycleError("fixture manifest must bind both recovery recipients")
    if any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item) for item in fingerprints):
        raise LifecycleError("fixture manifest contains an invalid recipient fingerprint")
    for key in ("ciphertext_sha256", "plaintext_sha256"):
        if not isinstance(value.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise LifecycleError(f"fixture manifest contains an invalid {key}")
    return value


def verify_fixture(machine_id: str, path: Path, ciphertext: Path, manifest_path: Path) -> dict[str, Any]:
    validate_machine_id(machine_id)
    manifest = load_fixture_manifest(manifest_path)
    if ciphertext.name != manifest["ciphertext_name"]:
        raise LifecycleError("fixture ciphertext name does not match its manifest")
    if sha256_file(ciphertext) != manifest["ciphertext_sha256"]:
        raise LifecycleError("fixture ciphertext digest mismatch")
    recipient = derive_recipient(path)
    fingerprint = recipient_fingerprint(recipient)
    if fingerprint not in manifest["recipient_sha256"]:
        raise LifecycleError("identity recipient is not bound by the fixture manifest")
    age = require_command("age")
    result = run_bytes([age, "--decrypt", "--identity", str(path), str(ciphertext)])
    if sha256_bytes(result.stdout) != manifest["plaintext_sha256"]:
        raise LifecycleError("decrypted fixture digest mismatch")
    try:
        plaintext = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LifecycleError("decrypted fixture is not the declared JSON payload") from exc
    expected = json.loads(fixture_plaintext(manifest["fixture_id"]))
    if plaintext != expected:
        raise LifecycleError("decrypted fixture content mismatch")
    return {
        "schema_version": SCHEMA_VERSION,
        "credential_id": CREDENTIAL_ID,
        "machine_id": machine_id,
        "custody": "target-local-age-file",
        "custody_path": custody_path(),
        "identity_mode": "0600",
        "recipient": recipient,
        "recipient_sha256": fingerprint,
        "fixture_id": manifest["fixture_id"],
        "fixture_ciphertext_sha256": manifest["ciphertext_sha256"],
        "fixture_plaintext_sha256": manifest["plaintext_sha256"],
        "verified_at": utc_now(),
        "accepted": True,
    }


ACCEPTANCE_KEYS = frozenset(
    {
        "schema_version",
        "credential_id",
        "machine_id",
        "custody",
        "custody_path",
        "identity_mode",
        "recipient",
        "recipient_sha256",
        "fixture_id",
        "fixture_ciphertext_sha256",
        "fixture_plaintext_sha256",
        "verified_at",
        "accepted",
    }
)


def validate_acceptance_reports(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if len(reports) != len(RECOVERY_MACHINES):
        raise LifecycleError("exactly two recovery acceptance reports are required")
    by_machine: dict[str, dict[str, Any]] = {}
    for report in reports:
        if set(report) != ACCEPTANCE_KEYS:
            raise LifecycleError("acceptance report has an unsupported shape")
        machine_id = validate_machine_id(str(report.get("machine_id", "")))
        if machine_id in by_machine:
            raise LifecycleError("duplicate recovery machine acceptance report")
        if (
            report.get("schema_version") != SCHEMA_VERSION
            or report.get("credential_id") != CREDENTIAL_ID
            or report.get("custody") != "target-local-age-file"
            or report.get("custody_path") != custody_path()
            or report.get("identity_mode") != "0600"
            or report.get("accepted") is not True
        ):
            raise LifecycleError("acceptance report policy mismatch")
        recipient = validate_recipient(str(report.get("recipient", "")))
        if report.get("recipient_sha256") != recipient_fingerprint(recipient):
            raise LifecycleError("acceptance report recipient fingerprint mismatch")
        by_machine[machine_id] = report
    if set(by_machine) != RECOVERY_MACHINES:
        raise LifecycleError("acceptance reports do not cover both recovery machines")
    shared_fields = ("fixture_id", "fixture_ciphertext_sha256", "fixture_plaintext_sha256")
    if any(len({report[field] for report in reports}) != 1 for field in shared_fields):
        raise LifecycleError("recovery machines did not verify the same fixture")
    if len({report["recipient"] for report in reports}) != len(RECOVERY_MACHINES):
        raise LifecycleError("recovery identities must have distinct public recipients")
    return by_machine


def load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise LifecycleError(f"JSON input must be a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"invalid JSON input: {path}") from exc
    if not isinstance(value, dict):
        raise LifecycleError(f"JSON input must contain an object: {path}")
    return value


def accepted_state(reports: list[dict[str, Any]], state_path: Path) -> dict[str, Any]:
    by_machine = validate_acceptance_reports(reports)
    state = load_json(state_path)
    machines = state.get("machines")
    if state.get("schema_version") != SCHEMA_VERSION or not isinstance(machines, dict):
        raise LifecycleError("machine-secret lock has an unsupported shape")
    for machine_id, report in by_machine.items():
        machine = machines.get(machine_id)
        if not isinstance(machine, dict):
            raise LifecycleError(f"machine-secret lock is missing machine: {machine_id}")
        machine[CREDENTIAL_ID] = {
            key: report[key]
            for key in (
                "accepted",
                "custody",
                "custody_path",
                "fixture_ciphertext_sha256",
                "fixture_id",
                "fixture_plaintext_sha256",
                "identity_mode",
                "recipient",
                "recipient_sha256",
                "verified_at",
            )
        }
    return state


def atomic_replace_json(path: Path, value: dict[str, Any]) -> None:
    if path.is_symlink() or not path.is_file():
        raise LifecycleError("machine-secret lock must be an existing regular file")
    mode = stat.S_IMODE(path.stat().st_mode)
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    validate_output_parent(path)
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise LifecycleError(f"report output already exists: {path}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def emit(value: dict[str, Any], output: Path | None = None) -> None:
    if output is None:
        print(json.dumps(value, sort_keys=True))
    else:
        write_new_json(output, value)
        print(json.dumps({"output": str(output), "sha256": sha256_file(output)}, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    inspect = subcommands.add_parser("inspect", help="Report missing or existing-unverified identity state")
    inspect.add_argument("--machine-id", required=True)

    generate = subcommands.add_parser("generate", help="Preview or create one target-local identity")
    generate.add_argument("--machine-id", required=True)
    generate.add_argument("--report", type=Path)
    generate.add_argument("--apply", action="store_true")

    fixture = subcommands.add_parser("create-fixture", help="Preview or create one dual-recipient fixture")
    fixture.add_argument("--fixture-id", required=True)
    fixture.add_argument("--recipient", action="append", required=True)
    fixture.add_argument("--output", type=Path, required=True)
    fixture.add_argument("--report", type=Path)
    fixture.add_argument("--apply", action="store_true")

    verify = subcommands.add_parser("verify-fixture", help="Decrypt and verify a fixture without outputting plaintext")
    verify.add_argument("--machine-id", required=True)
    verify.add_argument("--ciphertext", type=Path, required=True)
    verify.add_argument("--fixture-manifest", type=Path, required=True)
    verify.add_argument("--report", type=Path)

    accept = subcommands.add_parser("accept", help="Preview or record a matched two-machine acceptance")
    accept.add_argument("--report", action="append", type=Path, required=True)
    accept.add_argument("--state-output", type=Path, required=True)
    accept.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = identity_path()
    if args.command == "inspect":
        emit(inspect_identity(args.machine_id, path))
    elif args.command == "generate":
        report = generate_identity(args.machine_id, path) if args.apply else preview_generation(args.machine_id, path)
        emit(report, args.report.expanduser() if args.report else None)
    elif args.command == "create-fixture":
        output = args.output.expanduser()
        report = (
            create_fixture(args.fixture_id, args.recipient, output)
            if args.apply
            else fixture_preview(args.fixture_id, args.recipient, output)
        )
        emit(report, args.report.expanduser() if args.report and args.apply else None)
    elif args.command == "verify-fixture":
        report = verify_fixture(
            args.machine_id,
            path,
            args.ciphertext.expanduser(),
            args.fixture_manifest.expanduser(),
        )
        emit(report, args.report.expanduser() if args.report else None)
    elif args.command == "accept":
        reports = [load_json(path.expanduser()) for path in args.report]
        state = accepted_state(reports, args.state_output.expanduser())
        summary = {
            "schema_version": SCHEMA_VERSION,
            "credential_id": CREDENTIAL_ID,
            "machines": sorted(RECOVERY_MACHINES),
            "fixture_id": reports[0]["fixture_id"],
            "status": "accepted" if args.apply else "ready-to-accept",
        }
        if args.apply:
            atomic_replace_json(args.state_output.expanduser(), state)
        emit(summary)
    else:  # pragma: no cover - argparse enforces the command set.
        raise LifecycleError("unsupported command")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LifecycleError, OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
