#!/usr/bin/env python3
"""Apply approved workspace-built commands without a Vault checkout."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any


class WorkspaceDependencyError(RuntimeError):
    pass


def run_environment() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = ":".join(
        [
            str(Path.home() / ".local/bin"),
            str(Path.home() / ".bun/bin"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
        ]
    )
    return env


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=run_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_macos_gui(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a remote-Mac installer where its login Keychain is available."""
    state_root = Path.home() / ".local/state/ctx9-workspace-dependency-jobs"
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    label = f"com.ctx9.workspace-dependency.{os.getpid()}.{time.time_ns()}"
    launch_service = f"gui/{os.getuid()}/{label}"
    with tempfile.TemporaryDirectory(prefix="job-", dir=state_root) as directory_name:
        directory = Path(directory_name)
        directory.chmod(0o700)
        stdout_path = directory / "stdout"
        stderr_path = directory / "stderr"
        for path in (stdout_path, stderr_path):
            path.touch(mode=0o600)
            path.chmod(0o600)
        shell = 'cd "$1" && shift && exec "$@"'
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
                "/bin/sh",
                "-c",
                shell,
                "workspace-dependency",
                str(cwd or Path.home()),
                "/usr/bin/env",
                f"PATH={run_environment()['PATH']}",
                *command,
            ],
            env=run_environment(),
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
                    env=run_environment(),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                match = re.search(r"^\s*last exit code = (-?\d+)\s*$", status.stdout, re.MULTILINE)
                if match:
                    returncode = int(match.group(1))
                    break
                time.sleep(0.2)
            if returncode is None:
                returncode = 124
            return subprocess.CompletedProcess(
                command,
                returncode,
                stdout_path.read_text(encoding="utf-8", errors="replace"),
                stderr_path.read_text(encoding="utf-8", errors="replace"),
            )
        finally:
            subprocess.run(
                ["launchctl", "remove", label],
                env=run_environment(),
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


def platform_name() -> str:
    return "macos" if sys.platform == "darwin" else "linux" if sys.platform.startswith("linux") else "unsupported"


def safe_installer(workspace: Path, relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise WorkspaceDependencyError(f"unsafe installer path: {relative}")
    installer = workspace.joinpath(*candidate.parts)
    resolved_workspace = workspace.resolve()
    resolved_installer = installer.resolve()
    if resolved_workspace not in resolved_installer.parents:
        raise WorkspaceDependencyError(f"installer escapes workspace: {relative}")
    if not installer.is_file() or installer.is_symlink() or not stat.S_ISREG(installer.stat().st_mode):
        raise WorkspaceDependencyError(f"installer is not a tracked regular file: {relative}")
    tracked = run(["git", "-C", str(workspace), "ls-files", "--error-unmatch", relative])
    if tracked.returncode != 0:
        raise WorkspaceDependencyError(f"installer is not tracked: {relative}")
    return installer


def workspace_state(workspace: Path) -> tuple[bool, str]:
    if not (workspace / ".git").exists():
        return False, "workspace is missing or is not a Git checkout"
    status = run(["git", "-C", str(workspace), "status", "--porcelain", "--untracked-files=all"])
    if status.returncode != 0:
        return False, "cannot inspect workspace"
    if status.stdout.strip():
        return False, "workspace is dirty; preserving all work"
    branch = run(["git", "-C", str(workspace), "symbolic-ref", "--quiet", "HEAD"])
    if branch.returncode != 0:
        return False, "workspace is detached"
    upstream = run(["git", "-C", str(workspace), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    if upstream.returncode != 0:
        return False, "workspace has no upstream"
    counts = run(["git", "-C", str(workspace), "rev-list", "--left-right", "--count", "HEAD...@{upstream}"])
    if counts.returncode != 0:
        return False, "cannot compare workspace upstream"
    ahead, behind = (int(value) for value in counts.stdout.split())
    if ahead or behind:
        return False, f"workspace is not aligned with upstream (ahead {ahead}, behind {behind})"
    return True, "workspace is clean and aligned"


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
    machine = payload.get("machine")
    manifest = payload.get("manifest")
    workspaces = payload.get("workspaces")
    mode = str(payload.get("mode") or "dry-run")
    if not isinstance(machine, dict) or not isinstance(manifest, dict) or not isinstance(workspaces, dict):
        raise WorkspaceDependencyError("payload needs machine, manifest, and workspaces")
    if mode not in {"apply", "dry-run", "verify"}:
        raise WorkspaceDependencyError(f"unsupported mode: {mode}")
    entries = workspaces.get("entries", {})
    if not isinstance(entries, dict):
        raise WorkspaceDependencyError("workspace catalog has no entries")
    raw_dependencies = manifest.get("workspace_dependencies")
    if manifest.get("schema_version") != 1 or not isinstance(raw_dependencies, list):
        raise WorkspaceDependencyError("workspace dependency manifest is invalid")
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for dependency in raw_dependencies:
        if not isinstance(dependency, dict) or not isinstance(dependency.get("id"), str):
            raise WorkspaceDependencyError("every workspace dependency needs an id")
        dependency_id = dependency["id"]
        if dependency_id in seen:
            raise WorkspaceDependencyError(f"duplicate workspace dependency id: {dependency_id}")
        seen.add(dependency_id)
        if platform_name() not in dependency.get("platforms", []):
            continue
        machines = dependency.get("machines", ["*"])
        if "*" not in machines and machine.get("id") not in machines:
            continue
        workspace_id = dependency.get("workspace")
        if workspace_id not in entries:
            raise WorkspaceDependencyError(f"{dependency_id} references unknown workspace {workspace_id}")
        workspace_path = PurePosixPath(str(entries[workspace_id].get("path") or ""))
        if workspace_path.is_absolute() or ".." in workspace_path.parts or workspace_path.as_posix() in {"", "."}:
            raise WorkspaceDependencyError(f"workspace {workspace_id} needs a safe Code-root-relative path")
        roots = machine.get("roots")
        raw_code_root = roots.get("code") if isinstance(roots, dict) else None
        if not isinstance(raw_code_root, str):
            raise WorkspaceDependencyError(f"machine {machine.get('id')} has no Code root")
        code_root = Path.home() / raw_code_root[2:] if raw_code_root.startswith("~/") else Path(raw_code_root)
        if not code_root.is_absolute() or ".." in code_root.parts:
            raise WorkspaceDependencyError(f"machine {machine.get('id')} has an unsafe Code root")
        workspace = code_root.joinpath(*workspace_path.parts)
        safe, detail = workspace_state(workspace)
        if not safe:
            can_reconcile = mode == "dry-run" and "dirty" not in detail and "ahead" not in detail and "detached" not in detail
            results.append({"id": dependency_id, "ready": False, "can_apply": can_reconcile, "detail": detail})
            continue
        installer = safe_installer(workspace, str(dependency.get("installer") or ""))
        commands = dependency.get("commands")
        if (
            not isinstance(commands, list)
            or not commands
            or not all(isinstance(command, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", command) for command in commands)
        ):
            raise WorkspaceDependencyError(f"{dependency_id} has invalid expected commands")
        if dependency.get("source_commit_alignment") is not True:
            raise WorkspaceDependencyError(f"{dependency_id} does not require source alignment")
        arguments = dependency.get("arguments", {}).get(mode)
        if not isinstance(arguments, list) or not all(isinstance(arg, str) for arg in arguments):
            raise WorkspaceDependencyError(f"{dependency_id} has no structured {mode} arguments")
        expanded = [arg.replace("{display_name}", str(machine.get("display_name") or machine.get("id"))) for arg in arguments]
        installer_runner = (
            run_macos_gui
            if platform_name() == "macos" and machine.get("transport") == "ssh"
            else run
        )
        process = installer_runner([str(installer), *expanded], cwd=workspace)
        output = process.stdout.strip().splitlines()
        evidence: dict[str, Any] = {}
        if output:
            try:
                parsed = json.loads(output[-1])
                if isinstance(parsed, dict):
                    evidence = parsed
            except json.JSONDecodeError:
                pass
        head = run(["git", "-C", str(workspace), "rev-parse", "HEAD"])
        expected_commit = head.stdout.strip() if head.returncode == 0 else ""
        command_paths = {
            command: shutil.which(command, path=run_environment()["PATH"])
            for command in commands
        }
        commands_ready = all(command_paths.values())
        source_ready = (
            bool(expected_commit)
            and evidence.get("source_commit") == expected_commit
            and evidence.get("expected_source_commit") == expected_commit
        )
        ready = bool(evidence.get("ready")) and commands_ready and source_ready
        if not commands_ready:
            detail = "expected commands missing from PATH: " + ", ".join(
                command for command, path in command_paths.items() if path is None
            )
        elif not source_ready:
            detail = "installer evidence does not match the workspace source commit"
        else:
            detail = "verified" if ready else (
                (process.stderr or process.stdout).strip().splitlines()[-1][:500]
                if (process.stderr or process.stdout).strip()
                else "installer verification failed"
            )
        result = {
            "id": dependency_id,
            "ready": ready,
            "can_apply": process.returncode == 0 if mode == "dry-run" else ready,
            "detail": detail,
            "commands": command_paths,
            "source_commit": expected_commit,
            "evidence": evidence,
        }
        results.append(result)
    ready = all(result["ready"] for result in results)
    can_apply = all(result["can_apply"] for result in results)
    report = {
        "schema_version": 1,
        "machine_id": str(machine.get("id")),
        "mode": mode,
        "ready": ready,
        "can_apply": can_apply,
        "dependencies": results,
    }
    if mode == "apply" and ready:
        report["verified_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        atomic_write(Path.home() / ".agents/state/workspace-dependencies.lock.json", report)
    return report


def main() -> int:
    try:
        report = reconcile(json.load(sys.stdin))
        json.dump({"ok": True, **report}, sys.stdout)
        sys.stdout.write("\n")
        return 0 if report["ready"] or report["mode"] == "dry-run" else 2
    except (WorkspaceDependencyError, OSError, ValueError, json.JSONDecodeError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
