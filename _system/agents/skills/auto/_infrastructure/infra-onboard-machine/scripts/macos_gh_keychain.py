#!/usr/bin/env python3
"""Repair gh OAuth storage in macOS Keychain without exposing the token."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


HOST = "github.com"
SERVICE = f"gh:{HOST}"


class RepairError(RuntimeError):
    """A deterministic secure-storage repair failure."""


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        env=env,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def without_plaintext_tokens(hosts: bytes) -> bytes:
    lines = hosts.splitlines(keepends=True)
    return b"".join(
        line for line in lines if not re.match(rb"^[ \t]*oauth_token:", line)
    )


def atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    try:
        if sys.platform != "darwin":
            raise RepairError("this helper is restricted to macOS")
        gh = shutil.which("gh")
        security = shutil.which("security") or "/usr/bin/security"
        if not gh or not Path(security).is_file():
            raise RepairError("gh and the macOS security tool are required")

        hosts_path = Path.home() / ".config/gh/hosts.yml"
        original = hosts_path.read_bytes()
        token_result = run([gh, "auth", "token", "--hostname", HOST])
        token = token_result.stdout.strip()
        if token_result.returncode != 0 or not token:
            raise RepairError("the existing gh token is unavailable")
        user_result = run([gh, "api", "user", "--jq", ".login"])
        username = user_result.stdout.decode(errors="replace").strip()
        if user_result.returncode != 0 or not re.fullmatch(r"[A-Za-z0-9-]+", username):
            raise RepairError("the existing token did not resolve one safe GitHub username")

        for account in (username, ""):
            deleted = run(
                [security, "delete-generic-password", "-s", SERVICE, "-a", account]
            )
            if deleted.returncode not in {0, 44}:
                raise RepairError("could not replace the exact gh Keychain records")

        login = run(
            [
                gh,
                "auth",
                "login",
                "--hostname",
                HOST,
                "--git-protocol",
                "ssh",
                "--skip-ssh-key",
                "--with-token",
            ],
            input_bytes=token + b"\n",
        )
        if login.returncode != 0:
            atomic_write(hosts_path, original)
            raise RepairError("gh could not recreate its Keychain records")

        sanitized = without_plaintext_tokens(hosts_path.read_bytes())
        with tempfile.TemporaryDirectory(prefix="ctx9-gh-keychain-proof.") as directory:
            proof_dir = Path(directory)
            proof_hosts = proof_dir / "hosts.yml"
            proof_hosts.write_bytes(sanitized)
            proof_hosts.chmod(0o600)
            proof_env = {**os.environ, "GH_CONFIG_DIR": str(proof_dir)}
            status = run([gh, "auth", "status", "--hostname", HOST], env=proof_env)
            api = run([gh, "api", "user", "--jq", ".login"], env=proof_env)
            if (
                status.returncode != 0
                or api.returncode != 0
                or api.stdout.decode(errors="replace").strip() != username
            ):
                atomic_write(hosts_path, original)
                raise RepairError("Keychain-only proof failed; plaintext config was restored")

        atomic_write(hosts_path, sanitized)
        final_status = run([gh, "auth", "status", "--hostname", HOST])
        final_api = run([gh, "api", "user", "--jq", ".login"])
        if final_status.returncode != 0 or final_api.returncode != 0:
            atomic_write(hosts_path, original)
            raise RepairError("final gh verification failed; plaintext config was restored")
        print("macOS Keychain-only gh OAuth verified")
        return 0
    except (OSError, RepairError) as exc:
        print(f"macOS gh Keychain repair failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
