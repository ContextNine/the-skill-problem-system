#!/usr/bin/env python3
"""Reconcile approved agent dependencies using a self-contained JSON payload."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform as host_platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any
from urllib.request import urlopen


SUPPORTED_MANAGERS = {
    "apt",
    "brew",
    "brew-cask",
    "ctx9-component",
    "github-archive",
    "github-python-installer",
    "node-archive",
    "npm",
    "uv-tool",
}
SUPPORTED_KINDS = {
    "package",
    "coding-tool",
    "desktop-application",
    "access-provider",
    "system-capability",
    "workspace-command",
    "optional-service",
}
SUPPORTED_ADAPTERS = {
    "package",
    "codex",
    "t3-code",
    "claude-code",
    "opencode",
    "macos-application",
    "wireguard",
    "tailscale",
    "linux-user-service",
    "homebrew",
    "xcode-command-line-tools",
    "operating-system",
    "onboarding-package",
    "official-installer",
    "machine-image",
    "workspace-command",
    "skill-managed",
}
PACKAGE_STATE = Path(".agents/.vault-agent-package.json")
PACKAGE_ROOT = Path(".agents/package")


class DependencyError(RuntimeError):
    pass


def platform_name() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    raise DependencyError(f"unsupported platform: {sys.platform}")


def architecture_name() -> str:
    value = host_platform.machine().lower()
    aliases = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}
    return aliases.get(value, value)


def environment() -> dict[str, str]:
    home = Path.home()
    candidates = [
        home / ".local/bin",
        home / ".bun/bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/bin"),
        Path("/usr/sbin"),
        Path("/sbin"),
    ]
    env = dict(os.environ)
    env["PATH"] = ":".join(str(path) for path in candidates)
    return env


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        env=environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_macos_gui(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a protected installer in the logged-in macOS GUI domain."""
    state_root = Path.home() / ".local/state/ctx9-agent-dependency-jobs"
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    label = f"com.ctx9.agent-dependency.{os.getpid()}.{time.time_ns()}"
    launch_service = f"gui/{os.getuid()}/{label}"
    with tempfile.TemporaryDirectory(prefix="job-", dir=state_root) as directory_name:
        directory = Path(directory_name)
        directory.chmod(0o700)
        stdout_path = directory / "stdout"
        stderr_path = directory / "stderr"
        for path in (stdout_path, stderr_path):
            path.touch(mode=0o600)
            path.chmod(0o600)
        launch = subprocess.run(
            [
                "launchctl",
                "submit",
                "-l",
                label,
                "-o",
                str(stdout_path),
                "-e",
                str(stderr_path),
                "--",
                "/usr/bin/env",
                f"PATH={environment()['PATH']}",
                *command,
            ],
            env=environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if launch.returncode != 0:
            return subprocess.CompletedProcess(command, launch.returncode, launch.stdout, launch.stderr)
        try:
            deadline = time.monotonic() + 1800
            returncode: int | None = None
            while time.monotonic() < deadline:
                status = subprocess.run(
                    ["launchctl", "print", launch_service],
                    env=environment(),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if status.returncode != 0:
                    break
                match = re.search(r"\blast exit code = (-?\d+)", status.stdout)
                if match:
                    returncode = int(match.group(1))
                    break
                time.sleep(0.2)
            else:
                returncode = 124
            return subprocess.CompletedProcess(
                command,
                returncode if returncode is not None else 1,
                stdout_path.read_text(encoding="utf-8", errors="replace"),
                stderr_path.read_text(encoding="utf-8", errors="replace"),
            )
        finally:
            subprocess.run(
                ["launchctl", "remove", label],
                env=environment(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


def validate_reference_files(value: object) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise DependencyError("agent reference package must be an object")
    files: dict[str, dict[str, str]] = {}
    for raw_path, raw in value.items():
        path = PurePosixPath(str(raw_path))
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise DependencyError(f"unsafe agent reference path: {raw_path!r}")
        if not isinstance(raw, dict) or not isinstance(raw.get("content"), str):
            raise DependencyError(f"agent reference file needs text content: {raw_path}")
        content = raw["content"]
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if raw.get("sha256") != digest:
            raise DependencyError(f"agent reference digest mismatch: {raw_path}")
        files[path.as_posix()] = {"content": content, "sha256": digest}
    return files


def load_reference_state(home: Path) -> dict[str, str]:
    path = home / PACKAGE_STATE
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyError(f"agent reference package state is invalid: {exc}") from exc
    if value.get("schema_version") != 1 or not isinstance(value.get("files"), dict):
        raise DependencyError("agent reference package state has an unsupported schema")
    return {str(key): str(digest) for key, digest in value["files"].items()}


def inspect_reference_files(home: Path, files: dict[str, dict[str, str]]) -> dict[str, Any]:
    prior = load_reference_state(home)
    changes: list[dict[str, str]] = []
    collisions: list[str] = []
    for relative, entry in files.items():
        target = home / PACKAGE_ROOT / relative
        if target.is_symlink() or (target.exists() and not target.is_file()):
            collisions.append(str(target))
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        if actual == entry["sha256"]:
            continue
        if actual is not None and relative not in prior:
            collisions.append(str(target))
            continue
        changes.append({"path": str(target), "status": "different" if actual else "missing"})
    for relative in sorted(set(prior) - set(files)):
        target = home / PACKAGE_ROOT / relative
        if target.exists() or target.is_symlink():
            changes.append({"path": str(target), "status": "stale"})
    return {"ready": not changes and not collisions, "changes": changes, "collisions": collisions}


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_reference_files(home: Path, files: dict[str, dict[str, str]]) -> None:
    prior = load_reference_state(home)
    for relative, entry in files.items():
        atomic_write_text(home / PACKAGE_ROOT / relative, entry["content"])
    for relative in sorted(set(prior) - set(files), reverse=True):
        target = home / PACKAGE_ROOT / relative
        if target.is_symlink() or target.is_file():
            target.unlink(missing_ok=True)
    atomic_write(
        home / PACKAGE_STATE,
        {
            "schema_version": 1,
            "managed_by": "ctx9-agents sync",
            "files": {relative: entry["sha256"] for relative, entry in sorted(files.items())},
        },
    )


def validate_manifest(
    value: dict[str, Any],
    machine: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if value.get("schema_version") != 2 or not isinstance(value.get("dependencies"), list):
        raise DependencyError("registry needs schema_version 2 and a dependencies list")
    dependencies = value["dependencies"]
    ids: set[str] = set()
    packages: list[dict[str, Any]] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(dependency.get("id"), str):
            raise DependencyError("every dependency needs a string id")
        package_id = dependency["id"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", package_id):
            raise DependencyError(f"unsafe dependency id: {package_id}")
        if package_id in ids:
            raise DependencyError(f"duplicate dependency id: {package_id}")
        ids.add(package_id)
        kind = dependency.get("kind")
        platforms = dependency.get("platforms")
        groups = dependency.get("groups")
        required_by = dependency.get("required_by")
        lifecycle_doc = dependency.get("lifecycle_doc")
        contract = dependency.get("contract")
        eligibility = dependency.get("eligibility")
        if kind not in SUPPORTED_KINDS:
            raise DependencyError(f"dependency {package_id} has unsupported kind {kind}")
        if not isinstance(platforms, list) or not platforms or not all(
            item in {"macos", "linux"} for item in platforms
        ):
            raise DependencyError(f"dependency {package_id} needs supported platforms")
        if not isinstance(groups, list) or not all(isinstance(item, str) and item for item in groups):
            raise DependencyError(f"dependency {package_id} needs groups")
        if not isinstance(required_by, list) or not all(isinstance(item, str) and item for item in required_by):
            raise DependencyError(f"dependency {package_id} needs required_by routes")
        if not isinstance(lifecycle_doc, str) or not lifecycle_doc.startswith("dependency-references/") or ".." in PurePosixPath(lifecycle_doc).parts:
            raise DependencyError(f"dependency {package_id} needs a safe lifecycle_doc")
        if not isinstance(contract, dict) or contract.get("adapter") not in SUPPORTED_ADAPTERS:
            raise DependencyError(f"dependency {package_id} has an unsupported adapter")
        if eligibility not in {
            "enabled-agent-machines",
            "remote-vault-clients",
            "linux-workers",
            "macos-machines",
            "primary-machine",
            "capability-selected",
            "provider-selected",
        }:
            raise DependencyError(f"dependency {package_id} has unsupported eligibility {eligibility!r}")
        requires = dependency.get("requires", [])
        if not isinstance(requires, list) or not all(isinstance(item, str) for item in requires):
            raise DependencyError(f"dependency {package_id} has invalid requirements")
        if kind != "package":
            continue
        if contract.get("adapter") != "package":
            raise DependencyError(f"package {package_id} must use the package adapter")
        recipes = contract.get("recipes")
        verify = contract.get("verify")
        if not isinstance(recipes, dict) or set(recipes) != set(platforms):
            raise DependencyError(f"package {package_id} needs one recipe per platform")
        if not isinstance(verify, dict) or not isinstance(verify.get("command"), str):
            raise DependencyError(f"package {package_id} needs structured verification")
        if not isinstance(verify.get("args", []), list) or not all(
            isinstance(argument, str) for argument in verify.get("args", [])
        ):
            raise DependencyError(f"package {package_id} has invalid verification arguments")
        for platform, recipe in recipes.items():
            if platform not in {"macos", "linux"} or not isinstance(recipe, dict):
                raise DependencyError(f"package {package_id} has unsupported platform {platform}")
            manager = recipe.get("manager")
            if manager not in SUPPORTED_MANAGERS:
                raise DependencyError(f"package {package_id} uses unsupported manager {manager}")
            if manager in {"apt", "brew", "brew-cask", "ctx9-component", "npm", "uv-tool"}:
                package_name = recipe.get("package")
                if (
                    not isinstance(package_name, str)
                    or not package_name
                    or package_name.startswith("-")
                    or any(character.isspace() for character in package_name)
                ):
                    raise DependencyError(f"package {package_id} has an unsafe package name")
            if manager == "ctx9-component":
                private_catalog_url = recipe.get("private_catalog_url")
                credential_binding = recipe.get("credential_binding")
                private_fields = private_catalog_url is not None or credential_binding is not None
                if private_fields and (
                    not isinstance(private_catalog_url, str)
                    or not re.fullmatch(
                        r"https://gitlab\.com/api/v4/projects/[0-9]+/packages/generic/[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+/components\.json",
                        private_catalog_url,
                    )
                    or credential_binding != "ctx9-gitlab-group-read"
                ):
                    raise DependencyError(
                        f"package {package_id} needs an exact credential-free private catalog"
                    )
            if manager in {"node-archive", "github-archive"}:
                version = recipe.get("version")
                archives = recipe.get("archives")
                if not isinstance(version, str) or not version or not isinstance(archives, dict) or not archives:
                    raise DependencyError(f"package {package_id} has an invalid archive recipe")
                for architecture, archive in archives.items():
                    if architecture not in {"x64", "arm64"} or not isinstance(archive, dict):
                        raise DependencyError(f"package {package_id} has unsupported archive architecture")
                    url = archive.get("url")
                    checksum = archive.get("sha256")
                    official = (
                        isinstance(url, str)
                        and (
                            url.startswith("https://nodejs.org/dist/")
                            if manager == "node-archive"
                            else url.startswith("https://github.com/") and "/releases/download/" in url
                        )
                    )
                    if not official or not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
                        raise DependencyError(f"package {package_id} needs official checksummed archives")
                if manager == "github-archive":
                    binaries_by_arch = recipe.get("binaries_by_arch")
                    if not isinstance(binaries_by_arch, dict) or set(binaries_by_arch) != set(archives):
                        raise DependencyError(f"package {package_id} needs binary mappings for every archive")
                    for binaries in binaries_by_arch.values():
                        if not isinstance(binaries, dict) or not binaries:
                            raise DependencyError(f"package {package_id} has invalid binary mappings")
                        for command, relative in binaries.items():
                            path = PurePosixPath(str(relative))
                            if (
                                not isinstance(command, str)
                                or not command
                                or "/" in command
                                or path.is_absolute()
                                or ".." in path.parts
                            ):
                                raise DependencyError(f"package {package_id} has an unsafe binary mapping")
            if manager == "github-python-installer":
                version = recipe.get("version")
                archive = recipe.get("archive")
                archive_root = PurePosixPath(str(recipe.get("archive_root") or ""))
                installer = PurePosixPath(str(recipe.get("installer") or ""))
                arguments = recipe.get("arguments", [])
                if not isinstance(version, str) or not version or not isinstance(archive, dict):
                    raise DependencyError(f"package {package_id} has an invalid Python installer recipe")
                url = archive.get("url")
                checksum = archive.get("sha256")
                if (
                    not isinstance(url, str)
                    or not url.startswith("https://github.com/")
                    or "/releases/download/" not in url
                    or not isinstance(checksum, str)
                    or not re.fullmatch(r"[a-f0-9]{64}", checksum)
                    or archive_root.is_absolute()
                    or not archive_root.parts
                    or ".." in archive_root.parts
                    or installer.is_absolute()
                    or not installer.parts
                    or ".." in installer.parts
                    or not isinstance(arguments, list)
                    or not all(isinstance(argument, str) for argument in arguments)
                ):
                    raise DependencyError(f"package {package_id} needs a safe checksummed Python installer")
        remote_vault_client = bool(
            machine
            and machine.get("enabled")
            and isinstance(machine.get("vault"), dict)
            and machine["vault"].get("enabled")
            and machine["vault"].get("checkout_mode") == "remote-sshfs"
        )
        active_eligibility = eligibility == "enabled-agent-machines" or (
            eligibility == "remote-vault-clients" and remote_vault_client
        )
        if contract.get("install_policy") == "required" and active_eligibility:
            packages.append(
                {
                    "id": package_id,
                    "platforms": recipes,
                    "verify": verify,
                    "requires": requires,
                }
            )
    for dependency in dependencies:
        missing = set(dependency.get("requires", [])) - ids
        if missing:
            raise DependencyError(f"dependency {dependency['id']} references unknown requirements: {sorted(missing)}")
    package_ids = {package["id"] for package in packages}
    for package in packages:
        missing = set(package.get("requires", [])) - package_ids
        if missing:
            raise DependencyError(f"package {package['id']} requires inactive packages: {sorted(missing)}")
    return packages


def ordered_packages(packages: list[dict[str, Any]], platform: str) -> list[dict[str, Any]]:
    eligible = {package["id"]: package for package in packages if platform in package["platforms"]}
    ordered: list[dict[str, Any]] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(package_id: str) -> None:
        if package_id in visited:
            return
        if package_id in visiting:
            raise DependencyError(f"dependency cycle includes {package_id}")
        visiting.add(package_id)
        package = eligible[package_id]
        for requirement in package.get("requires", []):
            if requirement not in eligible:
                raise DependencyError(f"{package_id} requires unavailable {requirement} on {platform}")
            visit(requirement)
        visiting.remove(package_id)
        visited.add(package_id)
        ordered.append(package)

    for package_id in eligible:
        visit(package_id)
    return ordered


def numeric_version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+){1,3})", text)
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def archive_legacy_command(link: Path, package_id: str, *, allow_node_modules: bool = False) -> str | None:
    """Remove only recognized pre-manifest shims after recording exact recovery metadata."""
    if not link.is_symlink():
        return None
    target = link.resolve(strict=False)
    legacy_root = (Path.home() / ".local/lib").resolve()
    try:
        relative = target.relative_to(legacy_root)
    except ValueError:
        return None
    first = relative.parts[0] if relative.parts else ""
    if not first.startswith("node-v") and not (allow_node_modules and first == "node_modules"):
        return None
    symlink_target = os.readlink(link)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = Path.home() / ".agents/state/backups/dependencies" / f"{timestamp}-{package_id}-{link.name}.json"
    atomic_write(
        backup,
        {
            "schema_version": 1,
            "package_id": package_id,
            "original_path": str(link),
            "symlink_target": symlink_target,
            "resolved_target": str(target),
        },
    )
    link.unlink()
    return symlink_target


def verify_package(package: dict[str, Any]) -> dict[str, Any]:
    verify = package["verify"]
    command = shutil.which(str(verify["command"]), path=environment()["PATH"])
    if command is None:
        return {"id": package["id"], "ready": False, "detail": f"{verify['command']} is missing"}
    if verify.get("exists_only") is True:
        return {"id": package["id"], "ready": True, "command": command, "version": None, "detail": "verified"}
    process = run([command, *[str(arg) for arg in verify.get("args", [])]])
    output = (process.stdout or process.stderr).strip()
    ready = process.returncode == 0
    detail = "verified" if ready else (output.splitlines()[-1][:500] if output else "verification failed")
    version = numeric_version(output)
    minimum = verify.get("minimum")
    maximum_exclusive = verify.get("maximum_exclusive")
    if ready and minimum:
        minimum_tuple = tuple(int(part) for part in str(minimum).split("."))
        ready = version is not None and version >= minimum_tuple
        if not ready:
            detail = f"version is below {minimum}"
    if ready and maximum_exclusive:
        maximum_tuple = tuple(int(part) for part in str(maximum_exclusive).split("."))
        ready = version is not None and version < maximum_tuple
        if not ready:
            detail = f"version is not below {maximum_exclusive}"
    exact = verify.get("exact")
    if ready and exact:
        exact_tuple = tuple(int(part) for part in str(exact).split("."))
        ready = version == exact_tuple
        if not ready:
            detail = f"version does not equal {exact}"
    return {
        "id": package["id"],
        "ready": ready,
        "command": command,
        "version": ".".join(str(part) for part in version) if version else output.splitlines()[0][:500] if output else None,
        "detail": detail,
    }


def install_node_archive(recipe: dict[str, Any]) -> None:
    archive = recipe.get("archives", {}).get(architecture_name())
    if not isinstance(archive, dict):
        raise DependencyError(f"no Node archive for architecture {architecture_name()}")
    url = str(archive.get("url") or "")
    expected = str(archive.get("sha256") or "")
    version = str(recipe.get("version") or "")
    if not url.startswith("https://nodejs.org/dist/") or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise DependencyError("Node archive needs an official URL and SHA-256")
    install_root = Path.home() / ".local/share/agents/tools/node" / version
    if not install_root.is_dir():
        install_root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".agent-node-", dir=install_root.parent) as temporary_name:
            temporary = Path(temporary_name)
            archive_path = temporary / "node.tar.xz"
            with urlopen(url) as response, archive_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            if digest != expected:
                raise DependencyError(f"Node archive checksum mismatch: expected {expected}, got {digest}")
            with tarfile.open(archive_path, "r:xz") as handle:
                members = handle.getmembers()
                prefix = Path(members[0].name).parts[0] if members else ""
                if not prefix or any(member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
                    raise DependencyError("unsafe Node archive")
                handle.extractall(temporary / "extract")
            source = temporary / "extract" / prefix
            source.replace(install_root)
    bin_directory = Path.home() / ".local/bin"
    bin_directory.mkdir(parents=True, exist_ok=True)
    for command in ("node", "npm", "npx", "corepack"):
        target = install_root / "bin" / command
        link = bin_directory / command
        if not target.exists():
            raise DependencyError(f"Node archive is missing {command}")
        if link.is_symlink() or link.exists():
            if link.is_symlink() and link.resolve() == target.resolve():
                continue
            managed_root = (Path.home() / ".local/share/agents/tools/node").resolve()
            if not archive_legacy_command(link, "node24") and (
                not link.is_symlink() or managed_root not in link.resolve().parents
            ):
                raise DependencyError(f"refusing to replace unmanaged command: {link}")
            if link.is_symlink():
                link.unlink()
        link.symlink_to(target)


def install_github_archive(package: dict[str, Any], recipe: dict[str, Any]) -> None:
    archive = recipe.get("archives", {}).get(architecture_name())
    if not isinstance(archive, dict):
        raise DependencyError(f"no {package['id']} archive for architecture {architecture_name()}")
    url = str(archive.get("url") or "")
    expected = str(archive.get("sha256") or "")
    version = str(recipe.get("version") or "")
    if not url.startswith("https://github.com/") or "/releases/download/" not in url or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise DependencyError("GitHub archive needs a release URL and SHA-256")
    install_root = Path.home() / ".local/share/agents/tools" / str(package["id"]) / version
    if not install_root.is_dir():
        install_root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".agent-{package['id']}-", dir=install_root.parent
        ) as temporary_name:
            temporary = Path(temporary_name)
            archive_path = temporary / "archive.tar.gz"
            with urlopen(url) as response, archive_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            if digest != expected:
                raise DependencyError(f"{package['id']} archive checksum mismatch")
            extract = temporary / "extract"
            with tarfile.open(archive_path, "r:gz") as handle:
                members = handle.getmembers()
                if any(member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
                    raise DependencyError(f"unsafe {package['id']} archive")
                handle.extractall(extract)
            extract.replace(install_root)
    binaries = recipe.get("binaries_by_arch", {}).get(architecture_name(), recipe.get("binaries"))
    if not isinstance(binaries, dict) or not binaries:
        raise DependencyError(f"{package['id']} archive needs binary mappings")
    bin_directory = Path.home() / ".local/bin"
    bin_directory.mkdir(parents=True, exist_ok=True)
    for command, relative in binaries.items():
        candidate = PurePosixPath(str(relative))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise DependencyError(f"unsafe {package['id']} binary path")
        target = install_root.joinpath(*candidate.parts)
        link = bin_directory / str(command)
        if not target.is_file():
            raise DependencyError(f"{package['id']} archive is missing {relative}")
        if link.is_symlink() or link.exists():
            if link.is_symlink() and link.resolve() == target.resolve():
                continue
            managed_root = (Path.home() / ".local/share/agents/tools" / str(package["id"])).resolve()
            if not link.is_symlink() or managed_root not in link.resolve().parents:
                raise DependencyError(f"refusing to replace unmanaged command: {link}")
            link.unlink()
        link.symlink_to(target)


def install_github_python_installer(package: dict[str, Any], recipe: dict[str, Any]) -> None:
    archive = recipe.get("archive")
    if not isinstance(archive, dict):
        raise DependencyError(f"{package['id']} has no release archive")
    url = str(archive.get("url") or "")
    expected = str(archive.get("sha256") or "")
    if (
        not url.startswith("https://github.com/")
        or "/releases/download/" not in url
        or not re.fullmatch(r"[a-f0-9]{64}", expected)
    ):
        raise DependencyError("GitHub Python installer needs a release URL and SHA-256")
    with tempfile.TemporaryDirectory(prefix=f".agent-{package['id']}-") as temporary_name:
        temporary = Path(temporary_name)
        archive_path = temporary / "archive.tar.gz"
        with urlopen(url) as response, archive_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        if hashlib.sha256(archive_path.read_bytes()).hexdigest() != expected:
            raise DependencyError(f"{package['id']} archive checksum mismatch")
        extract = temporary / "extract"
        with tarfile.open(archive_path, "r:gz") as handle:
            members = handle.getmembers()
            if any(
                member.name.startswith("/")
                or ".." in Path(member.name).parts
                or member.issym()
                or member.islnk()
                for member in members
            ):
                raise DependencyError(f"unsafe {package['id']} archive")
            handle.extractall(extract)
        archive_root = PurePosixPath(str(recipe.get("archive_root") or ""))
        installer_relative = PurePosixPath(str(recipe.get("installer") or ""))
        installer = extract.joinpath(*archive_root.parts, *installer_relative.parts)
        if not installer.is_file():
            raise DependencyError(f"{package['id']} archive is missing {installer_relative}")
        python = shutil.which("python3", path=environment()["PATH"])
        if python is None:
            raise DependencyError(f"python3 is missing for {package['id']}")
        process = run([python, str(installer), *[str(item) for item in recipe.get("arguments", [])], "--json"])
        if process.returncode != 0:
            output = (process.stderr or process.stdout).strip().splitlines()
            raise DependencyError(
                f"install failed for {package['id']}: {output[-1][:500] if output else 'command failed'}"
            )
        try:
            report = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise DependencyError(f"{package['id']} installer returned invalid JSON") from exc
        if not isinstance(report, dict) or report.get("ready") is not True:
            raise DependencyError(f"{package['id']} installer did not report ready")


def install_package(package: dict[str, Any], recipe: dict[str, Any]) -> None:
    manager = recipe["manager"]
    if manager == "node-archive":
        install_node_archive(recipe)
        return
    if manager == "github-archive":
        install_github_archive(package, recipe)
        return
    if manager == "github-python-installer":
        install_github_python_installer(package, recipe)
        return
    name = str(recipe.get("package") or "")
    if not name:
        raise DependencyError(f"{package['id']} has no package name")
    if manager == "ctx9-component":
        executable = shutil.which("ctx9", path=environment()["PATH"])
        if executable is None:
            raise DependencyError(f"ctx9 is missing for {package['id']}")
        private_catalog_url = recipe.get("private_catalog_url")
        if private_catalog_url:
            helper = shutil.which("ctx9-gitlab-read", path=environment()["PATH"])
            if helper is None:
                raise DependencyError(f"ctx9-gitlab-read is missing for {package['id']}")
            command = [
                helper,
                "exec",
                "--",
                executable,
                "--private-catalog-url",
                str(private_catalog_url),
                "--credential-binding",
                str(recipe["credential_binding"]),
                "install",
                name,
                "--json",
            ]
        else:
            command = [executable, "install", name, "--json"]
        process = (
            run_macos_gui(command)
            if platform_name() == "macos" and os.environ.get("SSH_CONNECTION")
            else run(command)
        )
        if process.returncode != 0:
            output = (process.stderr or process.stdout).strip().splitlines()
            raise DependencyError(
                f"install failed for {package['id']}: {output[-1][:500] if output else 'command failed'}"
            )
        try:
            report = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise DependencyError(f"{package['id']} installer returned invalid JSON") from exc
        if not isinstance(report, list) or not report or not all(
            isinstance(item, dict) and item.get("ready") is True for item in report
        ):
            raise DependencyError(f"{package['id']} installer did not report ready")
        return
    if manager == "brew":
        installed = run(["brew", "list", "--versions", name]).returncode == 0
        command = ["brew", "upgrade" if installed else "install", name]
    elif manager == "brew-cask":
        installed = run(["brew", "list", "--cask", "--versions", name]).returncode == 0
        command = ["brew", "upgrade" if installed else "install", "--cask", name]
    elif manager == "apt":
        command = ["sudo", "-n", "apt-get", "install", "-y", "--no-install-recommends", name]
    elif manager == "npm":
        command = ["npm", "install", "--global", "--prefix", str(Path.home() / ".local"), name]
    elif manager == "uv-tool":
        command = ["uv", "tool", "install", "--force", name]
    else:
        raise DependencyError(f"unsupported manager: {manager}")
    executable = shutil.which(command[0], path=environment()["PATH"])
    if executable is None:
        raise DependencyError(f"package manager is missing for {package['id']}: {command[0]}")
    command_link = Path.home() / ".local/bin" / str(package["verify"]["command"])
    archived_target = (
        archive_legacy_command(command_link, str(package["id"]), allow_node_modules=True)
        if manager == "npm"
        else None
    )
    process = run([executable, *command[1:]])
    if process.returncode != 0:
        if archived_target is not None and not command_link.exists() and not command_link.is_symlink():
            command_link.symlink_to(archived_target)
        output = (process.stderr or process.stdout).strip().splitlines()
        raise DependencyError(f"install failed for {package['id']}: {output[-1][:500] if output else 'command failed'}")
    if manager == "brew" and recipe.get("link") is True:
        linked = run([executable, "link", "--overwrite", "--force", name])
        if linked.returncode != 0:
            output = (linked.stderr or linked.stdout).strip().splitlines()
            raise DependencyError(f"link failed for {package['id']}: {output[-1][:500] if output else 'command failed'}")
    if manager in {"brew", "brew-cask"}:
        archive_legacy_command(command_link, str(package["id"]), allow_node_modules=True)


def install_preflight(package: dict[str, Any], recipe: dict[str, Any], eligible_ids: set[str]) -> tuple[bool, str]:
    manager = recipe["manager"]
    if manager in {"node-archive", "github-archive"}:
        archive = recipe.get("archives", {}).get(architecture_name())
        return (isinstance(archive, dict), f"official archive for {architecture_name()}")
    if manager == "github-python-installer":
        return (
            shutil.which("python3", path=environment()["PATH"]) is not None or "python" in eligible_ids,
            "checksummed GitHub Python installer",
        )
    if manager == "ctx9-component":
        launcher_available = (
            shutil.which("ctx9", path=environment()["PATH"]) is not None
            or "ctx9-launcher" in eligible_ids
        )
        if recipe.get("private_catalog_url"):
            helper_available = shutil.which("ctx9-gitlab-read", path=environment()["PATH"]) is not None
            available = launcher_available and helper_available
            return (
                available,
                "authenticated ctx9 private catalog"
                if available
                else "ctx9 launcher or narrow GitLab reader is missing",
            )
        return launcher_available, "ctx9 component catalog" if launcher_available else "ctx9 launcher is missing"
    if manager in {"brew", "brew-cask"}:
        return (shutil.which("brew", path=environment()["PATH"]) is not None, "Homebrew")
    if manager == "apt":
        if shutil.which("apt-get", path=environment()["PATH"]) is None:
            return False, "apt-get is missing"
        sudo = shutil.which("sudo", path=environment()["PATH"])
        if sudo is None:
            return False, "sudo is missing"
        protected = run([sudo, "-n", "true"])
        return (protected.returncode == 0, "noninteractive sudo" if protected.returncode == 0 else "sudo needs a protected prompt")
    if manager == "npm":
        available = shutil.which("npm", path=environment()["PATH"]) is not None or "node24" in eligible_ids
        return available, "npm supplied by node24" if available else "npm is missing"
    if manager == "uv-tool":
        available = shutil.which("uv", path=environment()["PATH"]) is not None or "uv" in eligible_ids
        return available, "uv direct dependency" if available else "uv is missing"
    return False, f"unsupported manager {manager}"


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
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict):
        raise DependencyError("payload has no manifest")
    platform = platform_name()
    machine = payload.get("machine")
    if machine is not None and not isinstance(machine, dict):
        raise DependencyError("payload machine must be an object")
    packages = ordered_packages(validate_manifest(manifest, machine), platform)
    reference_selected = "reference_files" in payload
    reference_files = validate_reference_files(payload.get("reference_files")) if reference_selected else {}
    reference_state = (
        inspect_reference_files(Path.home(), reference_files)
        if reference_selected
        else {"ready": True, "changes": [], "collisions": []}
    )
    mode = str(payload.get("mode") or "dry-run")
    if mode not in {"apply", "dry-run", "verify"}:
        raise DependencyError(f"unsupported mode: {mode}")
    before = [verify_package(package) for package in packages]
    eligible_ids = {str(package["id"]) for package in packages}
    preflight = []
    for package, state in zip(packages, before, strict=True):
        installable, detail = (True, "already verified") if state["ready"] else install_preflight(
            package, package["platforms"][platform], eligible_ids
        )
        preflight.append({"id": package["id"], "installable": installable, "detail": detail})
    can_apply = all(item["installable"] for item in preflight) and not reference_state["collisions"]
    if mode == "apply":
        if not can_apply:
            blocked = [str(item["id"]) for item in preflight if not item["installable"]]
            raise DependencyError("dependency preflight failed: " + ", ".join(blocked))
        for package, state in zip(packages, before, strict=True):
            if not state["ready"]:
                install_package(package, package["platforms"][platform])
    after = [verify_package(package) for package in packages] if mode == "apply" else before
    if mode == "apply" and reference_selected:
        apply_reference_files(Path.home(), reference_files)
        reference_state = inspect_reference_files(Path.home(), reference_files)
    ready = all(item["ready"] for item in after) and reference_state["ready"]
    report = {
        "schema_version": 1,
        "machine_id": str(payload.get("machine_id") or "unknown"),
        "platform": platform,
        "architecture": architecture_name(),
        "mode": mode,
        "ready": ready,
        "can_apply": can_apply,
        "preflight": preflight,
        "packages": after,
        "reference_package": {
            "ready": reference_state["ready"],
            "file_count": len(reference_files),
            "changes": reference_state["changes"],
            "collisions": reference_state["collisions"],
        },
    }
    if mode == "apply" and ready:
        report["verified_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        atomic_write(Path.home() / ".agents/state/dependencies.lock.json", report)
    return report


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        report = reconcile(payload)
        json.dump({"ok": True, **report}, sys.stdout)
        sys.stdout.write("\n")
        return 0 if report["ready"] or report["mode"] == "dry-run" else 2
    except (DependencyError, OSError, ValueError, json.JSONDecodeError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
