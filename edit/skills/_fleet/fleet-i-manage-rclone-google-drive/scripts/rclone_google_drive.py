#!/usr/bin/env python3
"""Safely manage CodeFolderSync backup ciphertext in its dedicated Drive root."""

from __future__ import annotations

import argparse
import configparser
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import uuid


SKILL_ID = "fleet-i-manage-rclone-google-drive"
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]*")
SAFE_REMOTE = re.compile(r"[a-z0-9][a-z0-9_]*")
SHA256 = re.compile(r"[0-9a-f]{64}")
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
SSH_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
REMOTE_SCRIPT = re.compile(r"/[A-Za-z0-9._/-]+")
BINDINGS_CHILD_MARKER = "CTX9_RCLONE_SECRET_BINDINGS_CHILD"
MAX_OAUTH_TOKEN_BYTES = 64 * 1024
ALLOWED_DRIVE_SCOPES = frozenset({"drive.file", "drive.file,drive.readonly"})


class BackupError(RuntimeError):
    """A safe, user-facing backup contract failure."""


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BackupError(f"cannot read {label}") from error
    if not isinstance(value, dict):
        raise BackupError(f"{label} must be a JSON object")
    return value


def default_desired_path() -> Path:
    completed = subprocess.run(
        ["fleet", "config", "path"], check=False, capture_output=True, text=True
    )
    root = completed.stdout.strip()
    if completed.returncode != 0 or not root:
        raise BackupError("installed agent configuration is unavailable")
    return Path(root) / "skills/config" / SKILL_ID / "desired.json"


def safe_component(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise BackupError(f"{label} is missing or unsafe")
    if "/" in value or "\\" in value or ":" in value or any(ord(character) < 32 for character in value):
        raise BackupError(f"{label} is missing or unsafe")
    return value


def validate_desired(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != 2 or not isinstance(value.get("enabled"), bool):
        raise BackupError("desired state needs schema_version 2 and enabled")
    remote_name = value.get("remote_name")
    machines = value.get("allowed_machines")
    drive = value.get("google_drive")
    paths = value.get("paths")
    retention = value.get("retention")
    if not isinstance(remote_name, str) or not SAFE_REMOTE.fullmatch(remote_name):
        raise BackupError("desired remote_name is unsafe")
    if not isinstance(machines, list) or not all(
        isinstance(machine, str) and SAFE_ID.fullmatch(machine) for machine in machines
    ):
        raise BackupError("desired allowed_machines is invalid")
    if value["enabled"] and not machines:
        raise BackupError("enabled backup needs at least one allowed machine")
    if len(set(machines)) != len(machines):
        raise BackupError("desired allowed_machines contains duplicates")
    if not isinstance(drive, dict) or drive.get("scope") not in ALLOWED_DRIVE_SCOPES:
        raise BackupError(
            "Google Drive scope must be drive.file or drive.file,drive.readonly"
        )
    if not isinstance(paths, dict):
        raise BackupError("desired paths are missing")
    safe_component(paths.get("backup_prefix"), "backup prefix")
    safe_component(paths.get("acceptance_prefix"), "acceptance prefix")
    if not isinstance(retention, dict) or retention.get("mode") != "explicit-retirement-only":
        raise BackupError("retention mode must be explicit-retirement-only")
    if retention.get("automatic_deletion") is not False:
        raise BackupError("automatic retention deletion is forbidden")
    if "oauth_client_id" in drive or "oauth_client_secret" in drive:
        raise BackupError("raw OAuth application credentials are forbidden in desired state")
    for field in ("oauth_client_id_binding", "oauth_client_secret_binding"):
        item = drive.get(field)
        if not isinstance(item, str) or not ENV_NAME.fullmatch(item):
            raise BackupError(f"Google Drive {field} must be an environment binding name")
    for field in ("shared_drive_id", "root_folder_id"):
        item = drive.get(field)
        if item is not None and (not isinstance(item, str) or not item.strip()):
            raise BackupError(f"Google Drive {field} must be a non-empty string or null")
    return value


def desired_missing(desired: dict[str, Any]) -> list[str]:
    drive = desired["google_drive"]
    missing = [] if desired["enabled"] else ["enabled"]
    if not desired["allowed_machines"]:
        missing.append("allowed_machines")
    missing.extend(
        f"google_drive.{field}"
        for field in (
            "oauth_client_id_binding",
            "oauth_client_secret_binding",
            "shared_drive_id",
            "root_folder_id",
        )
        if not drive.get(field)
    )
    return missing


def require_machine(desired: dict[str, Any], machine_id: str) -> None:
    if not SAFE_ID.fullmatch(machine_id) or machine_id not in desired["allowed_machines"]:
        raise BackupError("machine is not allowed by desired state")


def require_configured(desired: dict[str, Any]) -> None:
    missing = desired_missing(desired)
    if missing:
        raise BackupError("desired Google Drive setup is incomplete: " + ", ".join(missing))


def password_command(machine_id: str) -> str:
    helper = Path(__file__).with_name("rclone_config_unlock.py").resolve()
    fields = [
        str(Path(sys.executable).resolve()),
        str(helper),
        "read",
        "--machine-id",
        machine_id,
    ]
    output = io.StringIO()
    csv.writer(output, delimiter=" ", quotechar='"', lineterminator="").writerow(fields)
    return output.getvalue()


def binding_environment(desired: dict[str, Any]) -> dict[str, str]:
    if os.environ.get(BINDINGS_CHILD_MARKER) != "1":
        raise BackupError("OAuth application credentials must come from Secret Bindings")
    drive = desired["google_drive"]
    client_id_name = drive["oauth_client_id_binding"]
    client_secret_name = drive["oauth_client_secret_binding"]
    client_id = os.environ.get(client_id_name)
    client_secret = os.environ.get(client_secret_name)
    if not client_id or not client_secret:
        raise BackupError("required OAuth application bindings are unavailable")
    environment = os.environ.copy()
    environment.pop(client_id_name, None)
    environment.pop(client_secret_name, None)
    environment.pop(BINDINGS_CHILD_MARKER, None)
    remote = re.sub(r"[^A-Za-z0-9]", "_", desired["remote_name"]).upper()
    environment[f"RCLONE_CONFIG_{remote}_CLIENT_ID"] = client_id
    environment[f"RCLONE_CONFIG_{remote}_CLIENT_SECRET"] = client_secret
    environment["RCLONE_DRIVE_CLIENT_ID"] = client_id
    environment["RCLONE_DRIVE_CLIENT_SECRET"] = client_secret
    environment["RCLONE_DRIVE_SCOPE"] = drive["scope"]
    environment.pop("RCLONE_CONFIG_PASS", None)
    environment.pop("RCLONE_PASSWORD_COMMAND", None)
    return environment


def redact_sensitive(value: str, sensitive_values: list[str]) -> str:
    redacted = value
    for sensitive in sensitive_values:
        if sensitive:
            redacted = redacted.replace(sensitive, "[REDACTED]")
    return redacted


def classify_rclone_failure(output: str) -> str:
    lowered = output.lower()
    categories = (
        ("insufficient authentication scopes", "insufficient_scope"),
        ("insufficientpermissions", "permission_denied"),
        ("permission denied", "permission_denied"),
        ("couldn't find root directory", "root_not_found"),
        ("root folder id", "root_not_found"),
        ("not found", "not_found"),
        ("error 404", "not_found"),
        ("error 403", "permission_denied"),
        ("error 401", "authentication_failed"),
    )
    for marker, category in categories:
        if marker in lowered:
            return category
    return "unclassified"


def canonical_oauth_token(value: str) -> str:
    if not value or len(value.encode("utf-8")) > MAX_OAUTH_TOKEN_BYTES:
        raise BackupError("OAuth token response is missing or too large")
    try:
        token = json.loads(value)
    except json.JSONDecodeError as error:
        raise BackupError("OAuth token response is unreadable") from error
    if not isinstance(token, dict):
        raise BackupError("OAuth token response is invalid")
    for field in ("access_token", "refresh_token", "token_type"):
        if not isinstance(token.get(field), str) or not token[field]:
            raise BackupError("OAuth token response is incomplete")
    return json.dumps(token, separators=(",", ":"), sort_keys=True)


def extract_oauth_token(output: str) -> str:
    decoder = json.JSONDecoder()
    for offset, character in enumerate(output):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(output[offset:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and all(
            isinstance(value.get(field), str) and value[field]
            for field in ("access_token", "refresh_token", "token_type")
        ):
            return canonical_oauth_token(json.dumps(value))
    raise BackupError("Rclone authorization did not return a usable token")


class Rclone:
    def __init__(self, executable: str, desired: dict[str, Any], machine_id: str) -> None:
        resolved = shutil.which(executable) if "/" not in executable else executable
        if not resolved or not Path(resolved).is_file():
            raise BackupError("rclone is not installed")
        self.executable = str(Path(resolved).resolve())
        self.desired = desired
        self.machine_id = machine_id

    def _environment(self) -> dict[str, str]:
        return binding_environment(self.desired)

    def command(self, *arguments: str) -> list[str]:
        return [
            self.executable,
            "--password-command",
            password_command(self.machine_id),
            "--ask-password=false",
            "--log-level",
            "ERROR",
            "--stats",
            "0",
            *arguments,
        ]

    def run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            self.command(*arguments),
            check=False,
            capture_output=True,
            text=True,
            env=self._environment(),
        )
        if completed.returncode != 0:
            category = classify_rclone_failure(completed.stdout + completed.stderr)
            raise BackupError(
                f"rclone command failed with exit {completed.returncode} ({category})"
            )
        return completed

    def run_oauth(self, *arguments: str) -> None:
        environment = self._environment()
        remote = re.sub(r"[^A-Za-z0-9]", "_", self.desired["remote_name"]).upper()
        sensitive_values = [
            environment[f"RCLONE_CONFIG_{remote}_CLIENT_ID"],
            environment[f"RCLONE_CONFIG_{remote}_CLIENT_SECRET"],
        ]
        process = subprocess.Popen(
            self.command(*arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=environment,
        )
        assert process.stdout is not None
        try:
            for line in process.stdout:
                sys.stdout.write(redact_sensitive(line, sensitive_values))
                sys.stdout.flush()
            return_code = process.wait()
        except BaseException:
            process.terminate()
            process.wait()
            raise
        if return_code != 0:
            raise BackupError(f"rclone OAuth command failed with exit {return_code}")

    def authorize_token(self) -> str:
        completed = subprocess.run(
            [
                self.executable,
                "--log-level",
                "ERROR",
                "--stats",
                "0",
                "authorize",
                "drive",
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=self._environment(),
        )
        if completed.returncode != 0:
            raise BackupError(f"rclone remote authorization failed with exit {completed.returncode}")
        return extract_oauth_token(completed.stdout)

    def run_oauth_input(self, token: str, *arguments: str) -> None:
        completed = subprocess.run(
            self.command(*arguments),
            check=False,
            input=canonical_oauth_token(token) + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=self._environment(),
        )
        if completed.returncode != 0:
            raise BackupError(f"rclone remote configuration failed with exit {completed.returncode}")


def remote_path(desired: dict[str, Any], *components: str) -> str:
    safe = [safe_component(component, "remote path component") for component in components]
    return f"{desired['remote_name']}:" + "/".join(safe)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_bundle(root: Path, snapshot_id: str, machine_id: str) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise BackupError("backup source must be a real directory")
    entries = list(root.iterdir())
    if not entries or any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise BackupError("backup bundle must contain flat regular files only")
    witness_path = root / "witness.json"
    witness = load_json(witness_path, "ciphertext witness")
    artifacts = witness.get("artifacts")
    if (
        witness.get("schema_version") != 1
        or witness.get("snapshot_id") != snapshot_id
        or witness.get("machine_id") != machine_id
        or not isinstance(artifacts, list)
        or not artifacts
    ):
        raise BackupError("ciphertext witness identity or schema does not match")
    expected = {"witness.json"}
    total = witness_path.stat().st_size
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise BackupError("ciphertext witness has an invalid artifact")
        name = artifact.get("name")
        size = artifact.get("size")
        digest = artifact.get("sha256")
        if (
            not isinstance(name, str)
            or not SAFE_ID.fullmatch(name)
            or not name.endswith(".age")
            or not isinstance(size, int)
            or size < 0
            or not isinstance(digest, str)
            or not SHA256.fullmatch(digest)
        ):
            raise BackupError("ciphertext witness has an invalid artifact contract")
        if name in expected:
            raise BackupError("ciphertext witness contains duplicate artifacts")
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise BackupError("ciphertext witness references a missing artifact")
        if path.stat().st_size != size or sha256_file(path) != digest:
            raise BackupError("ciphertext artifact does not match its witness")
        expected.add(name)
        total += size
    if {entry.name for entry in entries} != expected:
        raise BackupError("backup bundle contains unbound files")
    return {"artifact_count": len(artifacts), "file_count": len(expected), "total_bytes": total}


def parse_config(text: str, remote_name: str) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error as error:
        raise BackupError("rclone returned an unreadable configuration") from error
    if remote_name not in parser:
        raise BackupError("desired Rclone remote is missing")
    return dict(parser[remote_name])


def verify_remote(rclone: Rclone, live: bool) -> dict[str, Any]:
    desired = rclone.desired
    rclone.run("config", "encryption", "check")
    configuration = rclone.run("config", "show", desired["remote_name"]).stdout
    actual = parse_config(configuration, desired["remote_name"])
    drive = desired["google_drive"]
    matches = {
        "type": actual.get("type") == "drive",
        "oauth_client_id_not_persisted": not actual.get("client_id"),
        "scope": actual.get("scope") == drive["scope"],
        "shared_drive_id": actual.get("team_drive") == drive["shared_drive_id"],
        "root_folder_id": actual.get("root_folder_id") == drive["root_folder_id"],
        "client_secret_not_persisted": not actual.get("client_secret"),
    }
    if not all(matches.values()):
        raise BackupError("Rclone configuration does not match desired policy")
    if live:
        rclone.run("lsf", f"{desired['remote_name']}:", "--max-depth", "1")
    return {"ready": True, "encrypted": True, "matches": matches, "live_read": live}


def require_absent_encrypted_remote(rclone: Rclone) -> None:
    desired = rclone.desired
    try:
        rclone.run("config", "encryption", "check")
    except BackupError:
        readable = rclone.run("listremotes")
        if readable.stdout.strip():
            raise BackupError(
                "unencrypted Rclone configuration is not empty; refusing automatic encryption"
            )
        rclone.run("config", "encryption", "set")
        rclone.run("config", "encryption", "check")

    configured = {
        line.strip().removesuffix(":")
        for line in rclone.run("listremotes").stdout.splitlines()
        if line.strip()
    }
    if desired["remote_name"] in configured:
        raise BackupError("desired Rclone remote already exists; verify it instead of replacing it")


def configure_remote(rclone: Rclone) -> dict[str, Any]:
    desired = rclone.desired
    require_absent_encrypted_remote(rclone)
    drive = desired["google_drive"]
    rclone.run_oauth(
        "config",
        "create",
        desired["remote_name"],
        "drive",
        "scope",
        drive["scope"],
        "team_drive",
        drive["shared_drive_id"],
        "root_folder_id",
        drive["root_folder_id"],
        "config_is_local",
        "true",
        "--no-output",
    )
    return verify_remote(rclone, live=False)


def configure_remote_from_token(rclone: Rclone, token: str) -> dict[str, Any]:
    desired = rclone.desired
    require_absent_encrypted_remote(rclone)
    drive = desired["google_drive"]
    rclone.run_oauth_input(
        token,
        "config",
        "create",
        desired["remote_name"],
        "drive",
        "scope",
        drive["scope"],
        "team_drive",
        drive["shared_drive_id"],
        "root_folder_id",
        drive["root_folder_id"],
        "config_is_local",
        "false",
        "--no-output",
    )
    return verify_remote(rclone, live=False)


def reauthorize_remote(rclone: Rclone) -> dict[str, Any]:
    desired = rclone.desired
    rclone.run("config", "encryption", "check")
    configuration = rclone.run("config", "show", desired["remote_name"]).stdout
    actual = parse_config(configuration, desired["remote_name"])
    drive = desired["google_drive"]
    safe_existing_remote = {
        "type": actual.get("type") == "drive",
        "oauth_client_id_not_persisted": not actual.get("client_id"),
        "shared_drive_id": actual.get("team_drive") == drive["shared_drive_id"],
        "root_folder_id": actual.get("root_folder_id") == drive["root_folder_id"],
        "client_secret_not_persisted": not actual.get("client_secret"),
    }
    if not all(safe_existing_remote.values()):
        raise BackupError("existing Rclone remote is not safe to reauthorize")
    rclone.run_oauth(
        "config",
        "update",
        desired["remote_name"],
        "scope",
        drive["scope"],
        "config_is_local",
        "true",
        "--no-output",
    )
    return verify_remote(rclone, live=False)


def configure_remote_over_ssh(
    rclone: Rclone,
    target_machine_id: str,
    ssh_alias: str,
    target_script: str,
) -> dict[str, Any]:
    require_machine(rclone.desired, target_machine_id)
    if target_machine_id == rclone.machine_id:
        raise BackupError("remote configuration target must be another machine")
    if not SSH_ALIAS.fullmatch(ssh_alias):
        raise BackupError("SSH alias is unsafe")
    if not REMOTE_SCRIPT.fullmatch(target_script):
        raise BackupError("target controller path must be absolute and safe")
    token = rclone.authorize_token()
    completed = subprocess.run(
        [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            ssh_alias,
            "python3",
            target_script,
            "configure-token",
            "--machine-id",
            target_machine_id,
            "--approve",
        ],
        check=False,
        input=token + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.returncode != 0:
        raise BackupError(f"remote Rclone configuration failed with exit {completed.returncode}")
    return {
        "ready": True,
        "target_machine_id": target_machine_id,
        "token_transfer": "authenticated-ssh-stdin",
        "remote_output_returned": False,
    }


def command_plan(desired: dict[str, Any], machine_id: str, executable: str) -> dict[str, Any]:
    require_machine(desired, machine_id)
    missing = desired_missing(desired)
    resolved = shutil.which(executable) if "/" not in executable else executable
    installed = bool(resolved and Path(resolved).is_file())
    actions = []
    if not installed:
        actions.append("preview and approve rclone installation through fleet-i-update-dependencies")
    if missing:
        actions.append("complete and review non-secret desired Google Drive identifiers")
    actions.extend(
        [
            "save the OAuth application credentials as reviewed Secret Bindings personal globals",
            "generate the target-local config unlock through fleet-i-onboard-machine",
            "complete target-local OAuth and encrypted Rclone configuration",
            "verify policy and run the approved acceptance sentinel",
        ]
    )
    return {
        "machine_id": machine_id,
        "ready_for_live_configuration": installed and not missing,
        "rclone_installed": installed,
        "desired_missing": missing,
        "actions": actions,
    }


def command_acceptance(rclone: Rclone) -> dict[str, Any]:
    desired = rclone.desired
    run_id = uuid.uuid4().hex
    prefix = desired["paths"]["backup_prefix"]
    acceptance = desired["paths"]["acceptance_prefix"]
    target_dir = remote_path(desired, prefix, acceptance, rclone.machine_id, run_id)
    target_file = target_dir + "/sentinel.bin"
    uploaded = False
    cleanup = False
    with tempfile.TemporaryDirectory(prefix="ctx9-rclone-acceptance-") as temporary:
        root = Path(temporary)
        source = root / "source"
        download = root / "download"
        source.mkdir(mode=0o700)
        download.mkdir(mode=0o700)
        sentinel = source / "sentinel.bin"
        sentinel.write_bytes(secrets.token_bytes(64 * 1024))
        expected = sha256_file(sentinel)
        try:
            rclone.run("copyto", str(sentinel), target_file, "--immutable")
            uploaded = True
            rclone.run("check", str(source), target_dir, "--download", "--one-way")
            rclone.run("copyto", target_file, str(download / "sentinel.bin"), "--immutable")
            if sha256_file(download / "sentinel.bin") != expected:
                raise BackupError("acceptance sentinel digest mismatch")
        finally:
            if uploaded:
                try:
                    rclone.run("deletefile", target_file)
                    rclone.run("rmdir", target_dir)
                    cleanup = True
                except BackupError:
                    cleanup = False
    if not cleanup:
        raise BackupError("acceptance data passed but exact sentinel cleanup needs review")
    return {"ready": True, "bytes": 64 * 1024, "sha256_match": True, "cleanup": True}


def command_backup(rclone: Rclone, source: Path, snapshot_id: str) -> dict[str, Any]:
    summary = validate_bundle(source, snapshot_id, rclone.machine_id)
    desired = rclone.desired
    target = remote_path(
        desired, desired["paths"]["backup_prefix"], "snapshots", snapshot_id, rclone.machine_id
    )
    rclone.run("copy", str(source), target, "--immutable")
    rclone.run("check", str(source), target, "--download", "--one-way")
    listed = rclone.run("lsjson", target, "--recursive", "--files-only").stdout
    try:
        remote_entries = json.loads(listed)
    except json.JSONDecodeError as error:
        raise BackupError("rclone returned an unreadable remote inventory") from error
    if not isinstance(remote_entries, list) or any(not isinstance(entry, dict) for entry in remote_entries):
        raise BackupError("rclone returned an invalid remote inventory")
    sizes = [entry.get("Size") for entry in remote_entries]
    if any(not isinstance(size, int) or size < 0 for size in sizes):
        raise BackupError("rclone returned an invalid remote inventory")
    remote_bytes = sum(sizes)
    if len(remote_entries) != summary["file_count"] or remote_bytes != summary["total_bytes"]:
        raise BackupError("remote aggregate inventory does not match the ciphertext bundle")
    return {**summary, "remote_file_count": len(remote_entries), "remote_bytes": remote_bytes, "verified": True}


def command_download(
    rclone: Rclone, destination: Path, snapshot_id: str, source_machine_id: str
) -> dict[str, Any]:
    if destination.exists():
        raise BackupError("download destination must not exist")
    destination.mkdir(parents=True, mode=0o700)
    desired = rclone.desired
    source = remote_path(
        desired, desired["paths"]["backup_prefix"], "snapshots", snapshot_id, source_machine_id
    )
    rclone.run("copy", source, str(destination), "--immutable")
    summary = validate_bundle(destination, snapshot_id, source_machine_id)
    return {**summary, "verified": True, "destination_created": True}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desired", type=Path)
    parser.add_argument("--rclone", default="rclone")
    parser.add_argument("--bindings-child", action="store_true", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in (
        "plan",
        "configure",
        "reauthorize",
        "configure-token",
        "remote-configure",
        "verify",
        "acceptance-test",
        "retirement-plan",
    ):
        command = subparsers.add_parser(name)
        command.add_argument("--machine-id", required=True)
        if name in {
            "configure",
            "reauthorize",
            "configure-token",
            "remote-configure",
            "acceptance-test",
        }:
            command.add_argument("--approve", action="store_true")
        if name == "verify":
            command.add_argument("--live", action="store_true")
        if name == "remote-configure":
            command.add_argument("--target-machine-id", required=True)
            command.add_argument("--ssh-alias", required=True)
            command.add_argument("--target-script", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("--machine-id", required=True)
    backup.add_argument("--snapshot-id", required=True)
    backup.add_argument("--source", type=Path, required=True)
    backup.add_argument("--approve", action="store_true")
    download = subparsers.add_parser("download")
    download.add_argument("--machine-id", required=True)
    download.add_argument("--source-machine-id", required=True)
    download.add_argument("--snapshot-id", required=True)
    download.add_argument("--destination", type=Path, required=True)
    download.add_argument("--approve", action="store_true")
    return parser


def approved(arguments: argparse.Namespace) -> None:
    if not getattr(arguments, "approve", False):
        raise BackupError("live mutation requires --approve")


def child_arguments(arguments: argparse.Namespace, desired_path: Path) -> list[str]:
    result = [
        "--desired",
        str(desired_path),
        "--rclone",
        arguments.rclone,
        "--bindings-child",
        arguments.command,
        "--machine-id",
        arguments.machine_id,
    ]
    if arguments.command == "verify" and arguments.live:
        result.append("--live")
    if arguments.command in {
        "configure",
        "reauthorize",
        "acceptance-test",
        "backup",
        "download",
    }:
        result.append("--approve")
    if arguments.command in {"configure-token", "remote-configure"}:
        result.append("--approve")
    if arguments.command == "remote-configure":
        result.extend(
            [
                "--target-machine-id",
                arguments.target_machine_id,
                "--ssh-alias",
                arguments.ssh_alias,
                "--target-script",
                arguments.target_script,
            ]
        )
    if arguments.command == "backup":
        result.extend(["--snapshot-id", arguments.snapshot_id, "--source", str(arguments.source.resolve())])
    if arguments.command == "download":
        result.extend(
            [
                "--source-machine-id",
                arguments.source_machine_id,
                "--snapshot-id",
                arguments.snapshot_id,
                "--destination",
                str(arguments.destination.resolve()),
            ]
        )
    return result


def run_with_secret_bindings(arguments: argparse.Namespace, desired_path: Path) -> int:
    executable = shutil.which("secret-bindings")
    if not executable:
        raise BackupError("Secret Bindings CLI is unavailable")
    drive = validate_desired(load_json(desired_path, "Rclone Google Drive desired state"))["google_drive"]
    binding_names = [drive["oauth_client_id_binding"], drive["oauth_client_secret_binding"]]
    with tempfile.TemporaryDirectory(prefix="ctx9-rclone-bindings-") as temporary:
        root = Path(temporary)
        initialized = subprocess.run(
            ["git", "init", "--quiet", str(root)], check=False, capture_output=True, text=True
        )
        if initialized.returncode != 0:
            raise BackupError("cannot create the value-free Secret Bindings contract")
        (root / ".env.base").write_text(
            "".join(f"{name}=\n" for name in binding_names), encoding="utf-8"
        )
        environment = os.environ.copy()
        environment[BINDINGS_CHILD_MARKER] = "1"
        completed = subprocess.run(
            [
                executable,
                "exec",
                "--globals",
                "--environment",
                "local",
                "--contract",
                ".env.base",
                "--",
                str(Path(sys.executable).resolve()),
                str(Path(__file__).resolve()),
                *child_arguments(arguments, desired_path),
            ],
            cwd=root,
            env=environment,
            check=False,
        )
        return completed.returncode


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        desired_path = (arguments.desired or default_desired_path()).resolve()
        desired = validate_desired(load_json(desired_path, "Rclone Google Drive desired state"))
        require_machine(desired, arguments.machine_id)
        if arguments.command == "plan":
            emit(command_plan(desired, arguments.machine_id, arguments.rclone))
            return 0
        if arguments.command == "retirement-plan":
            emit(
                {
                    "machine_id": arguments.machine_id,
                    "mutating": False,
                    "steps": [
                        "disable new uploads",
                        "prove an accepted restore through both recovery identities",
                        "record a final aggregate remote witness",
                        "obtain explicit snapshot-disposition approval",
                        "revoke target-local OAuth and native records",
                        "remove the configured remote without deleting retained snapshots",
                    ],
                }
            )
            return 0
        require_configured(desired)
        if arguments.command in {
            "configure",
            "reauthorize",
            "configure-token",
            "remote-configure",
            "acceptance-test",
            "backup",
            "download",
        }:
            approved(arguments)
        if not arguments.bindings_child:
            return run_with_secret_bindings(arguments, desired_path)
        rclone = Rclone(arguments.rclone, desired, arguments.machine_id)
        if arguments.command == "configure":
            emit(configure_remote(rclone))
        elif arguments.command == "reauthorize":
            emit(reauthorize_remote(rclone))
        elif arguments.command == "configure-token":
            token = sys.stdin.read(MAX_OAUTH_TOKEN_BYTES + 1)
            emit(configure_remote_from_token(rclone, canonical_oauth_token(token.strip())))
        elif arguments.command == "remote-configure":
            emit(
                configure_remote_over_ssh(
                    rclone,
                    arguments.target_machine_id,
                    arguments.ssh_alias,
                    arguments.target_script,
                )
            )
        elif arguments.command == "verify":
            emit(verify_remote(rclone, arguments.live))
        elif arguments.command == "acceptance-test":
            emit(command_acceptance(rclone))
        elif arguments.command == "backup":
            if not SAFE_ID.fullmatch(arguments.snapshot_id):
                raise BackupError("snapshot id is unsafe")
            emit(command_backup(rclone, arguments.source.resolve(), arguments.snapshot_id))
        elif arguments.command == "download":
            if not SAFE_ID.fullmatch(arguments.snapshot_id):
                raise BackupError("snapshot id is unsafe")
            require_machine(desired, arguments.source_machine_id)
            emit(
                command_download(
                    rclone,
                    arguments.destination.resolve(),
                    arguments.snapshot_id,
                    arguments.source_machine_id,
                )
            )
        return 0
    except BackupError as error:
        emit({"ready": False, "error": str(error)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
