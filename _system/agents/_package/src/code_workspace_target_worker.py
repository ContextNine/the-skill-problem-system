#!/usr/bin/env python3
"""Target-side worker for cataloged Code workspace operations."""

from __future__ import annotations

import json
import fcntl
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


PRUNED_DIRECTORIES = {
    ".cache",
    ".ctx9",
    ".workspace-sync",
    ".next",
    ".pnpm-store",
    ".terraform",
    ".turbo",
    ".venv",
    ".yarn",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
    "vendor",
}
STATE_DIRECTORY = ".workspace-sync"
LEGACY_STATE_DIRECTORY = ".ctx9/workspace-bootstrap"
RUN_RETENTION = 100
HISTORY_RETENTION = 500


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def noninteractive_git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["GIT_LFS_SKIP_SMUDGE"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"
    environment["GIT_ASKPASS"] = "/usr/bin/false"
    environment["SSH_ASKPASS"] = "/usr/bin/false"
    environment["SSH_ASKPASS_REQUIRE"] = "never"
    environment["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o StrictHostKeyChecking=yes"
    return environment


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *args], env=noninteractive_git_environment())


def output(process: subprocess.CompletedProcess[str]) -> str:
    return process.stdout.strip()


def error_text(process: subprocess.CompletedProcess[str]) -> str:
    value = (process.stderr or process.stdout).strip()
    return value.splitlines()[-1][:500] if value else "command failed"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def migrate_runtime_state(code_root: Path) -> Path:
    """Move legacy workspace-sync state into its dedicated Code-root directory."""
    state_root = code_root / STATE_DIRECTORY
    legacy_root = code_root / LEGACY_STATE_DIRECTORY
    for label, path in (("workspace sync state", state_root), ("legacy workspace sync state", legacy_root)):
        if path.is_symlink():
            raise ValueError(f"{label} cannot be a symlink: {path}")
        if path.exists() and not path.is_dir():
            raise ValueError(f"{label} is not a directory: {path}")
    if state_root.exists() and legacy_root.exists():
        raise ValueError(
            f"both workspace sync state directories exist; resolve without merging: {legacy_root}, {state_root}"
        )
    if legacy_root.exists():
        legacy_root.rename(state_root)
        try:
            legacy_root.parent.rmdir()
        except OSError:
            pass
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    return state_root


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    file_mode = 0o600
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(file_mode)
    temporary.replace(path)


def append_bounded_jsonl(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [*existing[-(HISTORY_RETENTION - 1) :], json.dumps(value, sort_keys=True)]
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def canonical_remote(url: str) -> str | None:
    value = url.strip().rstrip("/")
    if not value:
        return None
    if "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme == "file" or not parsed.hostname:
            return None
        if parsed.password is not None or (parsed.scheme in {"http", "https"} and parsed.username is not None):
            return None
        if parsed.query or parsed.fragment:
            return None
        try:
            port = parsed.port
        except ValueError:
            return None
        host = parsed.hostname.lower()
        host_identity = f"{host}:{port}" if port is not None else host
        path = parsed.path.lstrip("/")
    else:
        match = re.match(r"^(?:[^@/:]+@)?([^/:]+):(.+)$", value)
        if not match:
            return None
        host, path = match.group(1).lower(), match.group(2).lstrip("/")
        host_identity = host
    if path.endswith(".git"):
        path = path[:-4]
    return f"{host_identity}/{path}" if path else None


def choose_remote(repo: Path) -> tuple[str | None, str | None]:
    names_result = git(repo, "remote")
    if names_result.returncode != 0:
        return None, None
    names = [line for line in output(names_result).splitlines() if line]
    name = "origin" if "origin" in names else names[0] if len(names) == 1 else None
    if name is None:
        return None, None
    url_result = git(repo, "remote", "get-url", name)
    return (name, output(url_result)) if url_result.returncode == 0 else (None, None)


def configured_remote_url(repo: Path, remote_name: str) -> str | None:
    """Return the literal configured URL without applying global insteadOf rules."""
    result = git(repo, "config", "--local", "--get", f"remote.{remote_name}.url")
    return output(result) if result.returncode == 0 and output(result) else None


def recursive_repositories(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        marker = ".git" in directories or ".git" in files or (current_path / ".git").is_symlink()
        if marker:
            found.append(current_path)
            directories.clear()
            continue
        directories[:] = [
            name
            for name in directories
            if name not in PRUNED_DIRECTORIES and not (current_path / name).is_symlink()
        ]
    return found


def repository_inventory(root: Path) -> dict[str, list[Path]]:
    inventory: dict[str, list[Path]] = {}
    for repo in recursive_repositories(root):
        _, remote_url = choose_remote(repo)
        identity = canonical_remote(remote_url) if remote_url else None
        if identity:
            inventory.setdefault(identity, []).append(repo)
    return inventory


def relocation_structure_problem(repo: Path) -> str | None:
    marker = repo / ".git"
    if marker.is_file() or marker.is_symlink():
        return "matching checkout uses a .git file (linked worktree or submodule)"
    worktrees = git(repo, "worktree", "list", "--porcelain")
    if worktrees.returncode != 0:
        return f"cannot inspect Git worktrees: {error_text(worktrees)}"
    count = sum(1 for line in output(worktrees).splitlines() if line.startswith("worktree "))
    if count > 1:
        return f"matching checkout owns {count} linked Git worktrees"
    return None


def safe_destination(root: Path, relative: str) -> tuple[Path | None, str | None]:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or relative in {"", "."} or ".." in pure.parts:
        return None, "invalid repository-relative path"
    destination = root.joinpath(*pure.parts)
    probe = destination if destination.exists() else destination.parent
    while not probe.exists() and probe != root:
        probe = probe.parent
    try:
        probe.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None, "destination escapes the target Code root through a symlink"
    return destination, None


def project_path(destination: Path, source: dict[str, object]) -> tuple[Path | None, str | None]:
    project = PurePosixPath(str(source.get("codex_project_root", ".")))
    if project.is_absolute() or ".." in project.parts:
        return None, "invalid Codex project root"
    candidate = destination if project.as_posix() == "." else destination.joinpath(*project.parts)
    if not destination.exists():
        return candidate, None
    probe = candidate if candidate.exists() else candidate.parent
    while not probe.exists() and probe != destination:
        probe = probe.parent
    if probe.exists():
        try:
            probe.resolve().relative_to(destination.resolve())
        except (OSError, ValueError):
            return None, "Codex project root escapes the repository through a symlink"
    return candidate, None


def enclosing_repository(destination: Path) -> Path | None:
    probe = destination.parent
    while not probe.exists():
        probe = probe.parent
    top_level = git(probe, "rev-parse", "--show-toplevel")
    if top_level.returncode != 0 or not output(top_level):
        return None
    return Path(output(top_level)).resolve()


def inspect_repository(destination: Path, source: dict[str, object]) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    relative = str(source["relative_path"])
    base: dict[str, object] = {"path": relative}
    inside = git(destination, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or output(inside) != "true":
        return None, {**base, "status": "conflict", "detail": "existing path is not a Git working tree"}
    top_level = git(destination, "rev-parse", "--show-toplevel")
    if top_level.returncode != 0 or Path(output(top_level)).resolve() != destination.resolve():
        return None, {**base, "status": "conflict", "detail": "existing path is not the repository root"}
    remote_name, remote_url = choose_remote(destination)
    if not remote_name or not remote_url:
        return None, {**base, "status": "blocked", "detail": "target repository has no unambiguous remote"}
    if canonical_remote(remote_url) != source.get("remote_identity"):
        return None, {**base, "status": "conflict", "detail": "target remote does not match catalog remote"}
    configured_url = configured_remote_url(destination, remote_name)
    if not configured_url or canonical_remote(configured_url) != source.get("remote_identity"):
        return None, {**base, "status": "conflict", "detail": "configured target remote does not match catalog remote"}
    dirty_result = git(destination, "status", "--porcelain=v1", "--untracked-files=normal")
    if dirty_result.returncode != 0:
        return None, {**base, "status": "error", "detail": f"git status failed: {error_text(dirty_result)}"}
    branch_result = git(destination, "symbolic-ref", "--quiet", "--short", "HEAD")
    branch = output(branch_result) if branch_result.returncode == 0 else None
    upstream_result = git(destination, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    upstream = output(upstream_result) if upstream_result.returncode == 0 else None
    ahead = behind = None
    divergence_error = False
    if upstream:
        counts_result = git(destination, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if counts_result.returncode == 0:
            ahead, behind = (int(value) for value in output(counts_result).split())
        else:
            divergence_error = True
    configured_project, project_problem = project_path(destination, source)
    return (
        {
            "path": relative,
            "remote_name": remote_name,
            "configured_remote_url": configured_url,
            "transport_drift": configured_url != source.get("remote_url"),
            "dirty": bool(output(dirty_result)),
            "branch": branch,
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
            "divergence_error": divergence_error,
            "project_path": configured_project,
            "project_problem": project_problem,
            "has_agents": (destination / "AGENTS.md").is_file(),
            "has_codex": (destination / ".codex").is_dir(),
        },
        None,
    )


def reconcile_remote(destination: Path, source: dict[str, object], apply: bool) -> dict[str, object]:
    """Reconcile only same-identity remote transport, rolling back failed verification."""
    relative = str(source["relative_path"])
    if not destination.exists() and not destination.is_symlink():
        return {"path": relative, "status": "missing", "detail": "repository is not bootstrapped"}
    state, problem = inspect_repository(destination, source)
    if problem:
        return problem
    assert state is not None
    remote_name = str(state["remote_name"])
    old_url = str(state["configured_remote_url"])
    desired_url = str(source["remote_url"])
    if old_url == desired_url:
        return {"path": relative, "status": "transport-current", "detail": f"{remote_name} already uses desired transport"}
    ssh_command = git(destination, "config", "--local", "--get", "core.sshCommand")
    if ssh_command.returncode == 0 and output(ssh_command):
        return {
            "path": relative,
            "status": "blocked",
            "detail": "repo-specific core.sshCommand requires manual review before transport migration",
        }
    planned = {
        "path": relative,
        "status": "planned-remote-update",
        "detail": f"change {remote_name} transport without changing repository identity",
        "old_url": old_url,
        "new_url": desired_url,
    }
    if not apply:
        return planned
    changed = git(destination, "remote", "set-url", remote_name, desired_url)
    if changed.returncode != 0:
        return {**planned, "status": "error", "detail": f"remote update failed: {error_text(changed)}"}
    literal = configured_remote_url(destination, remote_name)
    verified = run(
        ["git", "ls-remote", "--exit-code", desired_url, "HEAD"],
        env=noninteractive_git_environment(),
    )
    if literal == desired_url and verified.returncode == 0:
        return {**planned, "status": "remote-updated", "detail": f"updated and verified {remote_name} transport"}
    rollback = git(destination, "remote", "set-url", remote_name, old_url)
    rollback_detail = "restored prior URL" if rollback.returncode == 0 else f"rollback failed: {error_text(rollback)}"
    failure = "configured URL verification failed" if literal != desired_url else f"remote access failed: {error_text(verified)}"
    return {
        **planned,
        "status": "error",
        "detail": f"{failure}; {rollback_detail}",
        "rolled_back": rollback.returncode == 0,
    }


def clone_missing(destination: Path, source: dict[str, object], apply: bool) -> dict[str, object]:
    relative = str(source["relative_path"])
    branch = source.get("clone_branch")
    clone_mode = str(source.get("clone_mode", "partial"))
    if not apply:
        branch_detail = f"branch {branch}" if branch else "remote default branch"
        return {"path": relative, "status": "planned-clone", "detail": f"{clone_mode} clone, {branch_detail}"}
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = ["git", "clone", "--origin", "origin"]
    if clone_mode == "partial":
        command.append("--filter=blob:none")
    if isinstance(branch, str) and branch:
        command.extend(["--branch", branch])
    command.extend(["--", str(source["remote_url"]), str(destination)])
    cloned = run(command, env=noninteractive_git_environment())
    if cloned.returncode != 0:
        return {"path": relative, "status": "error", "detail": f"clone failed: {error_text(cloned)}"}
    return {"path": relative, "status": "cloned", "detail": f"{clone_mode} clone completed"}


def relocate_or_clone(
    target_root: Path,
    destination: Path,
    source: dict[str, object],
    apply: bool,
    inventory: dict[str, list[Path]],
    desired_paths: set[Path],
    claimed_paths: set[Path],
    allow_dirty_relocation: bool,
) -> dict[str, object]:
    relative = str(source["relative_path"])
    remote_identity = str(source["remote_identity"])
    matches = [path for path in inventory.get(remote_identity, []) if path not in claimed_paths]
    protected = [path for path in matches if path in desired_paths]
    candidates = [path for path in matches if path not in desired_paths]
    if protected:
        paths = ", ".join(sorted(path.relative_to(target_root).as_posix() for path in protected))
        return {
            "path": relative,
            "status": "conflict",
            "detail": f"matching remote is already assigned to another desired path: {paths}",
        }
    if len(candidates) > 1:
        paths = ", ".join(sorted(path.relative_to(target_root).as_posix() for path in candidates))
        return {
            "path": relative,
            "status": "conflict",
            "detail": f"multiple existing checkouts match the remote: {paths}",
        }
    if not candidates:
        return clone_missing(destination, source, apply)

    candidate = candidates[0]
    source_relative = candidate.relative_to(target_root).as_posix()
    structure_problem = relocation_structure_problem(candidate)
    if structure_problem:
        return {"path": relative, "status": "blocked", "detail": f"{source_relative}: {structure_problem}"}
    dirty_result = git(candidate, "status", "--porcelain=v1", "--untracked-files=normal")
    if dirty_result.returncode != 0:
        return {"path": relative, "status": "error", "detail": f"cannot inspect relocation source: {error_text(dirty_result)}"}
    dirty = bool(output(dirty_result))
    if dirty and not allow_dirty_relocation:
        return {
            "path": relative,
            "status": "blocked",
            "detail": f"matching checkout at {source_relative} is dirty; pass --allow-dirty-relocation after review",
        }
    parent_repo = enclosing_repository(destination)
    if parent_repo is not None:
        return {"path": relative, "status": "conflict", "detail": f"destination is inside existing repository {parent_repo}"}
    if not apply:
        qualifier = "dirty " if dirty else ""
        claimed_paths.add(candidate)
        return {
            "path": relative,
            "status": "planned-move",
            "detail": f"move {qualifier}matching checkout from {source_relative}",
            "from_path": source_relative,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        candidate.rename(destination)
    except OSError as exc:
        return {
            "path": relative,
            "status": "error",
            "detail": f"move from {source_relative} failed without fallback copying: {exc}",
            "from_path": source_relative,
        }
    claimed_paths.add(destination)
    inventory[remote_identity] = [destination if path == candidate else path for path in inventory.get(remote_identity, [])]
    return {
        "path": relative,
        "status": "moved",
        "detail": f"moved matching checkout from {source_relative}",
        "from_path": source_relative,
    }


def bootstrap_repository(
    target_root: Path,
    destination: Path,
    source: dict[str, object],
    apply: bool,
    inventory: dict[str, list[Path]],
    desired_paths: set[Path],
    claimed_paths: set[Path],
    allow_dirty_relocation: bool,
    refresh_existing: bool = False,
) -> dict[str, object]:
    relative = str(source["relative_path"])
    if not destination.exists() and not destination.is_symlink():
        result = relocate_or_clone(
            target_root,
            destination,
            source,
            apply,
            inventory,
            desired_paths,
            claimed_paths,
            allow_dirty_relocation,
        )
        if not refresh_existing or not apply or result.get("status") != "moved":
            return result
        moved_state, moved_problem = inspect_repository(destination, source)
        if moved_problem:
            return moved_problem
        assert moved_state is not None
        if moved_state["dirty"]:
            return result
        refreshed = refresh_repository(destination, source, apply=True)
        if refreshed.get("status") in {"already-current", "fast-forwarded"}:
            return {
                "path": relative,
                "status": "moved-and-refreshed",
                "detail": f"{result['detail']}; {refreshed['detail']}",
                "from_path": result.get("from_path"),
            }
        return refreshed
    state, problem = inspect_repository(destination, source)
    if problem:
        return problem
    assert state is not None
    if state["transport_drift"]:
        transport = reconcile_remote(destination, source, apply)
        if not apply or transport.get("status") != "remote-updated":
            return transport
        state, problem = inspect_repository(destination, source)
        if problem:
            return problem
        assert state is not None
    if state["dirty"]:
        if refresh_existing:
            return {"path": relative, "status": "blocked", "detail": "matching repository is dirty"}
        return {"path": relative, "status": "present-dirty", "detail": "matching repository exists; bootstrap leaves it unchanged"}
    claimed_paths.add(destination)
    if refresh_existing:
        return refresh_repository(destination, source, apply)
    return {"path": relative, "status": "already-present", "detail": "matching repository exists; bootstrap leaves it unchanged"}


def refresh_repository(destination: Path, source: dict[str, object], apply: bool) -> dict[str, object]:
    relative = str(source["relative_path"])
    if not destination.exists() and not destination.is_symlink():
        return {"path": relative, "status": "missing", "detail": "run bootstrap first"}
    state, problem = inspect_repository(destination, source)
    if problem:
        return problem
    assert state is not None
    if state["transport_drift"]:
        transport = reconcile_remote(destination, source, apply)
        if not apply or transport.get("status") != "remote-updated":
            return transport
        state, problem = inspect_repository(destination, source)
        if problem:
            return problem
        assert state is not None
    if state["dirty"]:
        return {"path": relative, "status": "blocked", "detail": "target repository is dirty"}
    branch = state["branch"]
    upstream = state["upstream"]
    remote_name = str(state["remote_name"])
    if not apply:
        if not branch:
            return {"path": relative, "status": "planned-fetch-only", "detail": "target HEAD is detached"}
        if not upstream:
            return {"path": relative, "status": "planned-fetch-only", "detail": "target branch has no upstream"}
        if not str(upstream).startswith(f"{remote_name}/"):
            return {"path": relative, "status": "planned-fetch-only", "detail": "target branch tracks a different remote"}
        if state["ahead"]:
            return {"path": relative, "status": "planned-fetch-only", "detail": f"target branch is ahead by {state['ahead']} commit(s)"}
        return {"path": relative, "status": "planned-fetch-fast-forward", "detail": f"current branch {branch}"}

    fetched = git(destination, "fetch", "--prune", remote_name)
    if fetched.returncode != 0:
        return {"path": relative, "status": "error", "detail": f"fetch failed: {error_text(fetched)}"}
    if not branch:
        return {"path": relative, "status": "blocked", "detail": "fetched, but target HEAD is detached"}
    if not upstream:
        return {"path": relative, "status": "blocked", "detail": "fetched, but target branch has no upstream"}
    if not str(upstream).startswith(f"{remote_name}/"):
        return {"path": relative, "status": "blocked", "detail": "fetched, but target branch tracks a different remote"}
    counts = git(destination, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
    if counts.returncode != 0:
        return {"path": relative, "status": "blocked", "detail": "cannot establish divergence after fetch"}
    ahead, behind = (int(value) for value in output(counts).split())
    if ahead:
        return {"path": relative, "status": "blocked", "detail": f"target branch is ahead by {ahead} commit(s)"}
    if not behind:
        return {"path": relative, "status": "already-current", "detail": f"current branch {branch}"}
    merged = git(destination, "merge", "--ff-only", str(upstream))
    if merged.returncode != 0:
        return {"path": relative, "status": "error", "detail": f"fast-forward failed: {error_text(merged)}"}
    return {"path": relative, "status": "fast-forwarded", "detail": f"advanced {behind} commit(s) on {branch}"}


def remote_ref(destination: Path | None, source: dict[str, object], branch: str | None) -> tuple[bool, bool]:
    ref = f"refs/heads/{branch}" if branch else "HEAD"
    checked = run(
        ["git", "ls-remote", "--exit-code", str(source["remote_url"]), ref],
        env=noninteractive_git_environment(),
    )
    if checked.returncode != 0:
        return False, False
    if destination is None or not branch:
        return True, False
    remote_head = output(checked).split()[0] if output(checked) else ""
    local = git(destination, "rev-parse", "HEAD")
    differs = local.returncode != 0 or not remote_head or output(local) != remote_head
    return True, differs


def preflight_repositories(repositories: list[dict[str, object]]) -> dict[str, object]:
    results: list[dict[str, object]] = []
    environment = noninteractive_git_environment()
    for source in repositories:
        relative = str(source.get("relative_path", ""))
        branch = source.get("clone_branch")
        ref = f"refs/heads/{branch}" if isinstance(branch, str) and branch else "HEAD"
        checked = run(
            ["git", "ls-remote", "--exit-code", str(source.get("remote_url", "")), ref],
            env=environment,
        )
        if checked.returncode == 0:
            results.append(
                {"path": relative, "status": "reachable", "detail": f"remote {ref} is reachable noninteractively"}
            )
        else:
            results.append(
                {
                    "path": relative,
                    "status": "blocked",
                    "detail": f"noninteractive Git access failed: {error_text(checked)}",
                }
            )
    return {"ok": all(result["status"] == "reachable" for result in results), "results": results}


def doctor_repository(destination: Path, source: dict[str, object]) -> dict[str, object]:
    relative = str(source["relative_path"])
    if not destination.exists() and not destination.is_symlink():
        remote_access, _ = remote_ref(None, source, None)
        access = "reachable" if remote_access else "unreachable or unauthorized"
        return {"path": relative, "status": "missing", "detail": f"repository is not bootstrapped; remote {access}"}
    state, problem = inspect_repository(destination, source)
    if problem:
        return problem
    assert state is not None
    branch = str(state["branch"]) if state["branch"] else None
    remote_access, remote_differs = remote_ref(destination, source, branch)
    issues: list[str] = []
    if state["dirty"]:
        issues.append("dirty")
    if not state["branch"]:
        issues.append("detached HEAD")
    if not state["upstream"]:
        issues.append("no upstream")
    elif not str(state["upstream"]).startswith(f"{state['remote_name']}/"):
        issues.append("branch tracks a different remote")
    if state["divergence_error"]:
        issues.append("divergence is unreadable")
    if state["ahead"]:
        issues.append(f"ahead {state['ahead']}")
    if state["behind"]:
        issues.append(f"behind {state['behind']}")
    if state["transport_drift"]:
        issues.append("transport drift")
    if not remote_access:
        issues.append("remote branch absent, unreachable, or unauthorized")
    elif remote_differs:
        issues.append("remote branch differs from local HEAD")
    if state["project_problem"]:
        issues.append(str(state["project_problem"]))
    elif state["project_path"] is not None and not Path(state["project_path"]).is_dir():
        issues.append("Codex project root is absent")
    features = f"AGENTS.md={'yes' if state['has_agents'] else 'no'}, .codex={'yes' if state['has_codex'] else 'no'}"
    if issues:
        return {"path": relative, "status": "attention", "detail": f"{', '.join(issues)}; {features}"}
    return {"path": relative, "status": "ready", "detail": features}


def record_target_run(
    target_root: Path,
    machine_id: str,
    source_machine_id: str,
    run_id: str,
    operation: str,
    repositories: list[dict[str, object]],
    results: list[dict[str, object]],
) -> dict[str, object]:
    state_root = target_root / STATE_DIRECTORY
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    completed_at = utc_now()
    inventory = repository_inventory(target_root)
    desired_identities = {str(repo["remote_identity"]) for repo in repositories}
    observed: list[dict[str, object]] = []
    display_by_identity = {str(repo["remote_identity"]): str(repo.get("remote_display", "")) for repo in repositories}
    for identity in sorted(desired_identities):
        for path in sorted(inventory.get(identity, [])):
            head = git(path, "rev-parse", "HEAD")
            observed.append(
                {
                    "remote_identity": identity,
                    "remote_display": display_by_identity.get(identity, ""),
                    "relative_path": path.relative_to(target_root).as_posix(),
                    "head": output(head) if head.returncode == 0 else None,
                }
            )
    run_record = {
        "schema_version": 1,
        "run_id": run_id,
        "machine_id": machine_id,
        "source_machine_id": source_machine_id,
        "role": "target",
        "operation": operation,
        "mode": "apply",
        "completed_at": completed_at,
        "results": results,
        "observed_repositories": observed,
    }
    atomic_write_json(state_root / "runs" / f"{run_id}.json", run_record)
    atomic_write_json(
        state_root / "state.json",
        {
            "schema_version": 1,
            "machine_id": machine_id,
            "updated_at": completed_at,
            "last_run_id": run_id,
            "observed_repositories": observed,
        },
    )
    status_counts: dict[str, int] = {}
    for result in results:
        status = str(result.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    append_bounded_jsonl(
        state_root / "history.jsonl",
        {
            "run_id": run_id,
            "completed_at": completed_at,
            "machine_id": machine_id,
            "source_machine_id": source_machine_id,
            "role": "target",
            "operation": operation,
            "status_counts": status_counts,
        },
    )
    run_files = sorted((state_root / "runs").glob("*.json"))
    for stale in run_files[:-RUN_RETENTION]:
        stale.unlink()
    return {"recorded": True, "root": str(state_root), "run_id": run_id}


def prerequisites() -> dict[str, str]:
    git_path = shutil.which("git")
    codex_path = shutil.which("codex")
    git_version = output(run([git_path, "--version"])) if git_path else "missing"
    codex_version = output(run([codex_path, "--version"])) if codex_path else "missing"
    codex_auth = "unavailable"
    if codex_path:
        auth = run([codex_path, "login", "status"])
        codex_auth = "authenticated" if auth.returncode == 0 else "not-authenticated-or-unverified"
    return {"git": git_version or "unreadable", "codex": codex_version or "unreadable", "codex_auth": codex_auth}


def main() -> int:
    lock_handle = None
    try:
        payload = json.load(sys.stdin)
        operation = str(payload.get("operation"))
        apply = bool(payload.get("apply"))
        preflight_only = bool(payload.get("preflight_only"))
        target_root = Path(str(payload["target_root"]))
        repositories = payload["repositories"]
        machine_id = str(payload.get("machine_id") or "unknown")
        source_machine_id = str(payload.get("source_machine_id") or "unknown")
        run_id = str(payload.get("run_id") or "")
        allow_dirty_relocation = bool(payload.get("allow_dirty_relocation"))
        if operation not in {"bootstrap", "reconcile", "refresh", "doctor", "migrate-github-remotes"}:
            raise ValueError("invalid operation")
        if operation == "doctor" and apply:
            raise ValueError("doctor cannot apply changes")
        if preflight_only and apply:
            raise ValueError("preflight_only cannot apply changes")
        if not target_root.is_absolute() or not isinstance(repositories, list):
            raise ValueError("invalid target payload")

        preflight = (
            preflight_repositories(repositories)
            if operation in {"bootstrap", "reconcile", "refresh", "migrate-github-remotes"}
            else {"ok": True, "results": []}
        )
        if apply and not preflight["ok"]:
            json.dump(
                {
                    "ok": True,
                    "operation": operation,
                    "mode": "preflight-failed",
                    "ready": False,
                    "prerequisites": prerequisites(),
                    "preflight": preflight,
                    "results": [],
                    "project_paths": [],
                    "history": None,
                    "applied": False,
                },
                sys.stdout,
            )
            sys.stdout.write("\n")
            return 0
        if apply:
            target_root.mkdir(parents=True, exist_ok=True)
            state_root = migrate_runtime_state(target_root)
            lock_path = state_root / "operation.lock"
            lock_handle = lock_path.open("a+", encoding="utf-8")
            lock_path.chmod(0o600)
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                lock_handle.close()
                raise ValueError("another workspace apply operation is active") from exc
        results: list[dict[str, object]] = []
        expected_projects: list[str] = []
        inventory = repository_inventory(target_root) if operation in {"bootstrap", "reconcile"} else {}
        desired_paths: set[Path] = set()
        for source in repositories:
            desired, _ = safe_destination(target_root, str(source.get("relative_path", "")))
            if desired is not None:
                desired_paths.add(desired)
        claimed_paths: set[Path] = set()
        for source in repositories:
            relative = str(source.get("relative_path", ""))
            try:
                destination, reason = safe_destination(target_root, relative)
                if destination is None:
                    results.append({"path": relative, "status": "blocked", "detail": reason})
                    continue
                configured_project, project_problem = project_path(destination, source)
                if project_problem or configured_project is None:
                    results.append({"path": relative, "status": "blocked", "detail": project_problem})
                    continue
                if operation in {"bootstrap", "reconcile"}:
                    result = bootstrap_repository(
                        target_root,
                        destination,
                        source,
                        apply,
                        inventory,
                        desired_paths,
                        claimed_paths,
                        allow_dirty_relocation,
                        refresh_existing=operation == "reconcile",
                    )
                elif operation == "refresh":
                    result = refresh_repository(destination, source, apply)
                elif operation == "migrate-github-remotes":
                    result = reconcile_remote(destination, source, apply)
                else:
                    result = doctor_repository(destination, source)
                results.append(result)
                if configured_project.is_dir() and result.get("status") not in {"blocked", "conflict", "error", "missing"}:
                    expected_projects.append(str(configured_project))
            except Exception as exc:
                results.append({"path": relative, "status": "error", "detail": str(exc)[:500]})
        checks = prerequisites()
        ready = checks["git"] != "missing" and checks["codex"] != "missing" and checks["codex_auth"] == "authenticated"
        history: dict[str, object] | None = None
        if apply:
            if not run_id:
                history = {"recorded": False, "root": str(target_root / STATE_DIRECTORY), "error": "apply payload has no run_id"}
            else:
                try:
                    history = record_target_run(
                        target_root,
                        machine_id,
                        source_machine_id,
                        run_id,
                        operation,
                        repositories,
                        results,
                    )
                except OSError as exc:
                    history = {"recorded": False, "root": str(target_root / STATE_DIRECTORY), "error": str(exc)[:500]}
        json.dump(
            {
                "ok": True,
                "operation": operation,
                "mode": "apply" if apply else "preflight" if preflight_only else "preview",
                "ready": ready,
                "prerequisites": checks,
                "preflight": preflight,
                "results": results,
                "project_paths": expected_projects,
                "history": history,
                "applied": apply,
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        if lock_handle is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()
        return 0
    except Exception as exc:
        if lock_handle is not None:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                lock_handle.close()
            except OSError:
                pass
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
