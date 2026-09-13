#!/usr/bin/env python3
"""Trust a new SSH hostname by reusing one exact, already trusted host key."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile


HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:-]*$")
FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]+$")


class TrustError(RuntimeError):
    pass


def validate_host(value: str, label: str) -> str:
    if not HOST_RE.fullmatch(value):
        raise TrustError(f"unsafe {label}: {value!r}")
    return value


def fingerprint(key_data: str) -> str:
    try:
        decoded = base64.b64decode(key_data, validate=True)
    except ValueError as exc:
        raise TrustError("known_hosts contains invalid host-key data") from exc
    digest = base64.b64encode(hashlib.sha256(decoded).digest()).decode().rstrip("=")
    return f"SHA256:{digest}"


def hashed_host_matches(pattern: str, host: str) -> bool:
    parts = pattern.split("|")
    if len(parts) != 4 or parts[0] or parts[1] != "1":
        return False
    try:
        salt = base64.b64decode(parts[2], validate=True)
        expected = base64.b64decode(parts[3], validate=True)
    except ValueError:
        return False
    actual = hmac.new(salt, host.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(actual, expected)


def host_field_matches(field: str, host: str) -> bool:
    for pattern in field.split(","):
        if pattern == host or hashed_host_matches(pattern, host):
            return True
    return False


def host_records(content: str, host: str, key_type: str) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if fields[0].startswith("@"):
            continue
        if len(fields) < 3:
            continue
        host_field, record_key_type, key_data = fields[:3]
        if record_key_type == key_type and host_field_matches(host_field, host):
            records.append((key_data, fingerprint(key_data)))
    return records


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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


def reconcile(
    known_hosts: Path,
    *,
    source_host: str,
    target_host: str,
    expected_fingerprint: str,
    key_type: str,
    mode: str,
) -> dict[str, object]:
    source_host = validate_host(source_host, "source host")
    target_host = validate_host(target_host, "target host")
    if source_host == target_host:
        raise TrustError("source and target hosts must differ")
    if not FINGERPRINT_RE.fullmatch(expected_fingerprint):
        raise TrustError("expected fingerprint must be an OpenSSH SHA256 fingerprint")

    content = known_hosts.read_text(encoding="utf-8") if known_hosts.is_file() else ""
    matching_sources = {
        key_data
        for key_data, actual_fingerprint in host_records(content, source_host, key_type)
        if actual_fingerprint == expected_fingerprint
    }
    if not matching_sources:
        raise TrustError(
            f"{source_host} has no trusted {key_type} record matching {expected_fingerprint}"
        )
    if len(matching_sources) != 1:
        raise TrustError(f"{source_host} resolves to multiple matching {key_type} keys")
    source_key = next(iter(matching_sources))

    target_records = host_records(content, target_host, key_type)
    conflicting = sorted(
        {actual_fingerprint for _, actual_fingerprint in target_records}
        - {expected_fingerprint}
    )
    if conflicting:
        raise TrustError(
            f"{target_host} already has a conflicting {key_type} record: {', '.join(conflicting)}"
        )
    ready = any(
        key_data == source_key and actual_fingerprint == expected_fingerprint
        for key_data, actual_fingerprint in target_records
    )
    report: dict[str, object] = {
        "source_host": source_host,
        "target_host": target_host,
        "key_type": key_type,
        "fingerprint": expected_fingerprint,
        "ready": ready,
        "mode": mode,
    }
    if mode == "verify" or ready:
        report["action"] = "none" if ready else "missing"
        return report
    if mode == "dry-run":
        report["action"] = "would-add-exact-trusted-alias"
        return report

    suffix = "" if not content or content.endswith("\n") else "\n"
    write_atomic(known_hosts, f"{content}{suffix}{target_host} {key_type} {source_key}\n")
    report["ready"] = True
    report["action"] = "added-exact-trusted-alias"
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-host", required=True)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--expected-fingerprint", required=True)
    parser.add_argument("--key-type", default="ssh-ed25519")
    parser.add_argument("--known-hosts", type=Path, default=Path.home() / ".ssh/known_hosts")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected_mode = "apply" if args.apply else "verify" if args.verify else "dry-run"
    report = reconcile(
        args.known_hosts.expanduser(),
        source_host=args.source_host,
        target_host=args.target_host,
        expected_fingerprint=args.expected_fingerprint,
        key_type=args.key_type,
        mode=selected_mode,
    )
    print(json.dumps(report, indent=2))
    return 0 if selected_mode != "verify" or report["ready"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TrustError, ValueError) as exc:
        print(json.dumps({"ready": False, "error": str(exc)}))
        raise SystemExit(2)
