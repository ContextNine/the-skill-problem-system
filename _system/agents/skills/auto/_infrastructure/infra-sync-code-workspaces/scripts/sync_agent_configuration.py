#!/usr/bin/env python3
"""Sync primary-owned Codex and Claude user configuration across the fleet."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
from typing import Any

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))


def resolve_agent_scripts_directory() -> Path:
    """Resolve package code from either its Vault source or standalone install."""
    vault_source = SCRIPT_DIRECTORY.parents[4] / "_package/src"
    if (vault_source / "global_agent_configuration.py").is_file():
        return vault_source

    commands = [["ctx9-agents", "verify"]]
    local_launcher = Path.home() / ".local/bin/ctx9-agents"
    if local_launcher.is_file():
        commands.append([str(local_launcher), "verify"])
    for command in commands:
        try:
            process = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            report = json.loads(process.stdout) if process.returncode == 0 else {}
        except (OSError, json.JSONDecodeError):
            continue
        package = report.get("package") if isinstance(report, dict) else None
        installed_source = Path(package) / "src" if isinstance(package, str) else None
        if installed_source and (installed_source / "global_agent_configuration.py").is_file():
            return installed_source

    raise RuntimeError("cannot resolve the ctx9-agents package runtime; install and verify ctx9-agents first")


AGENT_SCRIPTS_DIRECTORY = resolve_agent_scripts_directory()
if str(AGENT_SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(AGENT_SCRIPTS_DIRECTORY))

import global_agent_configuration


DEFAULT_REMOTE_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
SENSITIVE_NAME = re.compile(r"(?:^|_)(?:API_?KEY|PASSWORD|PRIVATE_?KEY|SECRET|TOKEN|CREDENTIAL)(?:$|_)", re.IGNORECASE)
CREDENTIAL_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@", re.IGNORECASE)
LANGFUSE_CONFIG_RELATIVE = Path("_system/agents/_package/instance/integrations/langfuse.json")


def run(command: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=stdin,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def output(process: subprocess.CompletedProcess[str]) -> str:
    return process.stdout.strip()


def error_text(process: subprocess.CompletedProcess[str]) -> str:
    value = (process.stderr or process.stdout).strip()
    return value.splitlines()[-1][:500] if value else "command failed"


def vault_root() -> Path:
    resolved = run(["vault", "root"])
    if resolved.returncode == 0 and output(resolved):
        return Path(output(resolved)).resolve()
    fallback = run(["git", "rev-parse", "--show-toplevel"])
    if fallback.returncode == 0 and output(fallback):
        return Path(output(fallback)).resolve()
    raise RuntimeError("cannot resolve the Vault root")


def current_machine_id(root: Path) -> str:
    identity = run(["git", "-C", str(root), "config", "--get", "vault.machine-id"])
    if identity.returncode == 0 and output(identity):
        return output(identity)
    marker = Path.home() / ".config/vault/machine-id"
    value = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
    if not value:
        raise RuntimeError("current machine has no Vault identity")
    return value


def load_registry(path: Path) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"machine registry is missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"machine registry is invalid: {exc}") from exc
    version = registry.get("schema_version") if isinstance(registry, dict) else None
    machines = registry.get("machines") if isinstance(registry, dict) else None
    primary = registry.get("primary_machine_id") if isinstance(registry, dict) else None
    if not isinstance(version, int) or version < 1:
        raise RuntimeError("machine registry needs a positive integer schema_version")
    if not isinstance(machines, list) or not machines:
        raise RuntimeError("machine registry has no machines")
    if not isinstance(primary, str) or not primary:
        raise RuntimeError("machine registry has no primary_machine_id")
    return registry


def require_primary(registry: dict[str, Any], source_id: str) -> None:
    if source_id != registry["primary_machine_id"]:
        raise RuntimeError(
            f"agent configuration is primary-owned; current machine is {source_id}, "
            f"expected {registry['primary_machine_id']}"
        )


def resolve_targets(
    registry: dict[str, Any],
    source_id: str,
    requested: list[str],
    *,
    provision_disabled: bool = False,
) -> list[dict[str, Any]]:
    machines = [machine for machine in registry["machines"] if isinstance(machine, dict)]
    if provision_disabled and len(requested) != 1:
        raise RuntimeError("--provision-disabled requires exactly one explicit --target")
    if requested:
        selected: list[dict[str, Any]] = []
        for value in requested:
            matches = [
                machine
                for machine in machines
                if value.casefold()
                in {
                    str(machine.get("id", "")).casefold(),
                    str(machine.get("display_name", "")).casefold(),
                }
            ]
            if len(matches) != 1:
                raise RuntimeError(f"target {value!r} did not resolve to exactly one machine")
            machine = matches[0]
            if machine.get("id") == source_id:
                raise RuntimeError(f"target {value!r} is the primary source machine")
            if provision_disabled:
                if machine.get("enabled"):
                    raise RuntimeError(f"target {value!r} is already enabled")
            else:
                if not machine.get("enabled"):
                    raise RuntimeError(f"target {value!r} is disabled")
                if machine.get("global_agents_eligible") is not True:
                    raise RuntimeError(f"target {value!r} is not eligible for personal agent configuration")
            if machine not in selected:
                selected.append(machine)
    else:
        selected = [
            machine
            for machine in machines
            if machine.get("enabled")
            and machine.get("global_agents_eligible") is True
            and machine.get("id") != source_id
        ]
    if not selected:
        raise RuntimeError("no eligible target machines remain")
    for machine in selected:
        required = {"id", "display_name", "transport", "home", "role", "platform"}
        missing = sorted(required - set(machine))
        if missing:
            raise RuntimeError(f"target {machine.get('id', '<unknown>')} missing: {', '.join(missing)}")
        if machine.get("transport") != "ssh" or not machine.get("ssh_alias"):
            raise RuntimeError(f"target {machine['id']} lacks supported SSH transport")
        home = str(machine["home"])
        if not PurePosixPath(home).is_absolute() or any(character.isspace() for character in home):
            raise RuntimeError(f"target {machine['id']} has an unsafe home path")
        if machine["role"] not in {"primary", "worker"} or machine["platform"] not in {"macos", "linux"}:
            raise RuntimeError(f"target {machine['id']} has an unsupported role or platform")
    return selected


def validate_codex_settings(text: str) -> None:
    table = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            table = line[1:-1].strip()
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip().strip('"')
        if table.endswith(".env") and SENSITIVE_NAME.search(key):
            raise RuntimeError(
                f"Codex config contains a credential-like inline environment setting at [{table}] {key}; "
                "keep the value machine-local or load it through the env workflow"
            )
        if CREDENTIAL_URL.search(value):
            raise RuntimeError("Codex config contains a credential-bearing URL; keep credentials machine-local")


def validate_claude_settings(value: object, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            credential_like_env = path and path[-1] == "env" and SENSITIVE_NAME.search(str(key))
            if credential_like_env and child is not None and child != "":
                raise RuntimeError(
                    f"Claude settings contain a credential-like inline environment setting at {'.'.join(child_path)}; "
                    "keep the value machine-local or load it through the env workflow"
                )
            validate_claude_settings(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_claude_settings(child, (*path, str(index)))
    elif isinstance(value, str) and CREDENTIAL_URL.search(value):
        raise RuntimeError("Claude settings contain a credential-bearing URL; keep credentials machine-local")


def load_langfuse_config(root: Path) -> str | None:
    path = root / LANGFUSE_CONFIG_RELATIVE
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Langfuse coding-agent metadata is missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Langfuse coding-agent metadata is invalid: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise RuntimeError("Langfuse coding-agent metadata needs schema_version 2")
    if not isinstance(value.get("instance_id"), str) or not value["instance_id"]:
        raise RuntimeError("Langfuse coding-agent metadata needs instance_id")
    if value.get("enabled") is not True:
        if value.get("base_url") is not None:
            raise RuntimeError("disabled Langfuse metadata must not retain a base_url")
        return None
    base_url = value.get("base_url")
    if not isinstance(base_url, str) or not base_url.startswith("https://"):
        raise RuntimeError("enabled Langfuse coding-agent metadata needs an HTTPS base_url")
    if not isinstance(value.get("credential_registry_id"), str) or not value["credential_registry_id"]:
        raise RuntimeError("Langfuse coding-agent metadata needs credential_registry_id")
    serialized = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if re.search(r'"(?:public_key|secret_key|authorization)"\s*:', serialized, re.IGNORECASE):
        raise RuntimeError("Langfuse coding-agent metadata must not contain credentials or authorization headers")
    return serialized


def load_instance_files(root: Path) -> list[dict[str, object]]:
    """Project the value-free private desired state into the installed config root."""
    source = root / "_system/agents/_package/instance"
    if not source.is_dir():
        raise RuntimeError(f"agent instance configuration is missing: {source}")
    files: list[dict[str, object]] = []
    for path in sorted(source.rglob("*")):
        if path.name == ".DS_Store":
            continue
        if path.is_symlink():
            raise RuntimeError(f"agent instance configuration cannot contain symlinks: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        files.append(
            {
                "path": f".config/ctx9/agents/{relative}",
                "kind": "file",
                "mode": 0o600,
                "content": base64.b64encode(path.read_bytes()).decode(),
            }
        )
    if not files:
        raise RuntimeError("agent instance configuration contains no files")
    return files


def load_source_bundle(
    source_home: Path,
    *,
    root: Path,
    registry: dict[str, Any],
) -> dict[str, object]:
    codex_config = source_home / ".codex/config.toml"
    claude_settings = source_home / ".claude/settings.json"
    missing = [str(path) for path in (codex_config, claude_settings) if not path.is_file()]
    if missing:
        raise RuntimeError("primary agent configuration is incomplete: " + ", ".join(missing))
    codex_text = codex_config.read_text(encoding="utf-8")
    try:
        claude_value = json.loads(claude_settings.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude user settings are invalid JSON: {exc}") from exc
    if not isinstance(claude_value, dict):
        raise RuntimeError("Claude user settings must contain a JSON object")
    validate_codex_settings(codex_text)
    validate_claude_settings(claude_value)
    agents_by_machine = {
        str(machine["id"]): global_agent_configuration.render_agents(
            root,
            registry,
            machine,
            source_home=source_home,
        )
        for machine in registry["machines"]
        if isinstance(machine, dict) and machine.get("id")
    }
    return {
        "source_home": str(source_home),
        "agents_by_machine": agents_by_machine,
        "codex_config": codex_text,
        "claude_settings": json.dumps(claude_value, indent=2, ensure_ascii=False) + "\n",
        "langfuse_config": load_langfuse_config(root),
        "instance_files": load_instance_files(root),
    }


def ensure_worker_mac_policy(text: str) -> str:
    lines = text.splitlines()
    output_lines: list[str] = []
    table = ""
    approval_seen = False
    sandbox_seen = False
    computer_table_seen = False
    computer_enabled_seen = False

    def finish_table() -> None:
        nonlocal computer_enabled_seen
        if table == "mcp_servers.computer-use" and not computer_enabled_seen:
            output_lines.append("enabled = true")
            computer_enabled_seen = True

    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            finish_table()
            if not table:
                if not approval_seen:
                    output_lines.append('approval_policy = "never"')
                if not sandbox_seen:
                    output_lines.append('sandbox_mode = "danger-full-access"')
            table = stripped[1:-1].strip()
            computer_enabled_seen = False
            if table == "mcp_servers.computer-use":
                computer_table_seen = True
            output_lines.append(raw_line)
            continue
        key, separator, _ = stripped.partition("=")
        key = key.strip()
        if separator and not table and key == "approval_policy":
            if not approval_seen:
                output_lines.append('approval_policy = "never"')
                approval_seen = True
            continue
        if separator and not table and key == "sandbox_mode":
            if not sandbox_seen:
                output_lines.append('sandbox_mode = "danger-full-access"')
                sandbox_seen = True
            continue
        if separator and table == "mcp_servers.computer-use" and key == "enabled":
            if not computer_enabled_seen:
                output_lines.append("enabled = true")
                computer_enabled_seen = True
            continue
        output_lines.append(raw_line)

    finish_table()
    if not table:
        if not approval_seen:
            output_lines.append('approval_policy = "never"')
        if not sandbox_seen:
            output_lines.append('sandbox_mode = "danger-full-access"')
    if not computer_table_seen:
        if output_lines and output_lines[-1] != "":
            output_lines.append("")
        output_lines.extend(["[mcp_servers.computer-use]", "enabled = true"])
    return "\n".join(output_lines).rstrip() + "\n"


def rendered_files(
    bundle: dict[str, object],
    machine: dict[str, Any],
    *,
    components: set[str] | None = None,
) -> list[dict[str, object]]:
    selected = components or {"config", "instructions"}
    unknown = selected - {"config", "instructions"}
    if unknown:
        raise RuntimeError(f"unknown agent configuration components: {', '.join(sorted(unknown))}")
    source_home = str(bundle["source_home"])
    target_home = str(machine["home"])
    codex_config = str(bundle["codex_config"]).replace(source_home, target_home)
    claude_settings = str(bundle["claude_settings"]).replace(source_home, target_home)
    if machine["role"] == "worker" and machine["platform"] == "macos":
        codex_config = ensure_worker_mac_policy(codex_config)
    json.loads(claude_settings)
    agents_by_machine = bundle.get("agents_by_machine")
    rendered_agents = agents_by_machine.get(str(machine["id"])) if isinstance(agents_by_machine, dict) else None
    if not isinstance(rendered_agents, str):
        raise RuntimeError(f"global agents were not rendered for {machine['id']}")
    files: list[dict[str, object]] = [
        {
            "path": ".codex/AGENTS.md",
            "component": "instructions",
            "kind": "file",
            "mode": 0o644,
            "content": base64.b64encode(rendered_agents.encode()).decode(),
        },
        {
            "path": ".codex/config.toml",
            "component": "config",
            "kind": "toml",
            "mode": 0o600,
            "content": base64.b64encode(codex_config.encode()).decode(),
            "preserve_tables": ["plugins", "marketplaces"],
        },
        {
            "path": ".claude/CLAUDE.md",
            "component": "instructions",
            "kind": "symlink",
            "target": "../.codex/AGENTS.md",
        },
        {
            "path": ".claude/settings.json",
            "component": "config",
            "kind": "file",
            "mode": 0o600,
            "content": base64.b64encode(claude_settings.encode()).decode(),
        },
    ]
    instance_files = bundle.get("instance_files")
    if not isinstance(instance_files, list) or not all(isinstance(item, dict) for item in instance_files):
        raise RuntimeError("agent instance configuration bundle is invalid")
    files.extend({**item, "component": "config"} for item in instance_files)
    return [
        {key: value for key, value in item.items() if key != "component"}
        for item in files
        if item["component"] in selected
    ]


def reconcile_source_alias(
    source_home: Path,
    bundle: dict[str, object],
    source_id: str,
    root: Path,
    *,
    apply: bool,
    verify: bool,
    backup_suffix: str,
    components: set[str],
) -> dict[str, object]:
    root_report = global_agent_configuration.ensure_agent_paths(root, dry_run=not apply)
    agents_by_machine = bundle.get("agents_by_machine")
    rendered_agents = agents_by_machine.get(source_id) if isinstance(agents_by_machine, dict) else None
    if not isinstance(rendered_agents, str):
        raise RuntimeError(f"global agents were not rendered for {source_id}")
    files: list[dict[str, object]] = []
    if "instructions" in components:
        files.extend(global_agent_configuration.home_agent_files(rendered_agents))
    if "config" in components:
        instance_files = bundle.get("instance_files")
        if not isinstance(instance_files, list) or not all(isinstance(item, dict) for item in instance_files):
            raise RuntimeError("agent instance configuration bundle is invalid")
        files.extend(instance_files)
    home_report = global_agent_configuration.reconcile_home(
        source_home,
        files,
        apply=apply,
        verify=verify,
        backup_suffix=backup_suffix,
    )
    return {
        "ok": True,
        "ready": bool(root_report["ready"]) and bool(home_report["ready"]),
        "applied": apply,
        "results": [*root_report["results"], *home_report["results"]],
        "root": root_report,
        "home": home_report,
    }


def target_environment_path(machine: dict[str, Any]) -> str:
    terminal_profile = machine.get("terminal_profile")
    configured = terminal_profile.get("remote_path") if isinstance(terminal_profile, dict) else None
    value = configured if isinstance(configured, str) and configured else DEFAULT_REMOTE_PATH
    if any(not part.startswith("/") or re.search(r"\s", part) for part in value.split(":")):
        raise RuntimeError(f"target {machine.get('id')} has an unsafe terminal_profile.remote_path")
    return value


def invoke_target(
    machine: dict[str, Any],
    bundle: dict[str, object],
    *,
    apply: bool,
    verify: bool,
    backup_suffix: str,
    components: set[str] | None = None,
) -> dict[str, object]:
    worker_source = (AGENT_SCRIPTS_DIRECTORY / "global_agent_configuration.py").read_text(encoding="utf-8")
    payload = json.dumps(
        {
            "home": machine["home"],
            "apply": apply,
            "verify": verify,
            "backup_suffix": backup_suffix,
            "files": rendered_files(bundle, machine, components=components),
        }
    )
    command = (
        f"env PATH={shlex.quote(target_environment_path(machine))} "
        f"python3 -c {shlex.quote(worker_source)}"
    )
    executed = run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", str(machine["ssh_alias"]), command],
        stdin=payload,
    )
    base = {"id": machine["id"], "display_name": machine.get("display_name")}
    if executed.returncode != 0 and not output(executed):
        return {**base, "ok": False, "error": f"SSH or remote worker failed: {error_text(executed)}"}
    try:
        response = json.loads(output(executed))
    except json.JSONDecodeError:
        return {**base, "ok": False, "error": f"invalid remote worker response: {error_text(executed)}"}
    return {**base, **response}


def sync_targets(
    machines: list[dict[str, Any]],
    bundle: dict[str, object],
    *,
    apply: bool,
    verify: bool,
    backup_suffix: str,
    components: set[str] | None = None,
) -> list[dict[str, object]]:
    return [
        invoke_target(
            machine,
            bundle,
            apply=apply,
            verify=verify,
            backup_suffix=backup_suffix,
            components=components,
        )
        for machine in machines
    ]


def print_report(report: dict[str, object]) -> None:
    source = report["source"]
    print(f"Source: {source['id']} {source['home']}")
    for result in source["alias"]["results"]:
        print(f"  {str(result['status']).upper():<10} {result['path']}: {result['detail']}")
    for target in report["targets"]:
        print(f"Target: {target.get('display_name') or target.get('id')} ({target.get('id')})")
        if not target.get("ok"):
            print(f"  ERROR {target.get('error', 'target failed')}")
            continue
        for result in target.get("results", []):
            print(f"  {str(result['status']).upper():<10} {result['path']}: {result['detail']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", action="append", default=[], help="machine ID or display name; repeatable")
    parser.add_argument("--machine-registry", type=Path, help="machines.json override")
    parser.add_argument("--source-home", type=Path, default=Path.home(), help="primary user's home directory")
    parser.add_argument("--provision-disabled", action="store_true", help="target one disabled machine during onboarding")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="install changed configuration")
    mode.add_argument("--verify", action="store_true", help="fail when configuration differs")
    parser.add_argument("--config", action="store_true", help="sync only Codex and Claude settings")
    parser.add_argument("--instructions", action="store_true", help="sync only AGENTS.md and the Claude alias")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = vault_root()
        source_id = current_machine_id(root)
        registry_path = args.machine_registry or (
            root / "_system/agents/_package/instance/fleet/machines.json"
        )
        registry = load_registry(registry_path.expanduser().resolve())
        require_primary(registry, source_id)
        source_home = args.source_home.expanduser().resolve()
        bundle = load_source_bundle(source_home, root=root, registry=registry)
        components = {
            name
            for name, selected in (("config", args.config), ("instructions", args.instructions))
            if selected
        } or {"config", "instructions"}
        targets = resolve_targets(
            registry,
            source_id,
            args.target,
            provision_disabled=bool(args.provision_disabled),
        )
        suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if args.apply:
            preview_alias = reconcile_source_alias(
                source_home,
                bundle,
                source_id,
                root,
                apply=False,
                verify=False,
                backup_suffix=suffix,
                components=components,
            )
            preview_targets = sync_targets(
                targets,
                bundle,
                apply=False,
                verify=False,
                backup_suffix=suffix,
                components=components,
            )
            if any(not target.get("ok") for target in preview_targets):
                report = {
                    "mode": "preflight-failed",
                    "source": {"id": source_id, "home": str(source_home), "alias": preview_alias},
                    "targets": preview_targets,
                }
                if args.json:
                    json.dump(report, sys.stdout, indent=2)
                    sys.stdout.write("\n")
                else:
                    print_report(report)
                return 1
        source_alias = reconcile_source_alias(
            source_home,
            bundle,
            source_id,
            root,
            apply=bool(args.apply),
            verify=bool(args.verify),
            backup_suffix=suffix,
            components=components,
        )
        target_reports = sync_targets(
            targets,
            bundle,
            apply=bool(args.apply),
            verify=bool(args.verify),
            backup_suffix=suffix,
            components=components,
        )
        report = {
            "mode": "apply" if args.apply else "verify" if args.verify else "preview",
            "source": {"id": source_id, "home": str(source_home), "alias": source_alias},
            "targets": target_reports,
        }
        if args.json:
            json.dump(report, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print_report(report)
        fatal = any(not target.get("ok") for target in target_reports)
        incomplete = not source_alias.get("ready", False) or any(
            not target.get("ready", False) for target in target_reports if target.get("ok")
        )
        if args.apply:
            incomplete = any(not target.get("applied", False) for target in target_reports if target.get("ok"))
        return 1 if fatal else 2 if incomplete else 0
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
