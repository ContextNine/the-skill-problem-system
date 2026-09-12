#!/usr/bin/env python3
"""Resolve and apply approved fleet dependency updates, then sync and verify."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from typing import Any


PACKAGE_DIRECTORY = Path(__file__).resolve().parents[1]
AGENTS_DIRECTORY = PACKAGE_DIRECTORY.parent
FLEET_SCRIPTS = AGENTS_DIRECTORY / "skills/_infrastructure/infra-i-sync-code-workspaces/scripts"
COMMANDS_DIRECTORY = AGENTS_DIRECTORY.parent / "commands"
for directory in (PACKAGE_DIRECTORY / "src", FLEET_SCRIPTS, COMMANDS_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import dependency_worker
import fleet_update_worker
import skill_source_config
import skill_source_update
import sync_agent_configuration as agent_configuration


class FleetUpdateError(RuntimeError):
    pass


SELECTOR_NAMES = {
    "dependencies",
    "coding-tools",
    "skills",
    "workspace-deps",
    "vault-dependencies",
}


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FleetUpdateError(f"{label} is missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise FleetUpdateError(f"{label} is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise FleetUpdateError(f"{label} must contain an object")
    return value


def selected_parts(args: argparse.Namespace) -> set[str]:
    if getattr(args, "dependency", []):
        return {"dependencies"}
    selected = {
        name
        for name, enabled in (
            ("dependencies", args.dependencies),
            ("coding-tools", args.coding_tools),
            ("skills", args.skills),
            ("workspace-deps", args.workspace_deps),
            ("vault-dependencies", args.vault_dependencies),
        )
        if enabled
    }
    return selected or set(SELECTOR_NAMES)


def dependency_ids(
    manifest: dict[str, Any],
    parts: set[str],
    requested: list[str],
) -> list[str]:
    dependency_worker.validate_manifest(manifest)
    dependencies = manifest.get("dependencies", [])
    known = {str(dependency["id"]) for dependency in dependencies}
    unknown = sorted(set(requested) - known)
    if unknown:
        raise FleetUpdateError(f"unknown dependencies: {', '.join(unknown)}")
    if requested:
        return list(dict.fromkeys(requested))
    selected: list[str] = []
    for dependency in dependencies:
        kind = dependency.get("kind")
        if kind == "coding-tool" and "coding-tools" in parts:
            selected.append(str(dependency["id"]))
        elif kind == "workspace-command":
            continue
        elif kind != "coding-tool" and "dependencies" in parts:
            selected.append(str(dependency["id"]))
    return selected


def exact_component_manifest(
    manifest: dict[str, Any],
    dependency_id: str,
    version: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise FleetUpdateError(f"invalid exact semantic version: {version!r}")
    candidate = copy.deepcopy(manifest)
    dependencies = candidate.get("dependencies", [])
    dependency = next(
        (item for item in dependencies if isinstance(item, dict) and item.get("id") == dependency_id),
        None,
    )
    if not isinstance(dependency, dict):
        raise FleetUpdateError(f"unknown dependency: {dependency_id}")
    contract = dependency.get("contract")
    if not isinstance(contract, dict) or contract.get("adapter") != "package":
        raise FleetUpdateError(f"{dependency_id} is not an exact component dependency")
    recipes = contract.get("recipes")
    verify = contract.get("verify")
    if not isinstance(recipes, dict) or not isinstance(verify, dict):
        raise FleetUpdateError(f"{dependency_id} has no exact component recipe")
    for platform, recipe in recipes.items():
        if not isinstance(recipe, dict) or recipe.get("manager") != "ctx9-component":
            raise FleetUpdateError(f"{dependency_id} has no promotable {platform} component recipe")
        current_url = recipe.get("private_catalog_url")
        if not isinstance(current_url, str):
            raise FleetUpdateError(f"{dependency_id} is not an immutable private component")
        next_url, replacements = re.subn(
            r"/[0-9]+\.[0-9]+\.[0-9]+/components\.json$",
            f"/{version}/components.json",
            current_url,
        )
        if replacements != 1:
            raise FleetUpdateError(f"{dependency_id} has an unsupported private catalog URL")
        recipe["private_catalog_url"] = next_url
    verify["exact"] = version
    dependency_worker.validate_manifest(candidate)
    return candidate


def write_manifest(path: Path, manifest: dict[str, Any]) -> bool:
    content = json.dumps(manifest, indent=2) + "\n"
    if path.read_text(encoding="utf-8") == content:
        return False
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def exact_t3_version(args: argparse.Namespace, parts: set[str]) -> str | None:
    if "coding-tools" not in parts:
        return None
    if args.verify and not args.t3_version:
        return None
    value = args.t3_version
    if value is None:
        process = subprocess.run(
            ["npm", "view", "t3", "dist-tags.nightly"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if process.returncode != 0:
            detail = (process.stderr or process.stdout).strip().splitlines()
            raise FleetUpdateError(
                "cannot resolve the approved T3 nightly: "
                + (detail[-1][:500] if detail else "npm view failed")
            )
        value = process.stdout.strip()
    if not value or "-nightly." not in value or re.search(r"\s", value):
        raise FleetUpdateError(f"invalid T3 nightly version: {value!r}")
    return value


def target_environment_path(machine: dict[str, Any]) -> str:
    return agent_configuration.target_environment_path(machine)


def invoke_worker(
    machine: dict[str, Any],
    manifest: dict[str, Any],
    ids: list[str],
    *,
    mode: str,
    resolved: dict[str, str],
    source_id: str,
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "machine": machine,
            "manifest": manifest,
            "dependency_ids": ids,
            "mode": mode,
            "resolved": resolved,
        }
    )
    worker_source = Path(fleet_update_worker.__file__).read_text(encoding="utf-8")
    if machine["id"] == source_id:
        process = subprocess.run(
            [sys.executable, "-c", worker_source],
            input=payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    else:
        command = (
            f"env PATH={shlex.quote(target_environment_path(machine))} "
            f"python3 -c {shlex.quote(worker_source)}"
        )
        process = subprocess.run(
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
    output = process.stdout.strip()
    if process.returncode != 0 and not output:
        detail = (process.stderr or "update worker failed").strip().splitlines()[-1]
        return {**base, "ok": False, "error": detail[:1000]}
    try:
        report = json.loads(output)
    except json.JSONDecodeError:
        detail = (process.stderr or output or "invalid update response").strip().splitlines()[-1]
        return {**base, "ok": False, "error": detail[:1000]}
    return {**base, **report}


def invoke_workers(
    machines: list[dict[str, Any]],
    manifest: dict[str, Any],
    ids: list[str],
    *,
    mode: str,
    resolved: dict[str, str],
    source_id: str,
) -> list[dict[str, Any]]:
    return [
        invoke_worker(
            machine,
            manifest,
            ids,
            mode=mode,
            resolved=resolved,
            source_id=source_id,
        )
        for machine in machines
    ]


def print_reports(reports: list[dict[str, Any]]) -> None:
    for report in reports:
        label = f"{report.get('display_name') or report.get('id')} ({report.get('id')})"
        if not report.get("ok"):
            print(f"{label}: ERROR {report.get('error', 'worker failed')}")
            continue
        print(f"{label}:")
        for item in report.get("results", []):
            before = item.get("before") or {}
            after = item.get("after") or {}
            old = before.get("version") or ("installed" if before.get("installed") else "absent")
            new = after.get("version") or ("installed" if after.get("installed") else old)
            detail = f"; {item['detail']}" if item.get("detail") and item["detail"] != "ready" else ""
            print(
                f"  {item.get('id')}: {item.get('status')} via {item.get('method')} "
                f"({old} -> {new}){detail}"
            )


def sync_arguments(args: argparse.Namespace, parts: set[str], mode: str) -> list[str]:
    selected: list[str] = []
    if parts & {"dependencies", "coding-tools"}:
        selected.append("--dependencies")
    for dependency_id in args.dependency:
        selected.extend(["--dependency", dependency_id])
    if "workspace-deps" in parts:
        selected.extend(["--workspaces", "--workspace-deps"])
    if "skills" in parts:
        selected.append("--skills")
    if not selected:
        return []
    command = ["sync", *selected]
    if mode == "dry-run":
        command.append("--dry-run")
    elif mode == "verify":
        command.append("--verify")
    if args.local_only:
        command.append("--local-only")
    else:
        for target in args.target:
            command.extend(["--target", target])
    command.extend(["--root", str(args.root), "--home", str(args.home)])
    if args.machine_registry:
        command.extend(["--machine-registry", str(args.machine_registry)])
    return command


def run_sync(
    args: argparse.Namespace,
    parts: set[str],
    mode: str,
    dependency_manifest: dict[str, Any] | None = None,
) -> int:
    arguments = sync_arguments(args, parts, mode)
    if not arguments:
        return 0
    if dependency_manifest is None:
        return subprocess.run([sys.executable, str(PACKAGE_DIRECTORY / "src/sync_agents.py"), *arguments]).returncode
    with tempfile.TemporaryDirectory(prefix="fleet-dependency-manifest-") as directory:
        path = Path(directory) / "dependencies.json"
        path.write_text(json.dumps(dependency_manifest, indent=2) + "\n", encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(PACKAGE_DIRECTORY / "src/sync_agents.py"),
                *arguments,
                "--dependency-manifest",
                str(path),
            ]
        ).returncode


def update_exact_component(
    args: argparse.Namespace,
    parts: set[str],
    manifest_path: Path,
    manifest: dict[str, Any],
) -> int:
    if len(args.dependency) != 1:
        raise FleetUpdateError("--version requires exactly one --dependency")
    candidate = exact_component_manifest(manifest, args.dependency[0], args.version)
    mode = "verify" if args.verify else "dry-run" if args.dry_run else "apply"
    print(f"Mode: {mode}")
    print(f"Dependency: {args.dependency[0]}")
    print(f"Exact version: {args.version}")
    result = run_sync(args, parts, mode, candidate)
    if result != 0 or mode != "apply":
        return result
    changed = write_manifest(manifest_path, candidate)
    print("Recorded exact fleet desired state." if changed else "Exact fleet desired state was already recorded.")
    return run_sync(args, parts, "verify")


def run_vault_dependencies(root: Path, mode: str) -> int:
    command = [sys.executable, str(root / "_system/deps/install.py")]
    command.append("--verify" if mode == "verify" else "--dry-run" if mode == "dry-run" else "--update")
    return subprocess.run(command, cwd=root).returncode


def print_skill_source_plan(plan: dict[str, Any]) -> None:
    print("Skill sources:")
    for item in plan.get("github", []):
        detail = f"; {item['detail']}" if item.get("detail") else ""
        print(f"  {item['id']}: {item['status']} ({item['skill_count']} skills){detail}")
        preview = str(item.get("preview") or "").strip()
        if preview:
            print(preview)


def print_applied_skill_sources(result: dict[str, Any]) -> None:
    print("Applied skill-source updates:")
    for item in result.get("github", []):
        print(f"  {item['id']}: {item['status']} ({item['skill_count']} skills, {item['changed_skills']} changed)")


def write_aggregate_updates(root: Path, reports: list[dict[str, Any]]) -> None:
    path = root / "_system/agents/_package/generated/state/dependencies.lock.json"
    existing = read_json(path, "aggregate dependency lock") if path.exists() else {"schema_version": 1, "machines": {}}
    machines = existing.get("machines")
    if not isinstance(machines, dict):
        raise FleetUpdateError("aggregate dependency lock needs machines")
    for report in reports:
        machine_id = str(report["id"])
        current = machines.get(machine_id, {})
        if not isinstance(current, dict):
            current = {}
        current["update"] = {
            key: value
            for key, value in report.items()
            if key not in {"display_name", "ok"}
        }
        machines[machine_id] = current
    existing["schema_version"] = 1
    existing["machines"] = machines
    existing["verified_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(existing, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def update(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    args.root = root
    args.home = args.home.expanduser().resolve()
    registry_path = (args.machine_registry or root / "_system/agents/_package/instance/fleet/machines.json").expanduser().resolve()
    registry = agent_configuration.load_registry(registry_path)
    source_id = agent_configuration.current_machine_id(root)
    agent_configuration.require_primary(registry, source_id)
    parts = selected_parts(args)
    if args.dependency and any(
        getattr(args, field)
        for field in ("coding_tools", "skills", "workspace_deps", "vault_dependencies")
    ):
        raise FleetUpdateError("--dependency cannot be combined with non-dependency selectors")
    manifest_path = root / "_system/agents/_package/defaults/dependencies.json"
    manifest = read_json(manifest_path, "agent dependency registry")
    ids = dependency_ids(manifest, parts, args.dependency)
    source = next((item for item in registry["machines"] if item.get("id") == source_id), None)
    if not isinstance(source, dict) or source.get("enabled") is not True:
        raise FleetUpdateError("current primary machine is not an enabled registry target")
    targets = [] if args.local_only else agent_configuration.resolve_targets(registry, source_id, args.target)
    machines = [source] if args.local_only else targets if args.target else [source, *targets]
    skill_snapshot_machines = [source, *targets]
    if args.version is not None:
        return update_exact_component(args, parts, manifest_path, manifest)
    resolved_t3 = exact_t3_version(args, parts)
    resolved = {"t3-code": resolved_t3} if resolved_t3 else {}
    mode = "verify" if args.verify else "dry-run" if args.dry_run else "apply"

    source_config: dict[str, Any] = {}
    source_plan: dict[str, Any] | None = None
    if args.skill_source and "skills" not in parts:
        raise FleetUpdateError("--skill-source requires --skills or the default all-parts update")
    if "skills" in parts:
        source_config = read_json(root / "_system/agents/_package/instance/skills/skill-sources.json", "skill-source config")
        skill_source_config.validate_config(source_config)
        source_plan = skill_source_update.plan_sources(root, args.skill_source)

    print(f"Mode: {mode}")
    print(f"Parts: {', '.join(sorted(parts))}")
    if resolved_t3:
        print(f"Resolved T3 nightly: {resolved_t3}")
    if source_plan is not None:
        print_skill_source_plan(source_plan)
        if not source_plan.get("ready"):
            print("Skill-source preflight has blockers; no update changes were applied.", file=sys.stderr)
            return 1 if not args.verify else 2

    preview: list[dict[str, Any]] = []
    if ids:
        preview = invoke_workers(machines, manifest, ids, mode="verify" if args.verify else "dry-run", resolved=resolved, source_id=source_id)
        print_reports(preview)
    preview_ready = all(report.get("ok") and report.get("can_apply" if not args.verify else "ready") for report in preview)
    if not preview_ready:
        print("Update preflight has blockers; no update changes were applied.", file=sys.stderr)
        return 1 if not args.verify else 2

    if "vault-dependencies" in parts:
        vault_result = run_vault_dependencies(root, "verify" if args.verify else "dry-run")
        if vault_result != 0:
            return vault_result
    sync_preview = run_sync(args, parts, "verify" if args.verify else "dry-run")
    if sync_preview != 0:
        print("Agent sync preflight failed; no update changes were applied.", file=sys.stderr)
        return sync_preview
    if args.verify:
        if "skills" in parts:
            skill_source_update.build_lock(root, source_config, skill_snapshot_machines, source_id)
            print("Verified current GH, local-repository, and distributed skill facts; no lock was written.")
        return 0
    if args.dry_run:
        return 0

    applied: list[dict[str, Any]] = []
    if source_plan is not None:
        applied_sources = skill_source_update.apply_sources(root, source_plan)
        print_applied_skill_sources(applied_sources)
    if ids:
        applied = invoke_workers(machines, manifest, ids, mode="apply", resolved=resolved, source_id=source_id)
        print("Applied dependency updates:")
        print_reports(applied)
        if not all(report.get("ok") and report.get("ready") for report in applied):
            raise FleetUpdateError("one or more dependency updates failed")
    if "vault-dependencies" in parts and run_vault_dependencies(root, "apply") != 0:
        raise FleetUpdateError("public Vault dependency update failed")
    if run_sync(args, parts, "apply") != 0:
        raise FleetUpdateError("post-update agent sync failed")
    verified = invoke_workers(machines, manifest, ids, mode="verify", resolved=resolved, source_id=source_id) if ids else []
    if not all(report.get("ok") and report.get("ready") for report in verified):
        raise FleetUpdateError("post-update dependency verification failed")
    if run_sync(args, parts, "verify") != 0:
        raise FleetUpdateError("post-update fleet verification failed")
    if "vault-dependencies" in parts and run_vault_dependencies(root, "verify") != 0:
        raise FleetUpdateError("post-update public Vault dependency verification failed")
    if verified:
        write_aggregate_updates(root, verified)
    if "skills" in parts:
        skill_lock = skill_source_update.build_lock(root, source_config, skill_snapshot_machines, source_id)
        skill_source_update.atomic_write_lock(root / "_system/agents/_package/generated/state/skills.lock.json", skill_lock)
        print("Recorded verified GH, local-repository, and distributed skill facts.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["update"])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="resolve and preview without changing machines")
    mode.add_argument("--verify", action="store_true", help="verify selected dependencies without resolving or changing them")
    parser.add_argument("--dependencies", action="store_true", help="update approved packages, applications, providers, and capabilities")
    parser.add_argument(
        "--dependency",
        action="append",
        default=[],
        help="update one approved dependency; repeatable",
    )
    parser.add_argument(
        "--version",
        help="adopt one exact immutable version; requires exactly one --dependency",
    )
    parser.add_argument("--coding-tools", dest="coding_tools", action="store_true", help="update installed Codex, T3, Claude Code, OpenCode, and related coding tools")
    parser.add_argument("--skills", action="store_true", help="update approved skill sources and distribute snapshots")
    parser.add_argument(
        "--skill-source",
        action="append",
        default=[],
        help="restrict skill updates to gh:<repository-directory>; repeatable",
    )
    parser.add_argument("--workspace-deps", dest="workspace_deps", action="store_true", help="update transitional workspace-built commands")
    parser.add_argument("--vault-dependencies", dest="vault_dependencies", action="store_true", help="update the independent public Vault dependencies on this full-Vault Mac")
    parser.add_argument("--target", action="append", default=[], help="target machine ID; repeatable")
    parser.add_argument("--local-only", action="store_true", help="operate only on the registered primary")
    parser.add_argument("--t3-version", help="use one exact approved T3 nightly version")
    parser.add_argument("--machine-registry", type=Path)
    parser.add_argument("--root", type=Path, default=agent_configuration.vault_root())
    parser.add_argument("--home", type=Path, default=Path.home())
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return update(parse_args(argv))
    except (
        FleetUpdateError,
        RuntimeError,
        dependency_worker.DependencyError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Fleet update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
