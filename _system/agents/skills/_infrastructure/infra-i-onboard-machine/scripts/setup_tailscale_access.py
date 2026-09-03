#!/usr/bin/env python3
"""Install, configure, and report Tailscale without storing authentication state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen


STABLE_PACKAGES_URL = "https://pkgs.tailscale.com/stable/"
LINUX_INSTALL_URL = "https://tailscale.com/install.sh"
TAILSCALE_TEAM_ID = "W5364U7YZB"
MAC_CLI = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
MAC_APP = "/Applications/Tailscale.app"
REMOTE_LINUX_INSTALLER = "/tmp/ctx9-tailscale-install.sh"


class SetupError(RuntimeError):
    pass


def load_machine(path: Path, machine_id: str) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"cannot read registry {path}: {exc}") from exc
    matches = [item for item in registry.get("machines", []) if item.get("id") == machine_id]
    if len(matches) != 1:
        raise SetupError(f"machine {machine_id!r} did not resolve exactly once")
    return matches[0]


def tailscale_settings(machine: dict[str, Any]) -> tuple[str, str, dict[str, bool | str]]:
    access = machine.get("machine_access")
    providers = access.get("providers") if isinstance(access, dict) else None
    provider = providers.get("tailscale") if isinstance(providers, dict) else None
    desired = provider.get("desired_state") if isinstance(provider, dict) else None
    variant = provider.get("client_variant") if isinstance(provider, dict) else None
    if not isinstance(desired, dict) or not isinstance(variant, str):
        raise SetupError("pending Tailscale provider with client_variant and desired_state is required")
    required = {
        "device_name": str,
        "accept_dns": bool,
        "accept_routes": bool,
        "tailscale_ssh": bool,
    }
    for key, expected in required.items():
        if not isinstance(desired.get(key), expected):
            raise SetupError(f"Tailscale desired_state.{key} is missing or invalid")
    if machine.get("platform") == "macos" and variant not in {"standalone", "app-store"}:
        raise SetupError("macOS Tailscale client_variant must be standalone or app-store")
    if machine.get("platform") == "linux" and variant != "linux-package":
        raise SetupError("Linux Tailscale client_variant must be linux-package")
    return str(machine["id"]), variant, desired


def target_prefix(machine: dict[str, Any]) -> list[str]:
    if machine.get("transport") == "local":
        return []
    alias = machine.get("ssh_alias")
    if machine.get("transport") != "ssh" or not isinstance(alias, str):
        raise SetupError("machine transport must be local or SSH with a canonical alias")
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", alias]


def run_target(
    machine: dict[str, Any],
    argv: list[str],
    *,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    prefix = target_prefix(machine)
    command = argv if not prefix else [*prefix, shlex.join(argv)]
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def target_has(machine: dict[str, Any], path_or_command: str) -> bool:
    if path_or_command.startswith("/"):
        probe = ["test", "-x", path_or_command]
    else:
        probe = ["sh", "-lc", f"command -v {shlex.quote(path_or_command)} >/dev/null"]
    return run_target(machine, probe).returncode == 0


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "vault-infra-i-onboard-machine/1"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def latest_macos_pkg_url(index_html: str) -> str:
    matches = re.findall(r'href="(Tailscale-([0-9.]+)-macos\.pkg)"', index_html)
    if not matches:
        raise SetupError("official stable package page did not list a macOS package")
    filename, _ = max(matches, key=lambda item: version_tuple(item[1]))
    return urljoin(STABLE_PACKAGES_URL, filename)


def verify_macos_pkg(path: Path) -> None:
    signature = subprocess.run(
        ["pkgutil", "--check-signature", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    if signature.returncode != 0 or f"({TAILSCALE_TEAM_ID})" not in signature.stdout:
        raise SetupError("macOS package is not signed by the expected Tailscale installer identity")
    assessment = subprocess.run(
        ["spctl", "-a", "-vv", "-t", "install", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    if assessment.returncode != 0:
        raise SetupError("macOS rejected the Tailscale installer assessment")


def stage_remote_macos_pkg(
    machine: dict[str, Any],
    local_path: Path,
    package_url: str,
    target_path: str,
    digest: str,
) -> None:
    alias = str(machine["ssh_alias"])
    existing_digest = run_target(machine, ["/usr/bin/shasum", "-a", "256", target_path])
    if existing_digest.returncode == 0 and existing_digest.stdout.split(maxsplit=1)[0] == digest:
        return

    if existing_digest.returncode == 0:
        copied = None
    else:
        try:
            copied = subprocess.run(
                ["scp", "-q", str(local_path), f"{alias}:{target_path}"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            copied = None

    if copied is None or copied.returncode != 0:
        download_path = f"{target_path}.download"
        downloaded = run_target(
            machine,
            [
                "/usr/bin/curl",
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--retry",
                "3",
                "--connect-timeout",
                "20",
                "--max-time",
                "600",
                "--output",
                download_path,
                package_url,
            ],
            timeout=660,
        )
        if downloaded.returncode != 0:
            run_target(machine, ["rm", "-f", download_path])
            raise SetupError("could not stage the verified macOS package on the target")
        downloaded_digest = run_target(machine, ["/usr/bin/shasum", "-a", "256", download_path])
        if downloaded_digest.returncode != 0 or downloaded_digest.stdout.split(maxsplit=1)[0] != digest:
            run_target(machine, ["rm", "-f", download_path])
            raise SetupError("target download did not match the locally verified macOS package")
        moved = run_target(machine, ["mv", "-f", download_path, target_path])
        if moved.returncode != 0:
            raise SetupError("target could not finalize the verified macOS package")

    staged_digest = run_target(machine, ["/usr/bin/shasum", "-a", "256", target_path])
    if staged_digest.returncode != 0 or staged_digest.stdout.split(maxsplit=1)[0] != digest:
        raise SetupError("staged macOS package does not match the locally verified payload")


def stage_macos_installer(machine: dict[str, Any]) -> tuple[str, str]:
    package_url = latest_macos_pkg_url(fetch(STABLE_PACKAGES_URL).decode("utf-8"))
    filename = package_url.rsplit("/", 1)[-1]
    local_path = Path(tempfile.gettempdir()) / filename
    payload = fetch(package_url)
    local_path.write_bytes(payload)
    verify_macos_pkg(local_path)
    digest = hashlib.sha256(payload).hexdigest()
    if machine.get("transport") == "local":
        target_path = str(local_path)
    else:
        target_path = f"/tmp/{filename}"
        stage_remote_macos_pkg(machine, local_path, package_url, target_path, digest)
        checked = run_target(machine, ["pkgutil", "--check-signature", target_path])
        if checked.returncode != 0 or f"({TAILSCALE_TEAM_ID})" not in checked.stdout:
            raise SetupError("target did not verify the expected Tailscale installer identity")
    opened = run_target(machine, ["open", target_path])
    if opened.returncode != 0:
        raise SetupError(f"verified package is staged at {target_path}, but Installer did not open")
    return target_path, digest


def stage_and_run_linux_installer(machine: dict[str, Any]) -> tuple[str | None, str]:
    payload = fetch(LINUX_INSTALL_URL)
    digest = hashlib.sha256(payload).hexdigest()
    local_path = Path(tempfile.gettempdir()) / "ctx9-tailscale-install.sh"
    local_path.write_bytes(payload)
    syntax = subprocess.run(
        ["sh", "-n", str(local_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if syntax.returncode != 0:
        raise SetupError("official Linux installer failed shell syntax validation")
    if machine.get("transport") == "local":
        staged_path = str(local_path)
    else:
        alias = str(machine["ssh_alias"])
        staged_path = REMOTE_LINUX_INSTALLER
        copied = subprocess.run(
            ["scp", "-q", str(local_path), f"{alias}:{staged_path}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        if copied.returncode != 0:
            raise SetupError("could not stage the official Linux installer on the target")
    installed = run_target(machine, ["sudo", "-n", "sh", staged_path], timeout=180)
    if installed.returncode == 0:
        return None, digest
    alias = machine.get("ssh_alias")
    if isinstance(alias, str):
        return f"ssh -t {shlex.quote(alias)} 'sudo sh {REMOTE_LINUX_INSTALLER}'", digest
    return f"sudo sh {shlex.quote(staged_path)}", digest


def tailscale_cli(machine: dict[str, Any]) -> str:
    if machine.get("platform") == "macos":
        return MAC_CLI
    return "tailscale"


def desired_up_argv(machine: dict[str, Any], desired: dict[str, bool | str]) -> list[str]:
    command = [
        tailscale_cli(machine),
        "up",
        f"--hostname={desired['device_name']}",
        f"--accept-dns={str(desired['accept_dns']).lower()}",
        f"--accept-routes={str(desired['accept_routes']).lower()}",
        f"--ssh={str(desired['tailscale_ssh']).lower()}",
        "--timeout=10s",
    ]
    if machine.get("platform") == "linux":
        return ["sudo", "-n", *command]
    return ["env", "TAILSCALE_BE_CLI=1", *command]


def sanitized_status(machine: dict[str, Any]) -> dict[str, Any]:
    cli = tailscale_cli(machine)
    prefix = ["env", "TAILSCALE_BE_CLI=1"] if machine.get("platform") == "macos" else []
    result = run_target(machine, [*prefix, cli, "status", "--json"])
    if result.returncode != 0:
        return {"backend_state": "Unavailable", "dns_name": None, "tailscale_ips": []}
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"backend_state": "Unavailable", "dns_name": None, "tailscale_ips": []}
    self_state = raw.get("Self") if isinstance(raw.get("Self"), dict) else {}
    dns_name = self_state.get("DNSName")
    ips = self_state.get("TailscaleIPs")
    return {
        "backend_state": raw.get("BackendState", "Unknown"),
        "dns_name": dns_name.rstrip(".") if isinstance(dns_name, str) and dns_name else None,
        "tailscale_ips": [item for item in ips if isinstance(item, str)] if isinstance(ips, list) else [],
    }


def auth_url(output: str) -> str | None:
    match = re.search(r"https://login\.tailscale\.com/[A-Za-z0-9/_-]+", output)
    return match.group(0) if match else None


def install_if_needed(
    machine: dict[str, Any],
    variant: str,
    apply: bool,
) -> tuple[bool, str | None, dict[str, str]]:
    installed = target_has(machine, MAC_CLI if machine.get("platform") == "macos" else "tailscale")
    if installed or not apply:
        return installed, None, {}
    if machine.get("platform") == "macos":
        if variant == "app-store":
            return False, (
                "Install the deliberately selected App Store variant, complete its VPN approval, "
                "then rerun this command."
            ), {}
        target_path, digest = stage_macos_installer(machine)
        return False, (
            f"Complete the protected Installer and Tailscale VPN approval for {target_path}; "
            f"verified SHA-256 {digest}. Then rerun this command."
        ), {"installer_sha256": digest}
    if machine.get("platform") == "linux":
        manual, digest = stage_and_run_linux_installer(machine)
        if manual:
            return False, (
                f"The official installer is staged with SHA-256 {digest}. "
                f"Run `{manual}`, then rerun this command."
            ), {"installer_sha256": digest}
        return target_has(machine, "tailscale"), None, {"installer_sha256": digest}
    raise SetupError("only macOS and Linux targets are supported")


def setup(machine: dict[str, Any], apply: bool) -> tuple[int, dict[str, Any]]:
    machine_id, variant, desired = tailscale_settings(machine)
    installed, checkpoint, install_evidence = install_if_needed(machine, variant, apply)
    report: dict[str, Any] = {
        "machine_id": machine_id,
        "client_variant": variant,
        "desired_state": desired,
        "installed": installed,
        "mode": "apply" if apply else "preview",
    }
    report.update(install_evidence)
    if checkpoint:
        report["checkpoint"] = checkpoint
        return 3, report
    if not installed:
        report["planned_action"] = "install the official Tailscale client, then apply desired state"
        return 0, report
    before = sanitized_status(machine)
    report["status_before"] = before
    if apply:
        applied = run_target(machine, desired_up_argv(machine, desired), timeout=45)
        url = auth_url(f"{applied.stdout}\n{applied.stderr}")
        after = sanitized_status(machine)
        report["status_after"] = after
        if after["backend_state"] != "Running":
            report["checkpoint"] = (
                f"Authenticate {machine_id} in the intended personal tailnet"
                + (f" at {url}" if url else " in the Tailscale app")
                + ", approve any VPN prompt, then rerun this command."
            )
            return 3, report
        if not after["dns_name"]:
            report["checkpoint"] = (
                "Tailscale is running but did not report a stable MagicDNS name. "
                "Enable MagicDNS for the personal tailnet, then rerun this command."
            )
            return 3, report
        report["next_command"] = (
            f"vault machine access configure {shlex.quote(machine_id)} tailscale "
            f"--host {shlex.quote(str(after['dns_name']))} --client-variant {shlex.quote(variant)} --apply"
        )
    else:
        report["planned_action"] = "apply registry-owned Tailscale settings and stop for login if needed"
    return 0, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("machine_id")
    parser.add_argument("--registry", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    machine = load_machine(args.registry.expanduser(), args.machine_id)
    code, report = setup(machine, args.apply)
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SetupError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
