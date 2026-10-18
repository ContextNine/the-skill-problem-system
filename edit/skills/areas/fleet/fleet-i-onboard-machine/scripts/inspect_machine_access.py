#!/usr/bin/env python3
"""Report sanitized reachability, latency, and Tailscale path evidence for one machine."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any


class InspectError(RuntimeError):
    pass


def load_machine(path: Path, machine_id: str) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InspectError(f"cannot read registry {path}: {exc}") from exc
    matches = [item for item in registry.get("machines", []) if item.get("id") == machine_id]
    if len(matches) != 1:
        raise InspectError(f"machine {machine_id!r} did not resolve exactly once")
    return matches[0]


def provider_route(machine: dict[str, Any], requested_provider: str | None) -> tuple[str, str]:
    access = machine.get("machine_access")
    if not isinstance(access, dict):
        raise InspectError("machine_access missing")
    provider = requested_provider or access.get("provider")
    providers = access.get("providers")
    selected = providers.get(provider) if isinstance(providers, dict) else None
    if provider not in {"wireguard", "tailscale"} or not isinstance(selected, dict):
        raise InspectError("selected provider is invalid")
    if selected.get("state") != "configured" or not selected.get("host"):
        raise InspectError("selected provider route is pending")
    return str(provider), str(selected["host"])


def ssh_argv(machine: dict[str, Any], host: str, remote_command: str) -> list[str]:
    access = machine["machine_access"]
    alias = str(machine["ssh_alias"])
    return [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", f"HostName={host}",
        "-o", f"User={access['ssh_user']}",
        "-o", f"IdentityFile={access['identity_file']}",
        "-o", "IdentitiesOnly=yes",
        alias,
        remote_command,
    ]


def measure_ssh(machine: dict[str, Any], host: str, attempts: int) -> tuple[list[float], list[str]]:
    measurements: list[float] = []
    errors: list[str] = []
    for _ in range(attempts):
        started = time.monotonic()
        result = subprocess.run(
            ssh_argv(machine, host, "true"),
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        elapsed = (time.monotonic() - started) * 1000
        if result.returncode == 0:
            measurements.append(round(elapsed, 1))
        else:
            detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unreachable"
            errors.append(detail)
    return measurements, errors


def parse_key_values(output: str) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for token in output.strip().split():
        key, separator, value = token.partition("=")
        if separator and value.isdigit():
            parsed[key] = int(value)
    return parsed


def wireguard_evidence(machine: dict[str, Any], host: str) -> dict[str, Any]:
    if machine.get("platform") == "linux":
        remote = (
            "sudo -n wg show all dump | "
            "awk -F '\\t' 'NF >= 9 { peers++; if ($6 > latest) latest=$6; "
            "if ($9 == 25) keepalive25++ } END { printf "
            "\"peers=%d latest_handshake_epoch=%d keepalive25=%d\\n\", "
            "peers, latest, keepalive25 }'"
        )
    else:
        remote = (
            "/usr/sbin/scutil --nc list | "
            "awk '/WireGuard/ { total++; if ($0 ~ /\\(Connected\\)/) connected++ } "
            "END { printf \"tunnels=%d connected=%d\\n\", total, connected }'"
        )
    result = subprocess.run(
        ssh_argv(machine, host, remote),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
    )
    if result.returncode != 0:
        return {"available": False}
    values = parse_key_values(result.stdout)
    if machine.get("platform") == "linux":
        latest = values.get("latest_handshake_epoch", 0)
        return {
            "available": True,
            "peer_count": values.get("peers", 0),
            "keepalive_25_peer_count": values.get("keepalive25", 0),
            "latest_handshake_age_seconds": max(0, int(time.time()) - latest) if latest else None,
        }
    return {
        "available": True,
        "tunnel_count": values.get("tunnels", 0),
        "connected_tunnel_count": values.get("connected", 0),
        "note": "native macOS client does not expose peer keys or handshake timestamps to this probe",
    }


def tailscale_cli() -> str | None:
    discovered = shutil.which("tailscale")
    if discovered:
        return discovered
    bundled = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
    return str(bundled) if bundled.is_file() else None


def classify_tailscale_ping(output: str) -> str:
    classification = "unknown"
    for line in output.splitlines():
        if "via peer-relay(" in line:
            classification = "peer-relay"
        elif "via DERP(" in line:
            classification = "derp"
        elif re.search(r"\bvia\s+(?:\d{1,3}\.){3}\d{1,3}:\d+\b", line):
            classification = "direct"
        elif re.search(r"\bvia\s+\[[0-9a-fA-F:]+\]:\d+\b", line):
            classification = "direct"
    return classification


def tailscale_evidence(host: str) -> dict[str, Any]:
    command = tailscale_cli()
    if not command:
        return {"available": False}
    environment = dict(os.environ)
    environment["TAILSCALE_BE_CLI"] = "1"
    ping = subprocess.run(
        [command, "ping", "--c", "5", host],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        env=environment,
    )
    netcheck = subprocess.run(
        [command, "netcheck"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        env=environment,
    )
    udp = re.search(r"(?m)^\s*UDP:\s*(true|false)", netcheck.stdout, re.IGNORECASE)
    nearest = re.search(r"(?m)^\s*Nearest DERP:\s*([^\r\n]+)", netcheck.stdout)
    return {
        "available": True,
        "ping_ok": ping.returncode == 0,
        "connection_type": classify_tailscale_ping(ping.stdout),
        "netcheck_ok": netcheck.returncode == 0,
        "udp": udp.group(1).casefold() == "true" if udp else None,
        "nearest_derp": nearest.group(1).strip() if nearest else None,
    }


def inspect(
    path: Path,
    machine_id: str,
    attempts: int,
    requested_provider: str | None,
) -> dict[str, Any]:
    machine = load_machine(path, machine_id)
    provider, host = provider_route(machine, requested_provider)
    alias = f"{machine['ssh_alias']}-mesh"
    measurements, errors = measure_ssh(machine, host, attempts)
    result: dict[str, Any] = {
        "machine_id": machine_id,
        "provider": provider,
        "mesh_host": host,
        "mesh_alias": alias,
        "route_mode": "forced-provider-probe",
        "attempts": attempts,
        "successful_attempts": len(measurements),
        "ssh_ms": measurements,
        "median_ssh_ms": round(statistics.median(measurements), 1) if measurements else None,
        "errors": errors,
    }
    if provider == "tailscale":
        result["tailscale"] = tailscale_evidence(host)
    else:
        result["wireguard"] = wireguard_evidence(machine, host)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("machine_id")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--provider", choices=("wireguard", "tailscale"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.attempts <= 10:
        raise InspectError("attempts must be between 1 and 10")
    result = inspect(args.registry.expanduser(), args.machine_id, args.attempts, args.provider)
    print(json.dumps(result, indent=2))
    return 0 if result["successful_attempts"] == result["attempts"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (InspectError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
