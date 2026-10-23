#!/usr/bin/env python3
"""Manage opt-in, machine-specific macOS login automation."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from package_layout import INTERNAL_ROOT, active_instance_root
from fleet_machine import current_machine_id as fleet_identity


DEFAULT_LABEL = "com.obsidian-context-vault.mac-startup"
DEFAULT_CONFIG_RELATIVE = Path("skills/config/fleet-i-code-folder-and-computer-topology/Mac Startup/defaults.json")
PRIVATE_CONFIG_RELATIVE = Path("fleet/startup.json")
TOPOLOGY_REGISTRY_RELATIVE = Path(
    "fleet/machines.json"
)
SOURCE_RUNNER = INTERNAL_ROOT / "assets/mac-startup/startup.sh"

RUNTIME_DIR = Path.home() / "Library/Application Support/obsidian-context-vault/mac-startup"
RUNTIME_RUNNER = RUNTIME_DIR / "startup.sh"
RUNTIME_CONFIG = RUNTIME_DIR / "runtime-config.json"
LEGACY_ARCHIVE_DIR = RUNTIME_DIR / "legacy-launchagents"
LAUNCH_AGENT_DIR = Path.home() / "Library/LaunchAgents"
LOG_DIR = Path.home() / "Library/Logs"
MACHINE_ID_PATH = Path.home() / ".config/vault/machine-id"

SUPPORTED_ACTIONS = {"open-applications", "remap-tilde-key"}
BUNDLE_ID_RE = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
MAPPING_SOURCE = 0x700000035
MAPPING_DESTINATION = 0x700000064


class MacStartupError(RuntimeError):
    """Raised for invalid configuration or an unsafe startup operation."""


def read_json(path: Path, *, required: bool) -> dict[str, object]:
    if not path.is_file():
        if required:
            raise MacStartupError(f"missing required config: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MacStartupError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise MacStartupError(f"config must be a JSON object: {path}")
    return data


def current_machine_id(root: Path) -> str | None:
    try:
        return fleet_identity()
    except RuntimeError:
        return None

def registered_machine(root: Path, machine_id: str | None) -> dict[str, object] | None:
    if not machine_id:
        return None
    registry = read_json(root / TOPOLOGY_REGISTRY_RELATIVE, required=False)
    machines = registry.get("machines", [])
    if not isinstance(machines, list):
        return None
    for machine in machines:
        if isinstance(machine, dict) and machine.get("id") == machine_id:
            return machine
    return None


def validate_label(label: object) -> str:
    value = str(label or DEFAULT_LABEL).strip()
    if not re.fullmatch(r"[A-Za-z0-9.-]+", value):
        raise MacStartupError(f"invalid LaunchAgent label: {value!r}")
    return value


def validate_actions(actions: object) -> dict[str, bool]:
    if not isinstance(actions, dict):
        raise MacStartupError("mac-startup actions must be a JSON object")
    normalized: dict[str, bool] = {}
    for name, enabled in actions.items():
        if name not in SUPPORTED_ACTIONS:
            raise MacStartupError(f"unsupported mac-startup action: {name}")
        if not isinstance(enabled, bool):
            raise MacStartupError(f"mac-startup action {name} must be true or false")
        normalized[name] = enabled
    for name in SUPPORTED_ACTIONS:
        normalized.setdefault(name, False)
    return normalized


def validate_applications(applications: object) -> list[str]:
    if applications is None:
        return []
    if not isinstance(applications, list):
        raise MacStartupError("mac-startup applications must be a JSON array")
    normalized: list[str] = []
    for application in applications:
        if not isinstance(application, str) or not BUNDLE_ID_RE.fullmatch(application):
            raise MacStartupError(
                f"invalid mac-startup application bundle identifier: {application!r}"
            )
        if application not in normalized:
            normalized.append(application)
    return normalized


def validate_legacy_labels(
    labels: object, *, managed_label: str = DEFAULT_LABEL
) -> list[str]:
    if labels is None:
        return []
    if not isinstance(labels, list):
        raise MacStartupError("legacy_launch_agents must be a JSON array")
    normalized: list[str] = []
    for label in labels:
        value = validate_label(label)
        if value == managed_label:
            raise MacStartupError("managed mac-startup label cannot be listed as legacy")
        if value not in normalized:
            normalized.append(value)
    return normalized


def load_config(root: Path, machine_id: str | None = None) -> dict[str, object]:
    defaults = read_json(root / DEFAULT_CONFIG_RELATIVE, required=True)
    if defaults.get("schema_version") != 1:
        raise MacStartupError("mac-startup defaults schema_version must be 1")

    resolved_machine_id = machine_id if machine_id is not None else current_machine_id(root)
    private = read_json(root / PRIVATE_CONFIG_RELATIVE, required=False)
    if private and private.get("schema_version") != 1:
        raise MacStartupError("private mac-startup schema_version must be 1")
    machine_override: dict[str, object] = {}
    machines = private.get("machines", {})
    if resolved_machine_id and isinstance(machines, dict):
        candidate = machines.get(resolved_machine_id, {})
        if isinstance(candidate, dict):
            machine_override = candidate

    default_actions = validate_actions(defaults.get("actions", {}))
    override_actions = machine_override.get("actions", {})
    if not isinstance(override_actions, dict):
        raise MacStartupError("machine mac-startup actions must be a JSON object")
    actions = validate_actions({**default_actions, **override_actions})

    applications = validate_applications(
        machine_override.get("applications", defaults.get("applications", []))
    )
    if actions["open-applications"] and not applications:
        raise MacStartupError(
            "mac-startup open-applications action requires at least one application"
        )

    enabled = machine_override.get("enabled", defaults.get("enabled", False))
    if not isinstance(enabled, bool):
        raise MacStartupError("mac-startup enabled must be true or false")

    label = validate_label(machine_override.get("label", defaults.get("label", DEFAULT_LABEL)))
    legacy = machine_override.get(
        "legacy_launch_agents", defaults.get("legacy_launch_agents", [])
    )
    return {
        "machine_id": resolved_machine_id,
        "enabled": enabled,
        "label": label,
        "actions": actions,
        "applications": applications,
        "legacy_launch_agents": validate_legacy_labels(legacy, managed_label=label),
    }


def enabled_actions(config: dict[str, object]) -> list[str]:
    actions = config.get("actions", {})
    assert isinstance(actions, dict)
    return sorted(name for name, enabled in actions.items() if enabled)


def runtime_actions(config: dict[str, object]) -> list[str]:
    actions = enabled_actions(config)
    runtime = [action for action in actions if action != "open-applications"]
    if "open-applications" in actions:
        applications = config.get("applications", [])
        assert isinstance(applications, list)
        runtime.extend(f"open-application:{bundle_id}" for bundle_id in applications)
    return runtime


def require_eligible_machine(
    root: Path,
    config: dict[str, object],
    *,
    provision_disabled: bool = False,
) -> dict[str, object]:
    if sys.platform != "darwin":
        raise MacStartupError("mac-startup requires macOS launchd")
    machine_id = config.get("machine_id")
    if not isinstance(machine_id, str) or not machine_id:
        raise MacStartupError(
            "this machine has no Fleet identity; identify it with `fleet machine identify ID`"
        )
    machine = registered_machine(root, machine_id)
    if machine is None:
        raise MacStartupError(f"machine {machine_id!r} is not in the private machine registry")
    if machine.get("enabled") is not True and not provision_disabled:
        raise MacStartupError(f"machine {machine_id!r} is disabled in the machine registry")
    if provision_disabled and machine.get("enabled") is True:
        raise MacStartupError(
            f"machine {machine_id!r} is already enabled; omit --provision-disabled"
        )
    if machine.get("platform") != "macos":
        raise MacStartupError(f"machine {machine_id!r} is not registered as macOS")
    if config.get("enabled") is not True:
        raise MacStartupError(f"mac-startup is disabled for machine {machine_id!r}")
    if not enabled_actions(config):
        raise MacStartupError(f"mac-startup has no enabled actions for machine {machine_id!r}")
    return machine


def launch_domain() -> str:
    return f"gui/{os.getuid()}"


def launch_service(label: str) -> str:
    return f"{launch_domain()}/{label}"


def plist_path(label: str) -> Path:
    return LAUNCH_AGENT_DIR / f"{label}.plist"


def runtime_command(actions: list[str], *, runner: Path | None = None) -> list[str]:
    resolved_runner = RUNTIME_RUNNER if runner is None else runner
    return ["/bin/zsh", str(resolved_runner), *actions]


def launch_agent_plist(label: str, actions: list[str]) -> dict[str, object]:
    return {
        "Label": label,
        "ProgramArguments": runtime_command(actions),
        "WorkingDirectory": str(RUNTIME_DIR),
        "RunAtLoad": True,
        "ProcessType": "Background",
        "StandardOutPath": str(LOG_DIR / "obsidian-context-vault-mac-startup.out.log"),
        "StandardErrorPath": str(LOG_DIR / "obsidian-context-vault-mac-startup.err.log"),
    }


def run_launchctl(
    args: list[str], *, check: bool = True, quiet: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        text=True,
        check=check,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.DEVNULL if quiet else None,
    )


def service_loaded(label: str) -> bool:
    if sys.platform != "darwin":
        return False
    return run_launchctl(["print", launch_service(label)], check=False, quiet=True).returncode == 0


def atomic_write(path: Path, data: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    try:
        if mode is not None:
            temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def next_archive_path(label: str) -> Path:
    candidate = LEGACY_ARCHIVE_DIR / f"{label}.plist"
    if not candidate.exists():
        return candidate
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    candidate = LEGACY_ARCHIVE_DIR / f"{label}.{stamp}.plist"
    suffix = 2
    while candidate.exists():
        candidate = LEGACY_ARCHIVE_DIR / f"{label}.{stamp}.{suffix}.plist"
        suffix += 1
    return candidate


def archive_legacy_agents(config: dict[str, object], *, dry_run: bool) -> list[Path]:
    archived: list[Path] = []
    labels = config.get("legacy_launch_agents", [])
    assert isinstance(labels, list)
    for label in labels:
        assert isinstance(label, str)
        path = plist_path(label)
        loaded = service_loaded(label)
        if not loaded and not path.exists():
            continue
        destination = next_archive_path(label)
        if dry_run:
            if loaded:
                print(f"would bootout legacy {launch_service(label)}")
            if path.exists():
                print(f"would archive {path} -> {destination}")
            archived.append(destination)
            continue
        if path.exists():
            run_launchctl(["bootout", launch_domain(), str(path)], check=False, quiet=True)
        run_launchctl(["bootout", launch_service(label)], check=False, quiet=True)
        if path.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(destination))
            archived.append(destination)
            print(f"archived legacy LaunchAgent: {destination}")
        elif loaded:
            print(f"unloaded legacy LaunchAgent: {label}")
    return archived


def run_actions(
    root: Path,
    *,
    dry_run: bool,
    deployed: bool = False,
    provision_disabled: bool = False,
) -> int:
    config = load_config(root)
    require_eligible_machine(
        root, config, provision_disabled=provision_disabled
    )
    actions = runtime_actions(config)
    runner = RUNTIME_RUNNER if deployed else SOURCE_RUNNER
    if not runner.is_file():
        raise MacStartupError(f"mac-startup runner is missing: {runner}")
    command = runtime_command(actions, runner=runner)
    if dry_run:
        print("would run: " + " ".join(command))
        return 0
    return subprocess.run(command, cwd=runner.parent).returncode


def install(
    root: Path, *, dry_run: bool, provision_disabled: bool = False
) -> int:
    config = load_config(root)
    require_eligible_machine(
        root, config, provision_disabled=provision_disabled
    )
    machine_id = str(config["machine_id"])
    label = str(config["label"])
    actions = runtime_actions(config)
    source_runner = SOURCE_RUNNER
    if not source_runner.is_file():
        raise MacStartupError(f"mac-startup runner is missing: {source_runner}")
    path = plist_path(label)
    plist = launch_agent_plist(label, actions)

    if dry_run:
        print(f"machine: {machine_id}")
        print(f"enabled actions: {', '.join(actions)}")
        archive_legacy_agents(config, dry_run=True)
        print(f"would copy {source_runner} -> {RUNTIME_RUNNER}")
        print(f"would write {RUNTIME_CONFIG}")
        print(f"would write {path}")
        print(f"would bootstrap {launch_domain()} {path}")
        return 0

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(RUNTIME_RUNNER, source_runner.read_bytes(), mode=0o755)
    runtime_config = {
        "schema_version": 1,
        "machine_id": machine_id,
        "actions": actions,
        "applications": config["applications"],
    }
    atomic_write(
        RUNTIME_CONFIG,
        (json.dumps(runtime_config, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        mode=0o600,
    )
    atomic_write(path, plistlib.dumps(plist, sort_keys=False), mode=0o644)

    archive_legacy_agents(config, dry_run=False)
    run_launchctl(["bootout", launch_service(label)], check=False, quiet=True)
    run_launchctl(["bootstrap", launch_domain(), str(path)])
    run_launchctl(["enable", launch_service(label)], check=False, quiet=True)
    print(f"installed {label}: {path}")
    return run_actions(
        root,
        dry_run=False,
        deployed=True,
        provision_disabled=provision_disabled,
    )


def uninstall(root: Path, *, dry_run: bool) -> int:
    if sys.platform != "darwin":
        raise MacStartupError("mac-startup requires macOS launchd")
    config = load_config(root)
    label = str(config["label"])
    path = plist_path(label)
    targets = [path, RUNTIME_RUNNER, RUNTIME_CONFIG]
    if dry_run:
        print(f"would bootout {launch_service(label)}")
        for target in targets:
            if target.exists():
                print(f"would remove {target}")
        print("current in-memory HID mapping would be left unchanged")
        return 0

    run_launchctl(["bootout", launch_service(label)], check=False, quiet=True)
    for target in targets:
        if target.exists():
            target.unlink()
            print(f"removed {target}")
    print("current in-memory HID mapping was left unchanged")
    return 0


def hidutil_mapping_active() -> tuple[bool, str | None]:
    if sys.platform != "darwin":
        return False, None
    result = subprocess.run(
        ["/usr/bin/hidutil", "property", "--get", "UserKeyMapping"],
        text=True,
        capture_output=True,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    for block in re.findall(r"\{([^}]*)\}", output, flags=re.DOTALL):
        source = re.search(r"HIDKeyboardModifierMappingSrc\s*=\s*(\d+)", block)
        destination = re.search(r"HIDKeyboardModifierMappingDst\s*=\s*(\d+)", block)
        if source and destination:
            if int(source.group(1)) == MAPPING_SOURCE and int(destination.group(1)) == MAPPING_DESTINATION:
                return True, output.strip()
    return False, output.strip() or None


def status_payload(root: Path) -> dict[str, object]:
    config = load_config(root)
    machine_id = config.get("machine_id")
    assert machine_id is None or isinstance(machine_id, str)
    label = str(config["label"])
    machine = registered_machine(root, machine_id)
    mapping_active, _ = hidutil_mapping_active()
    legacy: list[dict[str, object]] = []
    labels = config.get("legacy_launch_agents", [])
    assert isinstance(labels, list)
    for legacy_label in labels:
        assert isinstance(legacy_label, str)
        legacy.append(
            {
                "label": legacy_label,
                "loaded": service_loaded(legacy_label),
                "plistPresent": plist_path(legacy_label).is_file(),
            }
        )
    return {
        "supported": sys.platform == "darwin",
        "machineId": machine_id,
        "registeredMachine": machine is not None,
        "machinePlatform": machine.get("platform") if machine else None,
        "configuredEnabled": config.get("enabled") is True,
        "enabledActions": enabled_actions(config),
        "applications": config["applications"],
        "label": label,
        "plist": str(plist_path(label)),
        "plistInstalled": plist_path(label).is_file(),
        "loaded": service_loaded(label),
        "runtime": str(RUNTIME_RUNNER),
        "runtimeInstalled": RUNTIME_RUNNER.is_file(),
        "mapping": {
            "source": MAPPING_SOURCE,
            "destination": MAPPING_DESTINATION,
            "active": mapping_active,
        },
        "legacyAgents": legacy,
        "legacyArchiveDir": str(LEGACY_ARCHIVE_DIR),
    }


def print_status(root: Path, *, json_output: bool) -> int:
    payload = status_payload(root)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(f"supported: {'yes' if payload['supported'] else 'no'}")
    print(f"machine_id: {payload['machineId'] or 'unidentified'}")
    print(f"registered_machine: {'yes' if payload['registeredMachine'] else 'no'}")
    print(f"configured_enabled: {'yes' if payload['configuredEnabled'] else 'no'}")
    actions = payload["enabledActions"]
    assert isinstance(actions, list)
    print(f"enabled_actions: {', '.join(actions) if actions else 'none'}")
    applications = payload["applications"]
    assert isinstance(applications, list)
    print(f"applications: {', '.join(applications) if applications else 'none'}")
    print(f"label: {payload['label']}")
    print(f"plist_installed: {'yes' if payload['plistInstalled'] else 'no'}")
    print(f"loaded: {'yes' if payload['loaded'] else 'no'}")
    print(f"runtime_installed: {'yes' if payload['runtimeInstalled'] else 'no'}")
    mapping = payload["mapping"]
    assert isinstance(mapping, dict)
    print(f"remap_tilde_key_active: {'yes' if mapping['active'] else 'no'}")
    legacy_agents = payload["legacyAgents"]
    assert isinstance(legacy_agents, list)
    for legacy in legacy_agents:
        assert isinstance(legacy, dict)
        print(
            f"legacy {legacy['label']}: loaded={'yes' if legacy['loaded'] else 'no'}, "
            f"plist={'yes' if legacy['plistPresent'] else 'no'}"
        )
    print(f"legacy_archive_dir: {payload['legacyArchiveDir']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fleet machine startup", description="Manage opt-in, per-machine macOS login automation."
    )
    parser.add_argument("--config-root", type=Path, help="Fleet settings override")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--json", action="store_true", help="Emit machine-readable status JSON.")
    for name in ("run", "install", "uninstall"):
        command = subparsers.add_parser(name)
        command.add_argument("--dry-run", action="store_true")
        if name in {"run", "install"}:
            command.add_argument(
                "--provision-disabled",
                action="store_true",
                help="explicitly configure this disabled Mac before fleet enablement",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = active_instance_root(args.config_root)
    try:
        if args.command == "status":
            return print_status(root, json_output=args.json)
        if args.command == "run":
            return run_actions(
                root,
                dry_run=args.dry_run,
                provision_disabled=args.provision_disabled,
            )
        if args.command == "install":
            return install(
                root,
                dry_run=args.dry_run,
                provision_disabled=args.provision_disabled,
            )
        if args.command == "uninstall":
            return uninstall(root, dry_run=args.dry_run)
    except MacStartupError as exc:
        print(f"mac-startup: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
