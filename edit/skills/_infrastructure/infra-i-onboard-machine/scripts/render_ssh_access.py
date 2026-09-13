#!/usr/bin/env python3
"""Render provider-neutral fleet SSH aliases from the tracked machine registry."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import sys
from typing import Any


INCLUDE_LINE = "Include ~/.ssh/config.d/*"
MANAGED_HEADER = "# Managed by infra-i-onboard-machine. Edit the machine registry, not this file."
REGISTRY_SCHEMA_VERSION = 7
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/~-]*$")
SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")


class RenderError(RuntimeError):
    pass


def safe_token(value: Any, label: str) -> str:
    token = str(value or "")
    if not token or not SAFE_TOKEN.fullmatch(token):
        raise RenderError(f"unsafe {label}: {token!r}")
    return token


def safe_identity_file(value: Any, label: str) -> str:
    identity_file = str(value or "")
    if not identity_file.startswith("~/.ssh/") or not SAFE_PATH.fullmatch(identity_file[2:]):
        raise RenderError(f"unsafe {label}: {identity_file!r}")
    return identity_file


def load_registry(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(f"cannot read registry {path}: {exc}") from exc
    if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise RenderError(
            f"machine registry schema_version must be {REGISTRY_SCHEMA_VERSION}"
        )
    if not isinstance(payload.get("machines"), list):
        raise RenderError("machine registry has no machines")
    return payload


def render_machine(
    machine: dict[str, Any],
    *,
    identity_file_override: str | None = None,
    allow_local_target: bool = False,
    use_keychain: bool = False,
) -> str | None:
    if machine.get("transport") != "ssh" and not allow_local_target:
        return None
    machine_id = safe_token(machine.get("id"), "machine id")
    alias = safe_token(machine.get("ssh_alias"), f"SSH alias for {machine_id}")
    if alias != machine_id:
        raise RenderError(f"canonical SSH alias must equal machine ID for {machine_id}")
    access = machine.get("machine_access")
    if not isinstance(access, dict):
        raise RenderError(f"machine_access missing for {machine_id}")
    provider = access.get("provider")
    providers = access.get("providers")
    if provider not in {"wireguard", "tailscale"} or not isinstance(providers, dict):
        raise RenderError(f"selected provider invalid for {machine_id}")
    selected = providers.get(provider)
    if not isinstance(selected, dict) or selected.get("state") != "configured":
        return None
    mesh_host = safe_token(selected.get("host"), f"mesh host for {machine_id}")
    ssh_user = safe_token(access.get("ssh_user"), f"SSH user for {machine_id}")
    identity_file = safe_identity_file(
        identity_file_override or access.get("identity_file"),
        f"identity file for {machine_id}",
    )
    lan_host_value = access.get("lan_host")
    lan_host = safe_token(lan_host_value, f"LAN host for {machine_id}") if lan_host_value else None

    aliases = f"{alias} {alias}-mesh"
    if lan_host:
        aliases += f" {alias}-lan"
    lines = [
        f"Host {aliases}",
        f"    User {ssh_user}",
        f"    IdentityFile {identity_file}",
        "    IdentitiesOnly yes",
        "    BatchMode yes",
        "    PasswordAuthentication no",
        "    KbdInteractiveAuthentication no",
        "    StrictHostKeyChecking yes",
    ]
    if use_keychain:
        # macOS can recover a protected fleet identity from Keychain after login or
        # reboot, then repopulate the native agent on the first SSH connection.
        lines.extend(
            [
                "    UseKeychain yes",
                "    AddKeysToAgent yes",
            ]
        )
    lines.append("")
    if lan_host:
        lines.extend(
            [
                f"Host {alias}-lan",
                f"    HostName {lan_host}",
                "",
            ]
        )
    lines.extend(
        [
            f"Host {alias}-mesh",
            f"    HostName {mesh_host}",
            "",
        ]
    )
    if lan_host:
        timeout_flag = "-G 1" if platform.system() == "Darwin" else "-w 1"
        lines.extend(
            [
                f'Match originalhost {alias} exec "/usr/bin/nc -z {timeout_flag} {lan_host} 22 >/dev/null 2>&1"',
                f"    HostName {lan_host}",
                "",
                f"Match originalhost {alias}",
                f"    HostName {mesh_host}",
                "",
            ]
        )
    else:
        lines.extend([f"Host {alias}", f"    HostName {mesh_host}", ""])
    return "\n".join(lines)


def source_machine(registry: dict[str, Any], source_machine_id: str) -> dict[str, Any]:
    matches = [machine for machine in registry["machines"] if machine.get("id") == source_machine_id]
    if len(matches) != 1:
        raise RenderError(f"source machine {source_machine_id!r} did not resolve exactly once")
    return matches[0]


def source_identity_file(source: dict[str, Any]) -> str:
    fleet_shell = source.get("fleet_shell")
    if not isinstance(fleet_shell, dict):
        raise RenderError(f"fleet_shell missing for source machine {source.get('id')}")
    return safe_identity_file(
        fleet_shell.get("identity_file"),
        f"fleet-shell identity for source machine {source.get('id')}",
    )


def render_registry(
    registry: dict[str, Any],
    *,
    source_machine_id: str | None = None,
) -> str:
    sections = [MANAGED_HEADER, ""]
    source: dict[str, Any] | None = None
    identity_file: str | None = None
    primary_machine_id = str(registry.get("primary_machine_id") or "")
    if source_machine_id:
        source = source_machine(registry, source_machine_id)
        identity_file = source_identity_file(source)
    use_keychain = (
        source.get("platform") == "macos"
        if source is not None
        else platform.system() == "Darwin"
    )
    for machine in registry["machines"]:
        if source is not None:
            if machine.get("id") == source_machine_id:
                continue
            # The primary retains aliases for disabled onboarding targets. Workers only
            # receive the accepted enabled fleet so disabled machines stay excluded.
            if source_machine_id != primary_machine_id and not machine.get("enabled"):
                continue
        section = render_machine(
            machine,
            identity_file_override=identity_file,
            allow_local_target=source is not None,
            use_keychain=use_keychain,
        )
        if section:
            sections.extend([section.rstrip(), ""])
    return "\n".join(sections).rstrip() + "\n"


def ensure_include(content: str) -> str:
    lines = content.splitlines()
    matching = [index for index, line in enumerate(lines) if line.strip() == INCLUDE_LINE]
    if not matching:
        return INCLUDE_LINE + "\n" + content.lstrip("\n")
    if len(matching) == 1:
        return content if content.endswith("\n") else content + "\n"
    first = matching[0]
    deduplicated = [line for index, line in enumerate(lines) if index == first or line.strip() != INCLUDE_LINE]
    return "\n".join(deduplicated).rstrip() + "\n"


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def apply_render(
    *,
    registry_path: Path,
    ssh_config: Path,
    output: Path,
    apply: bool,
    source_machine_id: str | None = None,
) -> int:
    registry = load_registry(registry_path)
    rendered = render_registry(registry, source_machine_id=source_machine_id)
    try:
        existing_config = ssh_config.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing_config = ""
    updated_config = ensure_include(existing_config)
    if not apply:
        if updated_config != existing_config:
            print(f"DRY RUN: ensure {INCLUDE_LINE!r} in {ssh_config}")
        print(f"DRY RUN: write {output}")
        print(rendered, end="")
        return 0
    if updated_config != existing_config:
        write_atomic(ssh_config, updated_config)
        print(f"updated {ssh_config}")
    write_atomic(output, rendered)
    print(f"wrote {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument(
        "--source-machine-id",
        help="render aliases and the fleet-shell identity for this source machine",
    )
    parser.add_argument("--ssh-config", type=Path, default=Path.home() / ".ssh/config")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / ".ssh/config.d/vault-machine-access.conf",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return apply_render(
        registry_path=args.registry.expanduser(),
        ssh_config=args.ssh_config.expanduser(),
        output=args.output.expanduser(),
        apply=args.apply,
        source_machine_id=args.source_machine_id,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RenderError, OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
