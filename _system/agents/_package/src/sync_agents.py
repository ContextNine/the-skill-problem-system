#!/usr/bin/env python3
"""Synchronize skills, settings, and instructions across the registered fleet."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Any


PACKAGE_DIRECTORY = Path(__file__).resolve().parents[1]
AGENTS_DIRECTORY = PACKAGE_DIRECTORY.parent
SOURCE_FLEET_SCRIPTS = AGENTS_DIRECTORY / "skills/auto/_infrastructure/infra-sync-code-workspaces/scripts"
FLEET_SCRIPTS = (
    SOURCE_FLEET_SCRIPTS
    if (SOURCE_FLEET_SCRIPTS / "sync_code_workspaces.py").is_file()
    else PACKAGE_DIRECTORY / "src"
)
for directory in (PACKAGE_DIRECTORY / "src", FLEET_SCRIPTS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import skill_snapshots
import sync_agent_configuration as agent_configuration
import sync_skills
import dependency_worker
import workspace_dependency_worker


class AgentsSyncError(RuntimeError):
    pass


def load_json_yaml(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AgentsSyncError(f"{label} is missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentsSyncError(f"{label} is invalid JSON-compatible YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise AgentsSyncError(f"{label} must contain an object")
    return value


def validate_dependency_lifecycle_routes(root: Path, manifest: dict[str, Any]) -> None:
    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, list):
        raise AgentsSyncError("agent dependency registry needs a dependencies list")
    base = root / "_system/agents/_package/docs"
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(dependency.get("id"), str):
            raise AgentsSyncError("every agent dependency needs an id")
        raw = dependency.get("lifecycle_doc")
        candidate = PurePosixPath(str(raw or ""))
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise AgentsSyncError(f"dependency {dependency['id']} has an unsafe lifecycle route")
        if not base.joinpath(*candidate.parts).is_file():
            raise AgentsSyncError(f"dependency {dependency['id']} lifecycle route is missing: {raw}")


def validate_machine_secrets(root: Path) -> None:
    registry = load_json_yaml(
        root / "_system/agents/_package/instance/fleet/machine-secrets.json", "machine secret registry"
    )
    credentials = registry.get("credentials")
    if registry.get("schema_version") != 2 or not isinstance(credentials, list):
        raise AgentsSyncError("machine secret registry needs schema_version 2 and credentials")
    ids: set[str] = set()
    forbidden = {"value", "secret", "token", "password", "private_key"}
    for credential in credentials:
        if not isinstance(credential, dict) or not isinstance(credential.get("id"), str):
            raise AgentsSyncError("every machine credential needs an id")
        credential_id = credential["id"]
        if credential_id in ids:
            raise AgentsSyncError(f"duplicate machine credential id: {credential_id}")
        ids.add(credential_id)
        if forbidden & set(credential):
            raise AgentsSyncError(f"machine credential {credential_id} contains a forbidden value field")
        if credential.get("class") not in registry.get("classes", {}):
            raise AgentsSyncError(f"machine credential {credential_id} has an unknown lifecycle class")
        if credential.get("scope") not in {"vault", "agents", "both"}:
            raise AgentsSyncError(f"machine credential {credential_id} has an invalid scope")
        if not isinstance(credential.get("documentation"), dict):
            raise AgentsSyncError(f"machine credential {credential_id} needs documentation")


def validate_workspace_dependencies(
    manifest: dict[str, Any],
    workspaces: dict[str, Any],
    direct_manifest: dict[str, Any],
) -> None:
    dependencies = manifest.get("workspace_dependencies")
    entries = workspaces.get("entries", {})
    direct_ids = {
        str(dependency.get("id"))
        for dependency in direct_manifest.get("dependencies", [])
        if isinstance(dependency, dict)
        and isinstance(dependency.get("id"), str)
        and dependency.get("kind") == "package"
        and isinstance(dependency.get("contract"), dict)
        and dependency["contract"].get("install_policy") == "required"
        and dependency.get("eligibility") == "enabled-agent-machines"
    }
    if manifest.get("schema_version") != 1 or not isinstance(dependencies, list) or not isinstance(entries, dict):
        raise AgentsSyncError("workspace dependency selections need schema_version 1, workspace_dependencies, and workspace entries")
    seen: set[str] = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(dependency.get("id"), str):
            raise AgentsSyncError("every workspace dependency needs a string id")
        dependency_id = dependency["id"]
        if dependency_id in seen:
            raise AgentsSyncError(f"duplicate workspace dependency id: {dependency_id}")
        seen.add(dependency_id)
        if dependency.get("workspace") not in entries:
            raise AgentsSyncError(f"{dependency_id} references unknown workspace {dependency.get('workspace')}")
        installer = PurePosixPath(str(dependency.get("installer") or ""))
        if installer.is_absolute() or not installer.parts or ".." in installer.parts:
            raise AgentsSyncError(f"{dependency_id} has an unsafe installer path")
        platforms = dependency.get("platforms")
        if not isinstance(platforms, list) or not platforms or set(platforms) - {"macos", "linux"}:
            raise AgentsSyncError(f"{dependency_id} has unsupported platforms")
        requirements = dependency.get("requires", [])
        platform_requirements = dependency.get("platform_requires", {})
        if not isinstance(requirements, list) or not isinstance(platform_requirements, dict):
            raise AgentsSyncError(f"{dependency_id} has invalid direct dependency requirements")
        referenced = set(requirements)
        for platform, values in platform_requirements.items():
            if platform not in {"macos", "linux"} or not isinstance(values, list):
                raise AgentsSyncError(f"{dependency_id} has invalid platform requirements")
            referenced.update(values)
        unknown = referenced - direct_ids
        if unknown:
            raise AgentsSyncError(f"{dependency_id} references unknown direct dependencies: {sorted(unknown)}")
        arguments = dependency.get("arguments")
        if not isinstance(arguments, dict) or set(arguments) != {"apply", "dry-run", "verify"}:
            raise AgentsSyncError(f"{dependency_id} needs apply, dry-run, and verify arguments")
        for mode, values in arguments.items():
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise AgentsSyncError(f"{dependency_id} has invalid {mode} arguments")
            unknown_placeholders = {
                match
                for value in values
                for match in re.findall(r"\{[^{}]+\}", value)
                if match != "{display_name}"
            }
            if unknown_placeholders:
                raise AgentsSyncError(
                    f"{dependency_id} has unsupported argument placeholders: {sorted(unknown_placeholders)}"
                )
        commands = dependency.get("commands")
        if (
            not isinstance(commands, list)
            or not commands
            or not all(isinstance(command, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", command) for command in commands)
        ):
            raise AgentsSyncError(f"{dependency_id} needs safe expected command names")
        if dependency.get("source_commit_alignment") is not True:
            raise AgentsSyncError(f"{dependency_id} must require source commit alignment")


def invoke_portable_worker(
    machine: dict[str, Any],
    module: Any,
    payload: dict[str, Any],
    *,
    local: bool,
) -> dict[str, Any]:
    source = Path(str(module.__file__)).read_text(encoding="utf-8")
    encoded = json.dumps(payload)
    if local:
        executed = subprocess.run(
            [sys.executable, str(module.__file__)],
            input=encoded,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    else:
        command = (
            f"env PATH={shlex.quote(agent_configuration.target_environment_path(machine))} "
            f"python3 -c {shlex.quote(source)}"
        )
        executed = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                str(machine["ssh_alias"]),
                command,
            ],
            input=encoded,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    try:
        report = json.loads(executed.stdout.strip())
    except json.JSONDecodeError:
        detail = (executed.stderr or executed.stdout or "portable worker returned no report").strip().splitlines()[-1]
        return {"id": machine["id"], "ok": False, "error": detail[:1000]}
    return {"id": machine["id"], **report}


def invoke_dependency_targets(
    machines: list[dict[str, Any]],
    manifest: dict[str, Any],
    reference_files: dict[str, dict[str, str]],
    *,
    source_id: str,
    mode: str,
) -> list[dict[str, Any]]:
    return [
        invoke_portable_worker(
            machine,
            dependency_worker,
            {
                "manifest": manifest,
                "reference_files": reference_files,
                "machine_id": machine["id"],
                "machine": {
                    "id": machine["id"],
                    "enabled": machine.get("enabled", False),
                    "vault": machine.get("vault", {}),
                },
                "mode": mode,
            },
            local=str(machine["id"]) == source_id,
        )
        for machine in machines
    ]


def build_agent_reference_files(root: Path) -> dict[str, dict[str, str]]:
    agents = root / "_system/agents"
    files = [
        agents / "_package/defaults/dependencies.json",
        agents / "_package/instance/dependencies/selections.json",
        agents / "_package/docs/dependencies.md",
        agents / "_package/instance/fleet/machine-secrets.json",
        agents / "_package/instance/skills/sources.json",
        *sorted((agents / "_package/docs/dependency-references").glob("*.md")),
        *sorted((agents / "_package/docs/secrets").rglob("*.md")),
    ]
    result: dict[str, dict[str, str]] = {}
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise AgentsSyncError(f"agent reference source must be a real file: {path}")
        content = path.read_text(encoding="utf-8")
        relative = path.relative_to(agents).as_posix()
        result[relative] = {
            "content": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
    return result


def invoke_workspace_dependency_targets(
    machines: list[dict[str, Any]],
    manifest: dict[str, Any],
    workspaces: dict[str, Any],
    *,
    source_id: str,
    mode: str,
) -> list[dict[str, Any]]:
    return [
        invoke_portable_worker(
            machine,
            workspace_dependency_worker,
            {"manifest": manifest, "workspaces": workspaces, "machine": machine, "mode": mode},
            local=str(machine["id"]) == source_id,
        )
        for machine in machines
    ]


def invoke_workspace_sync(
    root: Path,
    target_ids: list[str],
    *,
    apply: bool,
) -> dict[str, Any]:
    if not target_ids:
        return {"ok": True, "targets": []}
    script = FLEET_SCRIPTS / "sync_code_workspaces.py"
    command = [
        sys.executable,
        str(script),
        "reconcile",
        "--catalog",
        str(root / "_system/agents/_package/instance/fleet/workspaces.json"),
        "--machine-registry",
        str(root / "_system/agents/_package/instance/fleet/machines.json"),
        "--skip-personal-configuration",
        "--json",
    ]
    for target_id in target_ids:
        command.extend(["--target", target_id])
    if apply:
        command.append("--apply")
    executed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        report = json.loads(executed.stdout)
    except json.JSONDecodeError as exc:
        detail = (executed.stderr or executed.stdout or "workspace sync returned no report").strip().splitlines()[-1]
        raise AgentsSyncError(f"workspace sync failed: {detail[:1000]}") from exc
    report["ok"] = executed.returncode == 0
    return report


def write_aggregate_lock(root: Path, reports: dict[str, dict[str, Any]]) -> None:
    path = root / "_system/agents/_package/generated/state/dependencies.lock.json"
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentsSyncError(f"aggregate dependency lock is invalid: {exc}") from exc
    if not isinstance(existing, dict) or not isinstance(existing.get("machines", {}), dict):
        raise AgentsSyncError("aggregate dependency lock must contain a machines object")
    machines = dict(existing.get("machines", {}))
    for machine_id, report in reports.items():
        previous = machines.get(machine_id, {})
        if not isinstance(previous, dict):
            raise AgentsSyncError(f"aggregate dependency lock entry is invalid: {machine_id}")
        merged = dict(previous)
        merged.update({key: value for key, value in report.items() if value is not None})
        machines[machine_id] = merged
    value = {
        "schema_version": 1,
        "verified_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "machines": machines,
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def selected_parts(args: argparse.Namespace) -> set[str]:
    selected = {
        name
        for name, enabled in (
            ("dependencies", args.dependencies),
            ("workspaces", args.workspaces),
            ("workspace-deps", args.workspace_deps),
            ("skills", args.skills),
            ("config", args.config),
            ("instructions", args.instructions),
        )
        if enabled
    }
    return selected or {"dependencies", "workspaces", "workspace-deps", "skills", "config", "instructions"}


def build_skill_snapshot_bundle(
    root: Path,
    *,
    require_repo_sources: bool,
) -> skill_snapshots.SnapshotBundle:
    working_plan, skills = sync_skills.discover_skills(
        root,
        require_repo_sources=require_repo_sources,
    )
    replacements = {
        action.target: action
        for action in working_plan.actions
        if action.kind == "replace"
    }
    with tempfile.TemporaryDirectory(prefix="vault-agent-skill-preview-") as temporary:
        preview_root = Path(temporary)
        sources: dict[str, Path] = {}
        for skill in skills:
            action = replacements.get(skill.path)
            if action is None:
                source = skill.path
            else:
                preview_target = preview_root / skill.name
                sync_skills.working_repo_skills.write_projection(
                    preview_target,
                    action.files,
                )
                source = preview_target
            sources[skill.name] = snapshot_skill_source(skill, source, preview_root)
        return skill_snapshots.build_bundle(sources)


def snapshot_skill_source(
    skill: sync_skills.Skill,
    source: Path,
    preview_root: Path,
) -> Path:
    """Overlay configured GitHub invocation policy without editing publisher files."""
    if skill.source != "gh" or skill.mode is None:
        return source
    preview_target = preview_root / skill.name
    shutil.copytree(source, preview_target)
    metadata = preview_target / "agents/openai.yaml"
    rendered = sync_skills.policy_text(metadata, skill.mode == "auto")
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(rendered, encoding="utf-8")
    return preview_target


def invoke_skill_target(
    machine: dict[str, Any],
    bundle: skill_snapshots.SnapshotBundle,
    *,
    apply: bool,
    verify: bool,
    backup_suffix: str,
) -> dict[str, object]:
    worker_source = Path(skill_snapshots.__file__).read_text(encoding="utf-8")
    payload = json.dumps(
        skill_snapshots.payload_for(
            Path(str(machine["home"])),
            bundle,
            apply=apply,
            verify=verify,
            backup_suffix=backup_suffix,
            legacy_catalog=None,
        )
    )
    command = (
        f"env PATH={shlex.quote(agent_configuration.target_environment_path(machine))} "
        f"python3 -c {shlex.quote(worker_source)}"
    )
    executed = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            str(machine["ssh_alias"]),
            command,
        ],
        input=payload,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    base = {"id": machine["id"], "display_name": machine.get("display_name")}
    output = executed.stdout.strip()
    if executed.returncode != 0 and not output:
        error = (executed.stderr or "remote skill snapshot worker failed").strip().splitlines()[-1]
        return {**base, "ok": False, "error": error[:1000]}
    try:
        report = json.loads(output)
    except json.JSONDecodeError:
        error = (executed.stderr or output or "invalid remote skill snapshot response").strip().splitlines()[-1]
        return {**base, "ok": False, "error": error[:1000]}
    return {**base, **report}


def invoke_skill_targets(
    machines: list[dict[str, Any]],
    bundle: skill_snapshots.SnapshotBundle,
    *,
    apply: bool,
    verify: bool,
    backup_suffix: str,
) -> list[dict[str, object]]:
    return [
        invoke_skill_target(
            machine,
            bundle,
            apply=apply,
            verify=verify,
            backup_suffix=backup_suffix,
        )
        for machine in machines
    ]


def print_skill_report(label: str, report: dict[str, object]) -> None:
    if not report.get("ok"):
        print(f"  {label} ERROR: {report.get('error', 'skill snapshot failed')}")
        return
    changes = report.get("changes")
    count = len(changes) if isinstance(changes, list) else 0
    status = "match" if report.get("ready") and not count else f"{count} change(s)"
    print(f"  {label}: {report.get('skill_count', 0)} skills, {status}")


def print_config_report(label: str, report: dict[str, object]) -> None:
    if not report.get("ok"):
        print(f"  {label} ERROR: {report.get('error', 'configuration sync failed')}")
        return
    results = report.get("results")
    changed = [item for item in results if item.get("status") != "match"] if isinstance(results, list) else []
    print(f"  {label}: {'match' if not changed else f'{len(changed)} change(s)'}")


def print_dependency_report(label: str, report: dict[str, Any], result_key: str) -> None:
    if not report.get("ok"):
        print(f"  {label} ERROR: {report.get('error', 'dependency worker failed')}")
        return
    results = report.get(result_key)
    pending = [item for item in results if not item.get("ready")] if isinstance(results, list) else []
    reference = report.get("reference_package")
    reference_changes = reference.get("changes", []) if isinstance(reference, dict) else []
    reference_collisions = reference.get("collisions", []) if isinstance(reference, dict) else []
    summary = (
        "ready"
        if not pending and not reference_changes and not reference_collisions
        else f"{len(pending)} package pending, {len(reference_changes)} reference change(s), {len(reference_collisions)} collision(s)"
    )
    print(f"  {label}: {summary}")
    for item in pending:
        print(f"    - {item.get('id')}: {item.get('detail', 'not ready')}")
    for path in reference_collisions:
        print(f"    - unmanaged reference collision: {path}")


def print_workspace_target(report: dict[str, Any]) -> None:
    if not report.get("ok"):
        print(f"  workspaces ERROR: {report.get('error', 'workspace worker failed')}")
        return
    results = report.get("results")
    if not isinstance(results, list):
        print("  workspaces ERROR: workspace worker returned no results")
        return
    blocked = [item for item in results if item.get("status") == "blocked"]
    planned = [item for item in results if str(item.get("status", "")).startswith("planned-")]
    print(
        f"  workspaces: {f'{len(blocked)} blocked' if blocked else 'ready'}"
        f"{f', {len(planned)} planned' if planned else ''}"
    )
    for item in blocked:
        print(f"    - {item.get('path')}: {item.get('detail', 'blocked')}")


def targets_ready(reports: list[dict[str, object]], *, require_match: bool) -> bool:
    return all(
        report.get("ok") and (not require_match or report.get("ready"))
        for report in reports
    )


def targets_applied(reports: list[dict[str, object]]) -> bool:
    return all(report.get("ok") and report.get("ready") and report.get("applied") for report in reports)


def source_alias(
    source_home: Path,
    bundle: dict[str, object],
    source_id: str,
    root: Path,
    *,
    apply: bool,
    verify: bool,
    suffix: str,
    components: set[str],
) -> dict[str, object]:
    return agent_configuration.reconcile_source_alias(
        source_home,
        bundle,
        source_id,
        root,
        apply=apply,
        verify=verify,
        backup_suffix=suffix,
        components=components,
    )


def sync(args: argparse.Namespace) -> int:
    root = (args.root or agent_configuration.vault_root()).expanduser().resolve()
    home = (args.home or Path.home()).expanduser().resolve()
    validate_machine_secrets(root)
    source_id = agent_configuration.current_machine_id(root)
    registry_path = args.machine_registry or (
        root / "_system/agents/_package/instance/fleet/machines.json"
    )
    registry = agent_configuration.load_registry(registry_path.expanduser().resolve())
    parts = selected_parts(args)
    primary_id = str(registry.get("primary_machine_id") or "")
    if source_id != primary_id:
        if not (args.local_only and parts == {"skills"}):
            agent_configuration.require_primary(registry, source_id)
    apply = not args.dry_run and not args.verify
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    targets = (
        []
        if args.local_only
        else agent_configuration.resolve_targets(
            registry,
            source_id,
            args.target,
            provision_disabled=False,
        )
    )
    source_matches = [machine for machine in registry["machines"] if machine.get("id") == source_id]
    if len(source_matches) != 1:
        raise AgentsSyncError(f"source machine {source_id!r} did not resolve exactly once")
    selected_machines = [source_matches[0], *targets]

    dependency_preview: list[dict[str, Any]] = []
    dependency_manifest: dict[str, Any] | None = None
    reference_files: dict[str, dict[str, str]] = {}
    if "dependencies" in parts:
        dependency_manifest = load_json_yaml(
            root / "_system/agents/_package/defaults/dependencies.json", "agent dependency registry"
        )
        validate_dependency_lifecycle_routes(root, dependency_manifest)
        reference_files = build_agent_reference_files(root)
        dependency_preview = invoke_dependency_targets(
            selected_machines,
            dependency_manifest,
            reference_files,
            source_id=source_id,
            mode="verify" if args.verify else "dry-run",
        )

    workspace_preview: dict[str, Any] | None = None
    if "workspaces" in parts:
        workspace_preview = invoke_workspace_sync(
            root,
            [str(machine["id"]) for machine in targets],
            apply=False,
        )

    workspace_dependency_preview: list[dict[str, Any]] = []
    workspace_dependency_manifest: dict[str, Any] | None = None
    workspaces_manifest: dict[str, Any] | None = None
    if "workspace-deps" in parts:
        workspace_dependency_manifest = load_json_yaml(
            root / "_system/agents/_package/instance/dependencies/selections.json", "workspace dependency manifest"
        )
        workspaces_manifest = load_json_yaml(
            root / "_system/agents/_package/instance/fleet/workspaces.json", "workspace manifest"
        )
        direct_for_validation = dependency_manifest or load_json_yaml(
            root / "_system/agents/_package/defaults/dependencies.json", "agent dependency registry"
        )
        validate_dependency_lifecycle_routes(root, direct_for_validation)
        validate_workspace_dependencies(
            workspace_dependency_manifest,
            workspaces_manifest,
            direct_for_validation,
        )
        workspace_dependency_preview = invoke_workspace_dependency_targets(
            selected_machines,
            workspace_dependency_manifest,
            workspaces_manifest,
            source_id=source_id,
            mode="verify" if args.verify else "dry-run",
        )

    skill_bundle: skill_snapshots.SnapshotBundle | None = None
    local_skill_preview: dict[str, object] | None = None
    remote_skill_preview: list[dict[str, object]] = []
    if "skills" in parts:
        sync_skills.sync(
            root,
            home,
            False,
            require_repo_sources=args.require_repo_sources,
            manage_home_discovery=False,
            manage_agent_configuration=False,
        )
        skill_bundle = build_skill_snapshot_bundle(
            root,
            require_repo_sources=args.require_repo_sources,
        )
        local_skill_preview = skill_snapshots.reconcile_local(
            home,
            skill_bundle,
            apply=False,
            verify=args.verify,
            backup_suffix=suffix,
            legacy_catalog=root / "_system/agents/skills",
        )
        remote_skill_preview = invoke_skill_targets(
            targets,
            skill_bundle,
            apply=False,
            verify=args.verify,
            backup_suffix=suffix,
        )

    agent_bundle: dict[str, object] | None = None
    local_config_preview: dict[str, object] | None = None
    remote_config_preview: list[dict[str, object]] = []
    config_parts = parts & {"config", "instructions"}
    if config_parts:
        agent_bundle = agent_configuration.load_source_bundle(home, root=root, registry=registry)
        local_config_preview = source_alias(
            home,
            agent_bundle,
            source_id,
            root,
            apply=False,
            verify=args.verify,
            suffix=suffix,
            components=config_parts,
        )
        remote_config_preview = agent_configuration.sync_targets(
            targets,
            agent_bundle,
            apply=False,
            verify=args.verify,
            backup_suffix=suffix,
            components=config_parts,
        )

    print(f"Mode: {'apply' if apply else 'verify' if args.verify else 'dry-run'}")
    print(f"Parts: {', '.join(sorted(parts))}")
    print("Source: local")
    source_dependency = next((item for item in dependency_preview if item.get("id") == source_id), None)
    if source_dependency is not None:
        print_dependency_report("dependencies", source_dependency, "packages")
    if workspace_preview is not None:
        print(f"  workspaces: {'ready' if workspace_preview.get('ok') else 'blocked'}")
        for warning in workspace_preview.get("warnings", []):
            print(f"    - warning: {warning}")
    source_workspace_dependency = next(
        (item for item in workspace_dependency_preview if item.get("id") == source_id), None
    )
    if source_workspace_dependency is not None:
        print_dependency_report("workspace dependencies", source_workspace_dependency, "dependencies")
    if local_skill_preview is not None:
        print_skill_report("skills", local_skill_preview)
    if local_config_preview is not None:
        print_config_report("agent configuration", local_config_preview)
    for machine in targets:
        machine_id = str(machine["id"])
        print(f"Target: {machine.get('display_name')} ({machine_id})")
        dependency_report = next((item for item in dependency_preview if item.get("id") == machine_id), None)
        if dependency_report is not None:
            print_dependency_report("dependencies", dependency_report, "packages")
        if workspace_preview is not None:
            workspace_report = next(
                (item for item in workspace_preview.get("targets", []) if item.get("id") == machine_id),
                None,
            )
            if workspace_report is not None:
                print_workspace_target(workspace_report)
        workspace_dependency_report = next(
            (item for item in workspace_dependency_preview if item.get("id") == machine_id), None
        )
        if workspace_dependency_report is not None:
            print_dependency_report("workspace dependencies", workspace_dependency_report, "dependencies")
        skill_report = next((item for item in remote_skill_preview if item.get("id") == machine_id), None)
        if skill_report is not None:
            print_skill_report("skills", skill_report)
        config_report = next((item for item in remote_config_preview if item.get("id") == machine_id), None)
        if config_report is not None:
            print_config_report("configuration", config_report)

    preflight_ok = (
        all(
            report.get("ok")
            and (report.get("ready") if args.verify else report.get("can_apply"))
            for report in dependency_preview
        )
        and (workspace_preview is None or workspace_preview.get("ok"))
        and all(
            report.get("ok")
            and (report.get("ready") if args.verify else report.get("can_apply"))
            for report in workspace_dependency_preview
        )
        and
        (local_skill_preview is None or local_skill_preview.get("ok"))
        and targets_ready(remote_skill_preview, require_match=args.verify)
        and (local_config_preview is None or local_config_preview.get("ok"))
        and targets_ready(remote_config_preview, require_match=args.verify)
    )
    if args.verify:
        local_ready = (
            (local_skill_preview is None or local_skill_preview.get("ready"))
            and (local_config_preview is None or local_config_preview.get("ready"))
        )
        return 0 if preflight_ok and local_ready else 2
    if not preflight_ok:
        print("Preflight failed; no agent sync changes were applied.", file=sys.stderr)
        return 1
    if not apply:
        return 0

    dependency_apply: list[dict[str, Any]] = []
    if dependency_manifest is not None:
        dependency_apply = invoke_dependency_targets(
            selected_machines,
            dependency_manifest,
            reference_files,
            source_id=source_id,
            mode="apply",
        )
        if not all(report.get("ok") and report.get("ready") for report in dependency_apply):
            print("Dependency apply failures:", file=sys.stderr)
            for report in dependency_apply:
                if not report.get("ok") or not report.get("ready"):
                    print_dependency_report(str(report.get("id") or "unknown"), report, "packages")
            raise AgentsSyncError("direct dependency apply was incomplete")

    if workspace_preview is not None:
        workspace_apply = invoke_workspace_sync(
            root,
            [str(machine["id"]) for machine in targets],
            apply=True,
        )
        if not workspace_apply.get("ok"):
            raise AgentsSyncError("workspace apply was incomplete")

    workspace_dependency_apply: list[dict[str, Any]] = []
    if workspace_dependency_manifest is not None and workspaces_manifest is not None:
        workspace_dependency_apply = invoke_workspace_dependency_targets(
            selected_machines,
            workspace_dependency_manifest,
            workspaces_manifest,
            source_id=source_id,
            mode="apply",
        )
        if not all(report.get("ok") and report.get("ready") for report in workspace_dependency_apply):
            print("Workspace dependency apply failures:", file=sys.stderr)
            for report in workspace_dependency_apply:
                if not report.get("ok") or not report.get("ready"):
                    print_dependency_report(str(report.get("id") or "unknown"), report, "dependencies")
            raise AgentsSyncError("workspace dependency apply was incomplete")
    if dependency_apply or workspace_dependency_apply:
        dependency_by_id = {str(report["id"]): report for report in dependency_apply}
        workspace_by_id = {str(report["id"]): report for report in workspace_dependency_apply}
        write_aggregate_lock(
            root,
            {
                str(machine["id"]): {
                    "direct": dependency_by_id.get(str(machine["id"])),
                    "workspace": workspace_by_id.get(str(machine["id"])),
                }
                for machine in selected_machines
            },
        )

    if "skills" in parts:
        sync_skills.sync(
            root,
            home,
            True,
            require_repo_sources=args.require_repo_sources,
            manage_home_discovery=False,
            manage_agent_configuration=False,
        )
        skill_bundle = build_skill_snapshot_bundle(
            root,
            require_repo_sources=args.require_repo_sources,
        )
        local_skill_apply = skill_snapshots.reconcile_local(
            home,
            skill_bundle,
            apply=True,
            verify=False,
            backup_suffix=suffix,
            legacy_catalog=root / "_system/agents/skills",
        )
        remote_skill_apply = invoke_skill_targets(
            targets,
            skill_bundle,
            apply=True,
            verify=False,
            backup_suffix=suffix,
        )
        if (
            not local_skill_apply.get("ok")
            or not local_skill_apply.get("ready")
            or not local_skill_apply.get("applied")
            or not targets_applied(remote_skill_apply)
        ):
            raise AgentsSyncError("skill snapshot apply was incomplete")

    if agent_bundle is not None:
        applied_alias = source_alias(
            home,
            agent_bundle,
            source_id,
            root,
            apply=True,
            verify=False,
            suffix=suffix,
            components=config_parts,
        )
        if not applied_alias.get("ok") or not applied_alias.get("ready") or not applied_alias.get("applied"):
            raise AgentsSyncError("local agent configuration apply failed")
        applied_targets = agent_configuration.sync_targets(
            targets,
            agent_bundle,
            apply=True,
            verify=False,
            backup_suffix=suffix,
            components=config_parts,
        )
        if not targets_applied(applied_targets):
            raise AgentsSyncError("remote configuration apply was incomplete")

    verify_args = argparse.Namespace(**vars(args))
    verify_args.verify = True
    verify_args.dry_run = False
    print("Verification:")
    return sync(verify_args)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync skills, settings, and rendered instructions locally and across the enabled fleet."
    )
    parser.add_argument("command", choices=["sync"])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="preview without changing files")
    mode.add_argument("--verify", action="store_true", help="verify selected parts without changing files")
    parser.add_argument("--dependencies", action="store_true", help="sync only approved direct agent dependencies")
    parser.add_argument("--workspaces", action="store_true", help="sync only managed Code workspaces")
    parser.add_argument("--workspace-deps", dest="workspace_deps", action="store_true", help="sync only approved workspace-built commands")
    parser.add_argument("--skills", action="store_true", help="sync only global skill snapshots")
    parser.add_argument("--config", action="store_true", help="sync only Codex and Claude settings")
    parser.add_argument(
        "--instructions",
        "--agents-md",
        dest="instructions",
        action="store_true",
        help="sync only rendered AGENTS.md and the Claude alias",
    )
    parser.add_argument("--target", action="append", default=[], help="target machine ID; repeatable")
    parser.add_argument("--local-only", action="store_true", help="sync only the current primary machine")
    parser.add_argument("--require-repo-sources", action="store_true")
    parser.add_argument("--machine-registry", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--home", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return sync(parse_args(argv))
    except (
        AgentsSyncError,
        RuntimeError,
        skill_snapshots.SnapshotError,
        sync_skills.SyncError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Agent sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
