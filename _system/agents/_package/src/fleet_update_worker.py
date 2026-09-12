#!/usr/bin/env python3
"""Plan and apply approved dependency updates on one fleet machine.

The worker is deliberately self-contained so the primary can send its source and
a JSON payload to machines that do not have the Vault.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform as host_platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.request import Request, urlopen


class FleetUpdateError(RuntimeError):
    pass


AUTOMATIC_PACKAGE_MANAGERS = {
    "apt",
    "brew",
    "brew-cask",
    "npm",
    "rclone-selfupdate",
    "uv-tool",
}
CODING_ADAPTERS = {"codex", "t3-code", "claude-code", "opencode"}
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9-]*")


def platform_name() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    raise FleetUpdateError(f"unsupported platform: {sys.platform}")


def environment() -> dict[str, str]:
    home = Path.home()
    env = dict(os.environ)
    env["NPM_CONFIG_PREFIX"] = str(home / ".local")
    env["PATH"] = ":".join(
        str(path)
        for path in (
            home / ".local/bin",
            home / ".bun/bin",
            Path("/opt/homebrew/bin"),
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            Path("/bin"),
            Path("/usr/sbin"),
            Path("/sbin"),
        )
    )
    return env


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            env=environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
        return subprocess.CompletedProcess(command, 124, stdout, stderr or "command timed out after 600 seconds")


def output_line(process: subprocess.CompletedProcess[str]) -> str | None:
    output = (process.stdout or process.stderr).strip().splitlines()
    return output[0][:500] if output else None


def command_state(command: str, args: list[str] | None = None) -> dict[str, Any]:
    executable = shutil.which(command, path=environment()["PATH"])
    if executable is None:
        return {"installed": False, "path": None, "version": None}
    process = run([executable, *(args or ["--version"])])
    return {
        "installed": process.returncode == 0,
        "path": executable,
        "version": output_line(process),
        "detail": None if process.returncode == 0 else output_line(process),
    }


def package_installed(manager: str, package: str) -> bool:
    if manager == "brew":
        return run(["brew", "list", "--versions", package]).returncode == 0
    if manager == "brew-cask":
        return run(["brew", "list", "--cask", "--versions", package]).returncode == 0
    if manager == "apt":
        return run(["dpkg-query", "-W", "-f=${Status}", package]).stdout.strip() == "install ok installed"
    if manager == "npm":
        return run(["npm", "list", "--global", "--depth=0", package]).returncode == 0
    if manager == "uv-tool":
        result = run(["uv", "tool", "list"])
        return result.returncode == 0 and any(
            line.split(" ", 1)[0].lower() == package.lower()
            for line in result.stdout.splitlines()
            if line and not line.startswith("-")
        )
    if manager == "rclone-selfupdate":
        return package == "rclone" and command_state("rclone")["installed"]
    return False


def package_update_command(manager: str, package: str) -> list[str]:
    if manager == "brew":
        return ["brew", "upgrade", package]
    if manager == "brew-cask":
        return ["brew", "upgrade", "--cask", package]
    if manager == "apt":
        return ["sudo", "-n", "apt-get", "install", "-y", "--only-upgrade", package]
    if manager == "npm":
        return ["npm", "install", "--global", "--prefix", str(Path.home() / ".local"), f"{package}@latest"]
    if manager == "uv-tool":
        return ["uv", "tool", "upgrade", package]
    if manager == "rclone-selfupdate":
        executable = shutil.which("rclone", path=environment()["PATH"])
        if executable is None or package != "rclone":
            raise FleetUpdateError("rclone-selfupdate needs an installed rclone command")
        return ["sudo", "-n", executable, "selfupdate", "--stable", "--package", "deb"]
    raise FleetUpdateError(f"unsupported update manager: {manager}")


def command_preflight(command: list[str]) -> tuple[bool, str]:
    executable = shutil.which(command[0], path=environment()["PATH"])
    if executable is None:
        return False, f"{command[0]} is missing"
    if command[:2] == ["sudo", "-n"] and run([executable, "-n", "true"]).returncode != 0:
        return False, "noninteractive sudo is unavailable"
    return True, "ready"


def result(
    dependency_id: str,
    *,
    status: str,
    method: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    detail: str | None = None,
    command: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": dependency_id,
        "status": status,
        "method": method,
        "before": before,
        "after": after,
        "detail": detail,
        "command": command,
        "ready": status not in {"blocked", "failed", "manual-action"},
    }


def verify_from_contract(dependency: dict[str, Any]) -> dict[str, Any]:
    verify = dependency.get("contract", {}).get("verify", {})
    if isinstance(verify, dict) and isinstance(verify.get("command"), str):
        return command_state(str(verify["command"]), [str(arg) for arg in verify.get("args", [])])
    return {"installed": False, "path": None, "version": None}


def plan_package(dependency: dict[str, Any], platform: str) -> dict[str, Any]:
    dependency_id = str(dependency["id"])
    contract = dependency["contract"]
    recipe = contract.get("recipes", {}).get(platform)
    if not isinstance(recipe, dict):
        return result(dependency_id, status="skipped-platform", method="registry", detail=f"not declared for {platform}")
    manager = str(recipe.get("manager") or "")
    package = str(recipe.get("package") or "")
    before = verify_from_contract(dependency)
    if manager not in AUTOMATIC_PACKAGE_MANAGERS:
        return result(
            dependency_id,
            status="skipped-policy",
            method=manager or "declared-artifact",
            before=before,
            detail="the declared artifact is version-pinned; update its registry recipe before syncing",
        )
    if not package_installed(manager, package):
        return result(
            dependency_id,
            status="skipped-not-installed",
            method=manager,
            before=before,
            detail="normal agent sync owns approved missing-package installation",
        )
    command = package_update_command(manager, package)
    ready, detail = command_preflight(command)
    return result(
        dependency_id,
        status="planned" if ready else "blocked",
        method=manager,
        before=before,
        detail=detail,
        command=command if ready else None,
    )


def macos_application_state(contract: dict[str, Any]) -> dict[str, Any]:
    application = Path(str(contract.get("application") or ""))
    installed = application.is_dir()
    version: str | None = None
    if installed:
        process = run(["/usr/bin/defaults", "read", str(application / "Contents/Info"), "CFBundleShortVersionString"])
        version = output_line(process)
    return {"installed": installed, "path": str(application), "version": version}


def plan_macos_application(dependency: dict[str, Any], platform: str) -> dict[str, Any]:
    dependency_id = str(dependency["id"])
    if platform != "macos":
        return result(dependency_id, status="skipped-platform", method="registry")
    contract = dependency["contract"]
    before = macos_application_state(contract)
    cask = str(contract.get("cask") or "")
    if not before["installed"]:
        return result(dependency_id, status="skipped-not-installed", method="macos-application", before=before)
    if cask and package_installed("brew-cask", cask):
        command = package_update_command("brew-cask", cask)
        ready, detail = command_preflight(command)
        return result(
            dependency_id,
            status="planned" if ready else "blocked",
            method="brew-cask",
            before=before,
            detail=detail,
            command=command if ready else None,
        )
    return result(
        dependency_id,
        status="manual-action",
        method="native-application",
        before=before,
        detail="installed application is not Homebrew-owned; use its signed native update channel",
    )


def selected_provider(machine: dict[str, Any]) -> str | None:
    access = machine.get("machine_access")
    return str(access.get("provider")) if isinstance(access, dict) and access.get("provider") else None


def plan_provider(dependency: dict[str, Any], machine: dict[str, Any], platform: str) -> dict[str, Any]:
    dependency_id = str(dependency["id"])
    if selected_provider(machine) != dependency_id:
        return result(dependency_id, status="skipped-not-selected", method="machine-registry")
    if platform == "linux":
        package = "tailscale" if dependency_id == "tailscale" else "wireguard-tools"
        before = command_state("tailscale" if dependency_id == "tailscale" else "wg")
        if not package_installed("apt", package):
            return result(dependency_id, status="manual-action", method="provider", before=before, detail="provider is not owned by the approved APT package")
        command = package_update_command("apt", package)
        ready, detail = command_preflight(command)
        return result(dependency_id, status="planned" if ready else "blocked", method="apt", before=before, detail=detail, command=command if ready else None)
    application_contract = dependency.get("contract", {}).get("macos_application")
    if dependency_id == "wireguard" and isinstance(application_contract, dict):
        before = macos_application_state(application_contract)
    else:
        before = command_state("tailscale")
    cask = dependency_id
    if package_installed("brew-cask", cask):
        command = package_update_command("brew-cask", cask)
        ready, detail = command_preflight(command)
        return result(dependency_id, status="planned" if ready else "blocked", method="brew-cask", before=before, detail=detail, command=command if ready else None)
    return result(dependency_id, status="manual-action", method="native-provider", before=before, detail="selected provider is not Homebrew-owned; use its signed native update channel")


def npm_global_package(name: str) -> bool:
    return package_installed("npm", name)


def t3_global_install_command(before: dict[str, Any], version: str) -> tuple[list[str] | None, str | None]:
    executable = Path(str(before.get("path") or ""))
    if not executable:
        return None, None
    resolved = executable.resolve()
    user_root = Path.home() / ".local/lib/node_modules/t3"
    if resolved == user_root or user_root in resolved.parents:
        return [
            "npm",
            "install",
            "--global",
            "--prefix",
            str(Path.home() / ".local"),
            f"t3@{version}",
        ], None
    system_root = Path("/usr/local/lib/node_modules/t3")
    if resolved == system_root or system_root in resolved.parents:
        npm = Path("/usr/local/bin/npm")
        if not npm.is_file():
            return None, "system T3 provenance has no matching /usr/local npm"
        command = [str(npm), "install", "--global", "--prefix", "/usr/local", f"t3@{version}"]
        if resolved.stat().st_uid == 0:
            command = ["sudo", "-n", *command]
        return command, None
    if npm_global_package("t3"):
        return ["npm", "install", "--global", f"t3@{version}"], None
    return None, None


def t3_state(contract: dict[str, Any]) -> dict[str, Any]:
    command = command_state("t3")
    application = Path(str(contract.get("macos_application") or ""))
    app_installed = platform_name() == "macos" and application.is_dir()
    npx_roots = sorted((Path.home() / ".npm/_npx").glob("*/node_modules/t3/package.json"))
    application_state = macos_application_state(
        {"application": str(application)}
    ) if app_installed else {"version": None}
    return {
        **command,
        "installed": bool(command["installed"] or app_installed or npx_roots),
        "version": command.get("version") or application_state.get("version"),
        "application": str(application) if app_installed else None,
        "npx_cache": str(npx_roots[-1]) if npx_roots else None,
    }


def codesign_team(application: Path) -> str | None:
    process = run(["/usr/bin/codesign", "-dv", "--verbose=4", str(application)])
    match = re.search(r"^TeamIdentifier=(\S+)\s*$", process.stderr, re.MULTILINE)
    return match.group(1) if process.returncode == 0 and match else None


def application_bundle_id(application: Path) -> str | None:
    process = run(
        ["/usr/bin/defaults", "read", str(application / "Contents/Info"), "CFBundleIdentifier"]
    )
    return process.stdout.strip() if process.returncode == 0 else None


def native_t3_asset(contract: dict[str, Any], version: str) -> dict[str, str]:
    repository = str(contract.get("release_repository") or "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise FleetUpdateError("T3 release repository is invalid")
    request = Request(
        f"https://api.github.com/repos/{repository}/releases/tags/v{version}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "vault-fleet-update"},
    )
    with urlopen(request, timeout=30) as response:
        release = json.load(response)
    architecture = host_platform.machine().lower()
    suffix = "-arm64.dmg" if architecture in {"arm64", "aarch64"} else "-x64.dmg" if architecture in {"x86_64", "amd64"} else ""
    if not suffix:
        raise FleetUpdateError(f"unsupported T3 macOS architecture: {architecture}")
    assets = [
        asset
        for asset in release.get("assets", [])
        if isinstance(asset, dict) and str(asset.get("name") or "").endswith(suffix)
    ]
    if release.get("prerelease") is not True or release.get("tag_name") != f"v{version}" or len(assets) != 1:
        raise FleetUpdateError(f"T3 release v{version} has no unique prerelease {suffix} asset")
    asset = assets[0]
    digest = str(asset.get("digest") or "")
    url = str(asset.get("browser_download_url") or "")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest) or not url.startswith(
        f"https://github.com/{repository}/releases/download/v{version}/"
    ):
        raise FleetUpdateError("T3 native asset lacks an approved URL or SHA-256 digest")
    return {"name": str(asset["name"]), "url": url, "sha256": digest.removeprefix("sha256:")}


def validate_t3_application(application: Path, contract: dict[str, Any], version: str) -> tuple[bool, str]:
    if application_bundle_id(application) != contract.get("macos_bundle_id"):
        return False, "bundle identifier mismatch"
    version_process = run(
        ["/usr/bin/defaults", "read", str(application / "Contents/Info"), "CFBundleShortVersionString"]
    )
    if version_process.returncode != 0 or version_process.stdout.strip() != version:
        return False, "version mismatch"
    if codesign_team(application) != contract.get("macos_team_id"):
        return False, "TeamIdentifier mismatch"
    signature = run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(application)])
    if signature.returncode != 0:
        return False, "code signature verification failed"
    gatekeeper = run(["/usr/sbin/spctl", "--assess", "--type", "execute", str(application)])
    if gatekeeper.returncode != 0:
        return False, "Gatekeeper assessment failed"
    return True, "accepted"


def install_native_t3(
    contract: dict[str, Any],
    version: str,
    asset: dict[str, str],
) -> None:
    target = Path(str(contract.get("macos_application") or ""))
    if target.is_symlink() or not target.is_dir() or target.parent not in {Path("/Applications"), Path.home() / "Applications"}:
        raise FleetUpdateError("installed T3 application path is unsafe")
    installed_ok, installed_detail = validate_t3_application(
        target,
        contract,
        macos_application_state({"application": str(target)}).get("version") or "",
    )
    if not installed_ok:
        raise FleetUpdateError(f"installed T3 application is not trusted: {installed_detail}")
    if codesign_team(target) != contract.get("macos_team_id"):
        raise FleetUpdateError("installed T3 TeamIdentifier does not match registry")
    with tempfile.TemporaryDirectory(prefix="vault-t3-update-") as temporary_name:
        temporary = Path(temporary_name)
        dmg = temporary / asset["name"]
        request = Request(asset["url"], headers={"User-Agent": "vault-fleet-update"})
        digest = hashlib.sha256()
        with urlopen(request, timeout=120) as response, dmg.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                handle.write(chunk)
        if digest.hexdigest() != asset["sha256"]:
            raise FleetUpdateError("T3 DMG checksum mismatch")
        attached = run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-plist", str(dmg)])
        if attached.returncode != 0:
            raise FleetUpdateError("T3 DMG could not be mounted read-only")
        mount_points: list[Path] = []
        try:
            plist = plistlib.loads(attached.stdout.encode())
            mount_points = [
                Path(str(entity["mount-point"]))
                for entity in plist.get("system-entities", [])
                if isinstance(entity, dict) and entity.get("mount-point")
            ]
            candidates = [
                child
                for mount in mount_points
                for child in mount.iterdir()
                if child.suffix == ".app" and child.is_dir()
            ]
            if len(candidates) != 1:
                raise FleetUpdateError("T3 DMG does not contain exactly one application")
            candidate = candidates[0]
            accepted, detail = validate_t3_application(candidate, contract, version)
            if not accepted:
                raise FleetUpdateError(f"T3 candidate failed acceptance: {detail}")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            staged = target.parent / f".{target.name}.vault-stage-{stamp}"
            backup = target.parent / f".{target.name}.vault-backup-{stamp}"
            if staged.exists() or backup.exists():
                raise FleetUpdateError("T3 staging path collision")
            shutil.copytree(candidate, staged, symlinks=True)
            staged_ok, staged_detail = validate_t3_application(staged, contract, version)
            if not staged_ok:
                shutil.rmtree(staged, ignore_errors=True)
                raise FleetUpdateError(f"staged T3 candidate failed acceptance: {staged_detail}")
            run(["/usr/bin/osascript", "-e", f'tell application id "{contract["macos_bundle_id"]}" to quit'])
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                running = run(
                    ["/usr/bin/osascript", "-e", f'application id "{contract["macos_bundle_id"]}" is running']
                )
                if running.stdout.strip().lower() != "true":
                    break
                time.sleep(0.25)
            else:
                shutil.rmtree(staged, ignore_errors=True)
                raise FleetUpdateError("T3 did not quit cleanly")
            target.rename(backup)
            try:
                staged.rename(target)
                final_ok, final_detail = validate_t3_application(target, contract, version)
                launchable = run(["/usr/bin/open", "-Ra", str(target)]).returncode == 0
                if not final_ok or not launchable:
                    raise FleetUpdateError(
                        f"installed T3 failed acceptance: {final_detail if not final_ok else 'not launchable'}"
                    )
            except Exception:
                if target.exists():
                    failed = target.parent / f".{target.name}.vault-failed-{stamp}"
                    target.rename(failed)
                    shutil.rmtree(failed, ignore_errors=True)
                backup.rename(target)
                raise
            shutil.rmtree(backup)
        finally:
            for mount in reversed(mount_points):
                run(["/usr/bin/hdiutil", "detach", str(mount)])


def coding_state(dependency: dict[str, Any]) -> dict[str, Any]:
    adapter = dependency["contract"]["adapter"]
    if adapter == "t3-code":
        return t3_state(dependency["contract"])
    command = {"codex": "codex", "claude-code": "claude", "opencode": "opencode"}[adapter]
    return command_state(command)


def codex_command(before: dict[str, Any]) -> tuple[list[str] | None, str, str | None]:
    executable = str(before.get("path") or "")
    if not executable:
        return None, "codex", "not installed"
    help_result = run([executable, "help", "update"])
    if help_result.returncode == 0:
        return [executable, "update"], "codex-self-update", None
    resolved = Path(executable).resolve()
    standalone = Path.home() / ".local/bin/codex"
    standalone_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "packages/standalone/current"
    if Path(executable) == standalone and (resolved == standalone_root or standalone_root in resolved.parents):
        return None, "codex-standalone", "installed standalone CLI does not expose its approved self-updater"
    if package_installed("brew-cask", "codex"):
        return package_update_command("brew-cask", "codex"), "brew-cask", None
    if npm_global_package("@openai/codex"):
        return ["npm", "install", "--global", "@openai/codex@latest"], "npm-global", None
    return None, "unknown", "Codex provenance is unsupported; preserving its path and ownership"


def opencode_command(before: dict[str, Any]) -> tuple[list[str] | None, str, str | None]:
    executable = Path(str(before.get("path") or ""))
    if not executable:
        return None, "opencode", "not installed"
    resolved = executable.resolve()
    user_npm_root = Path.home() / ".local/lib/node_modules/opencode-ai"
    if resolved == user_npm_root or user_npm_root in resolved.parents:
        return [str(executable), "upgrade", "--method", "npm"], "opencode-npm", None
    if Path.home() / ".bun" in resolved.parents:
        return [str(executable), "upgrade", "--method", "bun"], "opencode-bun", None
    if package_installed("brew", "opencode"):
        return [str(executable), "upgrade", "--method", "brew"], "opencode-brew", None
    return None, "unknown", "OpenCode provenance is unsupported; preserving its path and ownership"


def plan_coding_tool(dependency: dict[str, Any], resolved: dict[str, str]) -> dict[str, Any]:
    dependency_id = str(dependency["id"])
    adapter = str(dependency["contract"]["adapter"])
    before = coding_state(dependency)
    if not before["installed"]:
        return result(dependency_id, status="skipped-not-installed", method=adapter, before=before)
    command: list[str] | None
    method: str
    blocker: str | None = None
    if adapter == "codex":
        command, method, blocker = codex_command(before)
    elif adapter == "claude-code":
        command, method = [str(before["path"]), "update"], "claude-self-update"
    elif adapter == "opencode":
        command, method, blocker = opencode_command(before)
    else:
        version = resolved.get("t3-code")
        if not version or "-nightly." not in version:
            return result(dependency_id, status="blocked", method="t3-nightly", before=before, detail="one exact nightly version was not resolved")
        if version in str(before.get("version") or ""):
            return result(
                dependency_id,
                status="already-current",
                method="exact-nightly",
                before=before,
                detail="installed T3 already matches the resolved fleet version",
            )
        command, provenance_error = t3_global_install_command(before, version)
        if provenance_error:
            return result(dependency_id, status="blocked", method="npm-global", before=before, detail=provenance_error)
        if command:
            method = "npm-global"
        elif before.get("npx_cache") and not before.get("application") and not before.get("path"):
            command, method = ["npx", "--yes", f"t3@{version}", "--version"], "npx-exact"
        elif before.get("application") and platform_name() == "macos":
            try:
                asset = native_t3_asset(dependency["contract"], version)
            except (FleetUpdateError, OSError, ValueError) as exc:
                return result(dependency_id, status="blocked", method="signed-github-dmg", before=before, detail=str(exc))
            item = result(
                dependency_id,
                status="already-current" if before.get("version") == version else "planned",
                method="signed-github-dmg",
                before=before,
                detail="exact signed nightly asset resolved",
            )
            item["action"] = {"kind": "t3-dmg", "version": version, "asset": asset}
            return item
        else:
            command, method, blocker = None, "native-t3", "installed T3 provenance is unsupported"
    if blocker or command is None:
        return result(dependency_id, status="manual-action", method=method, before=before, detail=blocker)
    ready, detail = command_preflight(command)
    return result(dependency_id, status="planned" if ready else "blocked", method=method, before=before, detail=detail, command=command if ready else None)


def plan_lifecycle_owned(dependency: dict[str, Any]) -> dict[str, Any]:
    contract = dependency["contract"]
    commands = contract.get("commands", [])
    before = command_state(str(commands[0])) if isinstance(commands, list) and commands else None
    return result(
        str(dependency["id"]),
        status="skipped-policy",
        method=str(contract.get("adapter") or "lifecycle"),
        before=before,
        detail="this capability is updated by its owning lifecycle or machine image",
    )


def selected_dependencies(payload: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = payload.get("manifest")
    selected_ids = payload.get("dependency_ids")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        raise FleetUpdateError("payload needs dependency registry schema 2")
    if not isinstance(selected_ids, list) or not all(isinstance(item, str) and SAFE_ID.fullmatch(item) for item in selected_ids):
        raise FleetUpdateError("payload needs safe dependency_ids")
    raw = manifest.get("dependencies")
    if not isinstance(raw, list):
        raise FleetUpdateError("dependency registry needs dependencies")
    by_id = {str(item.get("id")): item for item in raw if isinstance(item, dict)}
    missing = set(selected_ids) - set(by_id)
    if missing:
        raise FleetUpdateError(f"unknown selected dependencies: {sorted(missing)}")
    return [by_id[item] for item in selected_ids]


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def reconcile(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "dry-run")
    if mode not in {"apply", "dry-run", "verify"}:
        raise FleetUpdateError(f"unsupported mode: {mode}")
    machine = payload.get("machine")
    if not isinstance(machine, dict) or not isinstance(machine.get("id"), str):
        raise FleetUpdateError("payload needs a machine")
    platform = platform_name()
    resolved = payload.get("resolved", {})
    if not isinstance(resolved, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in resolved.items()):
        raise FleetUpdateError("resolved versions must be strings")
    planned: list[dict[str, Any]] = []
    for dependency in selected_dependencies(payload):
        dependency_id = str(dependency["id"])
        if platform not in dependency.get("platforms", []):
            planned.append(result(dependency_id, status="skipped-platform", method="registry"))
            continue
        kind = dependency.get("kind")
        adapter = dependency.get("contract", {}).get("adapter")
        if mode == "verify" and adapter in CODING_ADAPTERS:
            before = coding_state(dependency)
            item = result(
                dependency_id,
                status="verified-installed" if before["installed"] else "skipped-not-installed",
                method=str(adapter),
                before=before,
                detail="installed provenance remains inspectable" if before["installed"] else None,
            )
        elif kind == "package":
            item = plan_package(dependency, platform)
        elif adapter in CODING_ADAPTERS:
            item = plan_coding_tool(dependency, resolved)
        elif adapter == "macos-application":
            item = plan_macos_application(dependency, platform)
        elif kind == "access-provider":
            item = plan_provider(dependency, machine, platform)
        else:
            item = plan_lifecycle_owned(dependency)
        planned.append(item)

    if mode == "apply" and any(not item["ready"] for item in planned):
        blocked = [item["id"] for item in planned if not item["ready"]]
        raise FleetUpdateError("immutable update plan has blockers: " + ", ".join(blocked))

    results: list[dict[str, Any]] = []
    for item in planned:
        if mode != "apply" or item["status"] != "planned":
            if mode == "verify" and item["status"] == "planned":
                item["status"] = "verified-installed"
                item["ready"] = True
                item["command"] = None
            results.append(item)
            continue
        action = item.get("action")
        command = item.get("command")
        dependency = next(value for value in selected_dependencies(payload) if value["id"] == item["id"])
        if isinstance(action, dict) and action.get("kind") == "t3-dmg":
            asset = action.get("asset")
            if not isinstance(asset, dict) or not all(
                isinstance(asset.get(key), str) for key in ("name", "url", "sha256")
            ):
                raise FleetUpdateError("planned T3 native action is invalid")
            install_native_t3(dependency["contract"], str(action.get("version") or ""), asset)
            item["after"] = coding_state(dependency)
            item.update(status="updated", ready=True, command=None, action=None, detail="accepted after update")
            results.append(item)
            continue
        if not isinstance(command, list):
            raise FleetUpdateError(f"planned dependency has no command: {item['id']}")
        process = run([str(value) for value in command])
        if process.returncode != 0:
            detail = (process.stderr or process.stdout).strip().splitlines()
            item.update(status="failed", ready=False, detail=detail[-1][:500] if detail else "update command failed", command=None)
            results.append(item)
            continue
        item["after"] = coding_state(dependency) if dependency["contract"]["adapter"] in CODING_ADAPTERS else (
            macos_application_state(dependency["contract"])
            if dependency["contract"]["adapter"] == "macos-application"
            else verify_from_contract(dependency)
        )
        if dependency["contract"]["adapter"] == "t3-code":
            exact = str(payload.get("resolved", {}).get("t3-code") or "")
            evidence = "\n".join(
                value
                for value in (
                    process.stdout,
                    process.stderr,
                    str(item["after"].get("version") or "") if isinstance(item.get("after"), dict) else "",
                )
                if value
            )
            if exact not in evidence:
                item.update(status="failed", ready=False, command=None, detail=f"T3 did not verify exact version {exact}")
                results.append(item)
                continue
        item.update(status="updated", ready=True, command=None, detail="accepted after update")
        results.append(item)

    ready = all(item["ready"] for item in results)
    report = {
        "schema_version": 1,
        "machine_id": machine["id"],
        "platform": platform,
        "mode": mode,
        "resolved": resolved,
        "ready": ready,
        "can_apply": all(item["ready"] for item in planned),
        "results": results,
    }
    if mode == "apply" and ready:
        report["verified_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        atomic_write(Path.home() / ".agents/state/updates.lock.json", report)
    return report


def main() -> int:
    try:
        report = reconcile(json.load(sys.stdin))
        json.dump({"ok": True, **report}, sys.stdout)
        sys.stdout.write("\n")
        return 0 if report["ready"] or report["mode"] == "dry-run" else 2
    except (FleetUpdateError, OSError, ValueError, json.JSONDecodeError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
