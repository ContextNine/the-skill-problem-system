#!/usr/bin/env python3
"""Synchronize cataloged Git workspaces on registered machines."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import sync_agent_configuration as agent_configuration
import plugin_reconciliation
import code_workspace_target_worker as workspace_worker


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
BLOCKING_STATUSES = {"attention", "blocked", "conflict", "error", "missing", "not-ready"}
STATE_DIRECTORY = ".workspace-sync"
LEGACY_STATE_DIRECTORY = ".ctx9/workspace-bootstrap"
RUN_RETENTION = 100
HISTORY_RETENTION = 500
DEFAULT_REMOTE_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def run(command: list[str], *, cwd: Path | None = None, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=stdin,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *args])


def output(process: subprocess.CompletedProcess[str]) -> str:
    return process.stdout.strip()


def error_text(process: subprocess.CompletedProcess[str]) -> str:
    value = (process.stderr or process.stdout).strip()
    return value.splitlines()[-1][:500] if value else "command failed"


def github_repository(owner: str, name: str, *, missing_ok: bool = False) -> dict[str, object] | None:
    """Resolve a GitHub repository through gh without handling credentials here."""
    result = run(["gh", "api", f"repos/{owner}/{name}"])
    if result.returncode != 0:
        if missing_ok and "HTTP 404" in (result.stderr or result.stdout):
            return None
        raise RuntimeError(f"cannot resolve GitHub repository {owner}/{name}: {error_text(result)}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitHub returned invalid repository metadata for {owner}/{name}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), int):
        raise RuntimeError(f"GitHub repository metadata is incomplete for {owner}/{name}")
    return payload


def prepare_github_owner_transfer(
    repositories: list[dict[str, object]], old_owner: str, new_owner: str
) -> list[dict[str, object]]:
    """Attach a verified owner-transfer destination while retaining the current identity for inspection."""
    owner_pattern = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
    if not re.fullmatch(owner_pattern, old_owner) or not re.fullmatch(owner_pattern, new_owner):
        raise RuntimeError("GitHub owners must be ordinary account or organization names")
    if old_owner.lower() == new_owner.lower():
        raise RuntimeError("GitHub owner transfer requires different old and new owners")
    prepared: list[dict[str, object]] = []
    for repository in repositories:
        identity = str(repository["remote_identity"])
        match = re.fullmatch(r"github\.com/([^/]+)/([^/]+)", identity, flags=re.IGNORECASE)
        if not match or match.group(1).lower() != old_owner.lower():
            raise RuntimeError(
                f"selected repository {repository['relative_path']} is not owned by github.com/{old_owner}"
            )
        name = match.group(2)
        previous = github_repository(old_owner, name, missing_ok=True)
        current = github_repository(new_owner, name)
        expected_id = previous["id"] if previous is not None else repository.get("expected_github_repository_id")
        if not isinstance(expected_id, int):
            raise RuntimeError(
                f"pre-transfer GitHub repository ID is required for {old_owner}/{name} after its old API route is gone"
            )
        assert current is not None
        if expected_id != current["id"]:
            raise RuntimeError(
                f"GitHub repository ID changed for {old_owner}/{name} -> {new_owner}/{name}"
            )
        if str(current.get("full_name", "")).lower() != f"{new_owner}/{name}".lower():
            raise RuntimeError(f"GitHub canonical owner is not {new_owner} for repository {name}")
        desired_url = f"git@github.com:{new_owner}/{name}.git"
        prepared.append(
            {
                **repository,
                "remote_url": desired_url,
                "remote_display": desired_url,
                "transfer_target_identity": f"github.com/{new_owner}/{name}",
                "github_repository_id": expected_id,
            }
        )
    return prepared


def adopt_github_owner_transfer(
    catalog_path: Path,
    transferred_remotes: dict[str, str],
    old_owner: str,
    new_owner: str,
) -> list[dict[str, str]]:
    """Persist verified GitHub owner changes to exact catalog entries."""
    catalog = load_catalog(catalog_path)
    entries = catalog["entries"]
    changes: list[dict[str, str]] = []
    for entry_id, verified_new_url in sorted(transferred_remotes.items()):
        entry = entries.get(entry_id)
        if not isinstance(entry, dict):
            raise RuntimeError(f"catalog entry {entry_id!r} is missing")
        configured = entry.get("remote")
        old_url = str(configured) if isinstance(configured, str) else ""
        expected_prefix = f"git@github.com:{old_owner}/"
        if old_url and (
            not old_url.lower().startswith(expected_prefix.lower()) or not old_url.endswith(".git")
        ):
            raise RuntimeError(f"catalog entry {entry_id!r} is not owned by {old_owner}")
        new_url = verified_new_url
        if not new_url.lower().startswith(f"git@github.com:{new_owner}/".lower()) or not new_url.endswith(".git"):
            raise RuntimeError(f"catalog entry {entry_id!r} has an invalid verified destination")
        entry["remote"] = new_url
        changes.append({"entry": entry_id, "from": old_url or "derived-from-checkout", "to": new_url})
    atomic_write_json(catalog_path, catalog, sort_keys=False)
    return changes


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def migrate_runtime_state(code_root: Path) -> Path:
    """Move legacy workspace-sync state into its dedicated Code-root directory."""
    state_root = code_root / STATE_DIRECTORY
    legacy_root = code_root / LEGACY_STATE_DIRECTORY
    for label, path in (("workspace sync state", state_root), ("legacy workspace sync state", legacy_root)):
        if path.is_symlink():
            raise RuntimeError(f"{label} cannot be a symlink: {path}")
        if path.exists() and not path.is_dir():
            raise RuntimeError(f"{label} is not a directory: {path}")
    if state_root.exists() and legacy_root.exists():
        raise RuntimeError(
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


def atomic_write_json(path: Path, value: object, *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    is_runtime_state = STATE_DIRECTORY in path.parts
    if is_runtime_state:
        path.parent.chmod(0o700)
    file_mode = 0o600 if is_runtime_state else path.stat().st_mode & 0o777 if path.exists() else 0o600
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=sort_keys) + "\n", encoding="utf-8")
    temporary.chmod(file_mode)
    temporary.replace(path)


def append_bounded_jsonl(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = path.with_name("history.lock")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise OSError("another source history writer is active") from exc
        try:
            existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            lines = [*existing[-(HISTORY_RETENTION - 1) :], json.dumps(value, sort_keys=True)]
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(path)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def record_source_run(
    source_root: Path,
    source_id: str,
    run_id: str,
    operation: str,
    repositories: list[dict[str, object]],
    target_reports: list[dict[str, object]],
    source_results: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    state_root = source_root / STATE_DIRECTORY
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    completed_at = utc_now()
    sanitized_repositories = [public_repository(repo) for repo in repositories]
    run_record = {
        "schema_version": 1,
        "run_id": run_id,
        "machine_id": source_id,
        "role": "source",
        "operation": operation,
        "mode": "apply",
        "completed_at": completed_at,
        "repositories": sanitized_repositories,
        "source_results": source_results or [],
        "targets": target_reports,
    }
    atomic_write_json(state_root / "runs" / f"{run_id}.json", run_record)
    atomic_write_json(
        state_root / "state.json",
        {
            "schema_version": 1,
            "machine_id": source_id,
            "updated_at": completed_at,
            "last_run_id": run_id,
            "observed_repositories": [
                {
                    "remote_identity": repo["remote_identity"],
                    "relative_path": repo["relative_path"],
                    "remote_display": repo["remote_display"],
                }
                for repo in sanitized_repositories
            ],
        },
    )
    status_counts: dict[str, int] = {}
    for result in source_results or []:
        status = str(result.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    for target in target_reports:
        for result in target.get("results", []):
            status = str(result.get("status", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1
    append_bounded_jsonl(
        state_root / "history.jsonl",
        {
            "run_id": run_id,
            "completed_at": completed_at,
            "machine_id": source_id,
            "role": "source",
            "operation": operation,
            "targets": [target.get("id") for target in target_reports],
            "status_counts": status_counts,
        },
    )
    run_files = sorted((state_root / "runs").glob("*.json"))
    for stale in run_files[:-RUN_RETENTION]:
        stale.unlink()
    return {"recorded": True, "root": str(state_root), "run_id": run_id}


def vault_root() -> Path:
    try:
        resolved = run(["vault", "root"])
    except FileNotFoundError:
        resolved = None
    if resolved is not None and resolved.returncode == 0 and output(resolved):
        return Path(output(resolved)).resolve()
    fallback = run(["git", "rev-parse", "--show-toplevel"])
    if fallback.returncode == 0 and output(fallback):
        return Path(output(fallback)).resolve()
    raise RuntimeError("cannot resolve the vault root")


def load_json(path: Path, label: str) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{label} must contain a JSON object")
    return data


def current_machine_id(root: Path) -> str:
    identity = run(["git", "-C", str(root), "config", "--get", "vault.machine-id"])
    if identity.returncode == 0 and output(identity):
        return output(identity)
    marker = Path.home() / ".config/vault/machine-id"
    try:
        value = marker.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if not value:
        raise RuntimeError("current machine has no Vault identity; use vault machine identify")
    return value


def remote_details(url: str) -> tuple[str | None, str, str | None]:
    value = url.strip().rstrip("/")
    if not value:
        return None, "", "remote URL is empty"
    if "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme == "file" or not parsed.hostname:
            return None, value, "local or malformed remote URL"
        if parsed.password is not None or (parsed.scheme in {"http", "https"} and parsed.username is not None):
            safe = urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))
            return None, safe, "credential-bearing remote URL"
        if parsed.query or parsed.fragment:
            safe = urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))
            return None, safe, "remote URL contains query or fragment data"
        try:
            port = parsed.port
        except ValueError:
            return None, value, "remote URL has an invalid port"
        host = parsed.hostname.lower()
        host_identity = f"{host}:{port}" if port is not None else host
        path = parsed.path.lstrip("/")
        display_user = parsed.username if parsed.scheme.startswith("ssh") else None
        display_netloc = f"{display_user}@{host_identity}" if display_user else host_identity
        display = urlunsplit((parsed.scheme, display_netloc, parsed.path, "", ""))
    else:
        match = re.match(r"^(?:([^@/:]+)@)?([^/:]+):(.+)$", value)
        if not match:
            return None, value, "local or unrecognized remote URL"
        user, host, path = match.groups()
        host_identity = host.lower()
        display = f"{user + '@' if user else ''}{host_identity}:{path}"
    if path.endswith(".git"):
        path = path[:-4]
    if not path:
        return None, display, "remote URL has no repository path"
    return f"{host_identity}/{path}", display, None


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


def normalize_project_root(value: object) -> str:
    project = PurePosixPath(str(value or "."))
    if project.is_absolute() or ".." in project.parts:
        raise RuntimeError(f"invalid codex_project_root: {value!r}")
    return project.as_posix()


def validate_under_code(path: Path, source_root: Path) -> Path:
    source_root = source_root.expanduser().resolve()
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(source_root)
    except ValueError as exc:
        raise RuntimeError(f"workspace path must be inside {source_root}: {resolved}") from exc
    return resolved


def load_catalog(path: Path) -> dict[str, object]:
    registry = load_json(path, "repository registry")
    if registry.get("schema_version") != 2:
        raise RuntimeError("repository registry needs schema_version 2")
    if not isinstance(registry.get("defaults", {}), dict) or not isinstance(registry.get("entries"), dict):
        raise RuntimeError("workspace defaults and entries must be objects")
    return registry


def normalize_spec(entry_id: str, raw: dict[str, object], defaults: dict[str, object]) -> dict[str, object]:
    spec = {**defaults, **raw, "id": entry_id}
    if not isinstance(spec.get("path"), str) or not spec["path"]:
        raise RuntimeError(f"catalog entry {entry_id!r} needs a path")
    path = PurePosixPath(str(spec["path"]))
    if path.is_absolute() or ".." in path.parts or str(spec["path"]).startswith("~"):
        raise RuntimeError(f"catalog entry {entry_id!r} path must be Code-root-relative")
    discovery = str(spec.get("discovery", "repository"))
    if discovery not in {"repository", "recursive", "auto"}:
        raise RuntimeError(f"catalog entry {entry_id!r} has invalid discovery {discovery!r}")
    clone_mode = str(spec.get("clone_mode", "partial"))
    if clone_mode not in {"partial", "full"}:
        raise RuntimeError(f"catalog entry {entry_id!r} has invalid clone_mode {clone_mode!r}")
    profiles = spec.get("profiles", ["core"])
    machines = spec.get("machines", ["*"])
    if not isinstance(profiles, list) or not all(isinstance(value, str) for value in profiles):
        raise RuntimeError(f"catalog entry {entry_id!r} profiles must be strings")
    if not isinstance(machines, list) or not all(isinstance(value, str) for value in machines):
        raise RuntimeError(f"catalog entry {entry_id!r} machines must be strings")
    spec.update(
        {
            "discovery": discovery,
            "clone_mode": clone_mode,
            "profiles": profiles,
            "machines": machines,
            "codex_project_root": normalize_project_root(spec.get("codex_project_root", ".")),
            "required": bool(spec.get("required", False)),
        }
    )
    return spec


def select_specs(catalog: dict[str, object], args: argparse.Namespace, source_root: Path) -> tuple[list[dict[str, object]], str]:
    defaults = catalog.get("defaults", {})
    entries = catalog["entries"]
    if args.path:
        if args.entry or args.profile:
            raise RuntimeError("--path cannot be combined with --entry or --profile")
        specs: list[dict[str, object]] = []
        for index, supplied in enumerate(args.path, start=1):
            candidate = supplied if supplied.is_absolute() else source_root / supplied
            candidate = validate_under_code(candidate, source_root)
            relative = candidate.relative_to(source_root).as_posix()
            specs.append(
                normalize_spec(
                    f"path-{index}",
                    {"path": relative, "discovery": "auto", "required": True},
                    defaults,
                )
            )
        return specs, "explicit paths"

    if args.entry and args.profile:
        raise RuntimeError("--entry and --profile are mutually exclusive")
    if args.entry:
        selected_ids = args.entry
        missing = [entry_id for entry_id in selected_ids if entry_id not in entries]
        if missing:
            raise RuntimeError(f"unknown catalog entries: {', '.join(missing)}")
        selected_specs = []
        for entry_id in selected_ids:
            raw = entries[entry_id]
            if not isinstance(raw, dict):
                raise RuntimeError(f"catalog entry {entry_id!r} must be an object")
            selected_specs.append(normalize_spec(entry_id, raw, defaults))
        return selected_specs, "selected entries"

    profile = args.profile or str(catalog.get("default_profile", "core"))
    specs = []
    for entry_id, raw in entries.items():
        if not isinstance(raw, dict):
            raise RuntimeError(f"catalog entry {entry_id!r} must be an object")
        spec = normalize_spec(entry_id, raw, defaults)
        if profile in spec["profiles"]:
            specs.append(spec)
    if not specs:
        raise RuntimeError(f"no catalog entries match profile {profile!r}")
    return specs, f"profile {profile}"


def has_git_marker(path: Path) -> bool:
    marker = path / ".git"
    return marker.is_dir() or marker.is_file() or marker.is_symlink()


def recursive_repositories(root: Path) -> list[Path]:
    found: list[Path] = []
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


def repositories_by_remote(root: Path) -> dict[str, list[Path]]:
    matches: dict[str, list[Path]] = {}
    for repo in recursive_repositories(root):
        _, remote_url = choose_remote(repo)
        if not remote_url:
            continue
        identity, _, problem = remote_details(remote_url)
        if not problem and identity:
            matches.setdefault(identity, []).append(repo)
    return matches


def inspect_source_repository(
    repo: Path,
    spec: dict[str, object],
    source_root: Path,
    *,
    catalog_relative_path: str | None = None,
) -> tuple[dict[str, object] | None, str | None]:
    relative = repo.resolve().relative_to(source_root).as_posix()
    configured_remote = spec.get("remote")
    source_exists = repo.is_dir() and has_git_marker(repo)
    actual_remote_name = actual_remote_url = None
    if source_exists:
        top = git(repo, "rev-parse", "--show-toplevel")
        if top.returncode != 0 or Path(output(top)).resolve() != repo.resolve():
            return None, "path is not an exact Git working-tree root"
        actual_remote_name, actual_remote_url = choose_remote(repo)

    remote_url = str(configured_remote) if configured_remote else actual_remote_url
    if not remote_url:
        return None, "repository has no configured or unambiguous non-local remote"
    remote_identity, remote_display, remote_problem = remote_details(remote_url)
    if remote_problem or not remote_identity:
        return None, remote_problem or "invalid remote"
    if actual_remote_url:
        actual_identity, _, actual_problem = remote_details(actual_remote_url)
        if actual_problem or actual_identity != remote_identity:
            return None, "configured remote does not match the source checkout"

    branch = upstream = None
    ahead = behind = None
    dirty = False
    has_submodules = False
    clone_branch = None
    if source_exists:
        branch_result = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
        branch = output(branch_result) if branch_result.returncode == 0 else None
        upstream_result = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        upstream = output(upstream_result) if upstream_result.returncode == 0 else None
        if upstream:
            counts_result = git(repo, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
            if counts_result.returncode == 0:
                ahead, behind = (int(value) for value in output(counts_result).split())
        status_result = git(repo, "status", "--porcelain=v1", "--untracked-files=normal")
        dirty = status_result.returncode != 0 or bool(output(status_result))
        has_submodules = (repo / ".gitmodules").is_file()
        if branch and upstream and actual_remote_name and upstream.startswith(f"{actual_remote_name}/") and ahead == 0:
            clone_branch = upstream[len(actual_remote_name) + 1 :]

    project_root = str(spec["codex_project_root"])
    project_relative = relative if project_root == "." else f"{relative}/{project_root}"
    return (
        {
            "entry_id": spec["id"],
            "relative_path": relative,
            "remote_url": remote_url,
            "remote_display": remote_display,
            "remote_identity": remote_identity,
            "branch": branch,
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
            "dirty": dirty,
            "clone_branch": clone_branch,
            "clone_mode": spec["clone_mode"],
            "has_submodules": has_submodules,
            "source_present": source_exists,
            "machines": spec["machines"],
            "codex_project_root": project_root,
            "project_relative_path": project_relative,
            "catalog_relative_path": catalog_relative_path or relative,
            "source_relocated": bool(catalog_relative_path and catalog_relative_path != relative),
            "expected_github_repository_id": spec.get("github_repository_id"),
        },
        None,
    )


def discover_specs(specs: list[dict[str, object]], source_root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    repositories: dict[str, dict[str, object]] = {}
    duplicate_paths: set[str] = set()
    skipped: list[dict[str, object]] = []
    remote_inventory: dict[str, list[Path]] | None = None
    for spec in specs:
        raw_path = Path(str(spec["path"])).expanduser()
        entry_path = validate_under_code(raw_path if raw_path.is_absolute() else source_root / raw_path, source_root)
        discovery = str(spec["discovery"])
        if discovery == "auto":
            discovery = "repository" if entry_path.is_dir() and has_git_marker(entry_path) else "recursive"
        candidates: list[Path] = []
        catalog_relative = entry_path.relative_to(source_root).as_posix()
        if discovery == "repository":
            if entry_path.is_dir() and has_git_marker(entry_path):
                candidates = [entry_path]
            elif spec.get("remote"):
                configured_identity, _, configured_problem = remote_details(str(spec["remote"]))
                if configured_problem or not configured_identity:
                    skipped.append({"entry": spec["id"], "path": catalog_relative, "reason": configured_problem or "invalid configured remote", "required": True})
                    continue
                if remote_inventory is None:
                    remote_inventory = repositories_by_remote(source_root)
                relocated = remote_inventory.get(configured_identity, [])
                if len(relocated) == 1:
                    candidates = relocated
                elif len(relocated) > 1:
                    skipped.append({"entry": spec["id"], "path": catalog_relative, "reason": "catalog path is not a Git root and multiple source checkouts match its remote", "required": True})
                    continue
                elif not entry_path.exists():
                    candidates = [entry_path]
                else:
                    skipped.append({"entry": spec["id"], "path": catalog_relative, "reason": "catalog path exists but is not a Git root", "required": spec["required"]})
                    continue
            else:
                skipped.append({"entry": spec["id"], "path": str(entry_path), "reason": "repository path is absent or not a Git root", "required": spec["required"]})
                continue
        else:
            if not entry_path.is_dir():
                skipped.append({"entry": spec["id"], "path": str(entry_path), "reason": "recursive workspace path is absent", "required": spec["required"]})
                continue
            candidates = recursive_repositories(entry_path)
            if not candidates:
                skipped.append({"entry": spec["id"], "path": str(entry_path), "reason": "no Git repositories discovered recursively", "required": spec["required"]})
                continue
        for candidate in candidates:
            record, problem = inspect_source_repository(
                candidate,
                spec,
                source_root,
                catalog_relative_path=catalog_relative if discovery == "repository" else None,
            )
            relative = candidate.resolve().relative_to(source_root).as_posix()
            if problem or record is None:
                member_required = bool(spec["required"] and discovery == "repository")
                skipped.append({"entry": spec["id"], "path": relative, "reason": problem or "inspection failed", "required": member_required})
                continue
            if relative in duplicate_paths:
                skipped.append({"entry": spec["id"], "path": relative, "reason": "duplicate target-relative repository path", "required": True})
                continue
            existing = repositories.get(relative)
            if existing:
                detail = "different remotes" if existing["remote_identity"] != record["remote_identity"] else "the same remote"
                skipped.append({"entry": spec["id"], "path": relative, "reason": f"duplicate target-relative path resolves to {detail}", "required": True})
                repositories.pop(relative, None)
                duplicate_paths.add(relative)
                continue
            repositories[relative] = record

    overlapping: set[str] = set()
    paths = sorted(repositories)
    for index, parent in enumerate(paths):
        parent_parts = PurePosixPath(parent).parts
        for child in paths[index + 1 :]:
            child_parts = PurePosixPath(child).parts
            if len(child_parts) > len(parent_parts) and child_parts[: len(parent_parts)] == parent_parts:
                overlapping.update({parent, child})
    for relative in sorted(overlapping):
        entry_id = repositories[relative]["entry_id"]
        skipped.append({"entry": entry_id, "path": relative, "reason": "parent/child repository paths overlap on the target", "required": True})
        repositories.pop(relative, None)

    casefold_paths: dict[str, str] = {}
    case_collisions: set[str] = set()
    for relative in sorted(repositories):
        folded = relative.casefold()
        existing = casefold_paths.get(folded)
        if existing is not None and existing != relative:
            case_collisions.update({existing, relative})
        else:
            casefold_paths[folded] = relative
    for relative in sorted(case_collisions):
        entry_id = repositories[relative]["entry_id"]
        skipped.append({"entry": entry_id, "path": relative, "reason": "case-insensitive target path collision", "required": True})
        repositories.pop(relative, None)

    identity_paths: dict[str, str] = {}
    repeated_identities: set[str] = set()
    for relative, repo in repositories.items():
        identity = str(repo["remote_identity"])
        existing = identity_paths.get(identity)
        if existing is not None and existing != relative:
            repeated_identities.update({existing, relative})
        else:
            identity_paths[identity] = relative
    for relative in sorted(repeated_identities):
        entry_id = repositories[relative]["entry_id"]
        skipped.append({"entry": entry_id, "path": relative, "reason": "canonical remote appears at multiple desired paths", "required": True})
        repositories.pop(relative, None)
    return [repositories[key] for key in sorted(repositories)], sorted(skipped, key=lambda item: (str(item["entry"]), str(item["path"])))


def source_warnings(repositories: list[dict[str, object]]) -> list[str]:
    warnings: list[str] = []
    for repo in repositories:
        relative = str(repo["relative_path"])
        if repo.get("source_relocated"):
            warnings.append(
                f"{repo['entry_id']}: source remote moved from catalog path "
                f"{repo['catalog_relative_path']} to {relative}; adopt the source layout before applying"
            )
        if not repo["source_present"]:
            warnings.append(f"{relative}: source checkout absent; catalog remote and default branch will be used")
        if repo["dirty"]:
            warnings.append(f"{relative}: dirty source files are not transferred")
        if isinstance(repo["ahead"], int) and repo["ahead"]:
            warnings.append(f"{relative}: {repo['ahead']} locally-ahead commit(s) are not transferred")
        if repo["source_present"] and not repo["branch"]:
            warnings.append(f"{relative}: detached source HEAD; new targets use the remote default branch")
        elif repo["source_present"] and not repo["upstream"]:
            warnings.append(f"{relative}: source branch has no upstream; new targets use the remote default branch")
        if repo["has_submodules"]:
            warnings.append(f"{relative}: submodules are not initialized")
    return warnings


def adopt_source_layout(catalog_path: Path, source_root: Path, repositories: list[dict[str, object]]) -> list[dict[str, object]]:
    relocations = [repo for repo in repositories if repo.get("source_relocated")]
    if not relocations:
        return []
    registry = load_json(catalog_path, "repository registry")
    entries = registry.get("entries")
    if not isinstance(entries, dict):
        raise RuntimeError("workspace entries are unavailable while adopting source layout")
    changes: list[dict[str, object]] = []
    for repo in relocations:
        entry_id = str(repo["entry_id"])
        entry = entries.get(entry_id)
        if not isinstance(entry, dict) or entry.get("discovery", "repository") != "repository":
            raise RuntimeError(f"cannot adopt source layout for non-repository entry {entry_id!r}")
        raw_current_path = Path(str(entry.get("path", ""))).expanduser()
        current_path = (raw_current_path if raw_current_path.is_absolute() else source_root / raw_current_path).resolve()
        expected = (source_root / str(repo["catalog_relative_path"])).resolve()
        if current_path != expected:
            raise RuntimeError(f"catalog entry {entry_id!r} changed during discovery; refusing to overwrite it")
        old_path = str(entry["path"])
        new_path = str(repo["relative_path"])
        entry["path"] = new_path
        changes.append({"entry": entry_id, "from": old_path, "to": new_path})
    atomic_write_json(catalog_path, registry, sort_keys=False)
    return changes


def load_machines(path: Path) -> dict[str, object]:
    registry = load_json(path, "machine registry")
    version = registry.get("schema_version")
    if not isinstance(version, int) or version < 1 or not isinstance(registry.get("machines"), list):
        raise RuntimeError("machine registry needs a positive integer schema_version and a machines list")
    if not isinstance(registry.get("primary_machine_id"), str):
        raise RuntimeError("machine registry has no primary_machine_id")
    return registry


def machine_code_root(machine: dict[str, object]) -> Path:
    home = machine.get("home")
    roots = machine.get("roots")
    raw = roots.get("code") if isinstance(roots, dict) else None
    if not isinstance(home, str) or not PurePosixPath(home).is_absolute() or not isinstance(raw, str):
        raise RuntimeError(f"machine {machine.get('id')} has no usable home or Code root")
    value = PurePosixPath(home).joinpath(*PurePosixPath(raw[2:]).parts) if raw.startswith("~/") else PurePosixPath(raw)
    if not value.is_absolute() or ".." in value.parts or "$" in raw:
        raise RuntimeError(f"machine {machine.get('id')} has an unsafe Code root")
    return Path(value.as_posix())


def resolve_targets(
    registry: dict[str, object],
    source_id: str,
    requested: list[str],
    *,
    provision_disabled: bool = False,
) -> list[dict[str, object]]:
    machines = [machine for machine in registry["machines"] if isinstance(machine, dict)]
    selected: list[dict[str, object]] = []
    if provision_disabled and len(requested) != 1:
        raise RuntimeError("--provision-disabled requires exactly one explicit --target")
    if requested:
        for value in requested:
            candidates = [
                machine
                for machine in machines
                if value.casefold() in {str(machine.get("id", "")).casefold(), str(machine.get("display_name", "")).casefold()}
            ]
            if len(candidates) != 1:
                raise RuntimeError(f"target {value!r} did not resolve to exactly one machine")
            machine = candidates[0]
            if machine.get("id") == source_id:
                raise RuntimeError(f"target {value!r} is the executing machine")
            if provision_disabled and machine.get("enabled"):
                raise RuntimeError(f"target {value!r} is already enabled")
            if not provision_disabled and not machine.get("enabled"):
                raise RuntimeError(f"target {value!r} is disabled")
            if machine not in selected:
                selected.append(machine)
    else:
        selected = [machine for machine in machines if machine.get("enabled") and machine.get("id") != source_id]
    if not selected:
        raise RuntimeError("no enabled target machines remain")
    for machine in selected:
        if machine.get("transport") != "ssh" or not machine.get("ssh_alias"):
            raise RuntimeError(f"target {machine.get('id')} lacks supported SSH transport")
        if not isinstance(machine.get("home"), str) or not str(machine["home"]).startswith("/"):
            raise RuntimeError(f"target {machine.get('id')} has no absolute home path")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", str(machine["ssh_alias"])):
            raise RuntimeError(f"target {machine.get('id')} has an unsafe SSH alias")
    return selected


def repositories_for_machine(repositories: list[dict[str, object]], machine_id: str) -> list[dict[str, object]]:
    return [repo for repo in repositories if "*" in repo["machines"] or machine_id in repo["machines"]]


def target_environment_path(machine: dict[str, object]) -> str:
    terminal_profile = machine.get("terminal_profile")
    configured = terminal_profile.get("remote_path") if isinstance(terminal_profile, dict) else None
    value = configured if isinstance(configured, str) and configured else DEFAULT_REMOTE_PATH
    parts = value.split(":")
    if any(not part.startswith("/") or re.search(r"\s", part) for part in parts):
        raise RuntimeError(f"target {machine.get('id')} has an unsafe terminal_profile.remote_path")
    return value


def target_python_command(machine: dict[str, object], worker_source: str) -> str:
    """Run a worker with the registered PATH and the logged-in macOS SSH agent."""
    remote_path = target_environment_path(machine)
    return (
        f"export PATH={shlex.quote(remote_path)}; "
        'if [ "$(uname -s)" = Darwin ] && [ ! -S "${SSH_AUTH_SOCK:-}" ]; then '
        'ctx9_agent_socket="$(launchctl print "gui/$(id -u)/com.openssh.ssh-agent" 2>/dev/null '
        "| awk '$1 == \"path\" && $2 == \"=\" && $3 ~ /\\/Listeners$/ {print $3; exit}')\"; "
        'if [ -S "$ctx9_agent_socket" ]; then export SSH_AUTH_SOCK="$ctx9_agent_socket"; fi; '
        'unset ctx9_agent_socket; fi; '
        f"exec python3 -c {shlex.quote(worker_source)}"
    )


def invoke_target(
    machine: dict[str, object],
    repositories: list[dict[str, object]],
    operation: str,
    apply: bool,
    *,
    source_id: str,
    run_id: str | None,
    allow_dirty_relocation: bool,
    preflight_only: bool = False,
) -> dict[str, object]:
    worker_path = Path(__file__).with_name("code_workspace_target_worker.py")
    worker_source = worker_path.read_text(encoding="utf-8")
    target_root = str(machine_code_root(machine))
    payload = json.dumps(
        {
            "operation": operation,
            "apply": apply,
            "target_root": target_root,
            "repositories": repositories,
            "machine_id": machine.get("id"),
            "source_machine_id": source_id,
            "run_id": run_id,
            "allow_dirty_relocation": allow_dirty_relocation,
            "preflight_only": preflight_only,
        }
    )
    remote_command = target_python_command(machine, worker_source)
    executed = run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", str(machine["ssh_alias"]), remote_command],
        stdin=payload,
    )
    base = {"id": machine.get("id"), "display_name": machine.get("display_name"), "target_root": target_root}
    if executed.returncode != 0 and not output(executed):
        return {**base, "ok": False, "error": f"SSH or remote worker failed: {error_text(executed)}"}
    try:
        response = json.loads(output(executed))
    except json.JSONDecodeError:
        return {**base, "ok": False, "error": f"invalid remote worker response: {error_text(executed)}"}
    return {**base, **response}


def invoke_plugin_target(
    machine: dict[str, object],
    inventory: dict[str, object],
    repositories: list[dict[str, object]],
    *,
    apply: bool,
    preflight_only: bool = False,
) -> dict[str, object]:
    worker_source = Path(__file__).with_name("plugin_reconciliation.py").read_text(encoding="utf-8")
    payload = json.dumps(
        {
            "home": machine["home"],
            "platform": machine.get("platform"),
            "inventory": inventory,
            "planned_repositories": [str(repository["relative_path"]) for repository in repositories],
            "apply": apply,
            "preflight_only": preflight_only,
        }
    )
    remote_command = target_python_command(machine, worker_source)
    executed = run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", str(machine["ssh_alias"]), remote_command],
        stdin=payload,
    )
    base = {"id": machine.get("id"), "display_name": machine.get("display_name")}
    if executed.returncode != 0 and not output(executed):
        return {**base, "ok": False, "ready": False, "applied": False, "error": f"SSH or plugin worker failed: {error_text(executed)}"}
    try:
        response = json.loads(output(executed))
    except json.JSONDecodeError:
        return {**base, "ok": False, "ready": False, "applied": False, "error": f"invalid plugin worker response: {error_text(executed)}"}
    return {**base, **response}


def public_repository(repo: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in repo.items() if key != "remote_url"}


def print_discovery(report: dict[str, object]) -> None:
    print(f"Source: {report['source_machine']} {report['source_root']}")
    print(f"Selection: {report['selection']}")
    print(f"Repositories: {len(report['repositories'])} usable, {len(report['skipped'])} skipped")
    for repo in report["repositories"]:
        print(f"  REPO {repo['relative_path']} <- {repo['remote_display']} [project {repo['project_relative_path']}]")
    for item in report["skipped"]:
        importance = "REQUIRED" if item["required"] else "SKIP"
        print(f"  {importance} {item['entry']}:{item['path']}: {item['reason']}")
    for warning in report["warnings"]:
        print(f"  WARN {warning}")


def print_target_report(report: dict[str, object]) -> None:
    print_discovery(report)
    source_remotes = report.get("source_remote_results")
    if source_remotes:
        print("Source remotes:")
        for result in source_remotes:
            print(f"  {str(result['status']).upper():<27} {result['path']}: {result['detail']}")
    source_agent_configuration = report.get("source_agent_configuration")
    if source_agent_configuration:
        print("Primary agent configuration:")
        for result in source_agent_configuration.get("results", []):
            print(f"  {str(result['status']).upper():<27} {result['path']}: {result['detail']}")
    source_plugins = report.get("source_plugins")
    if source_plugins:
        print("Primary plugins:")
        if not source_plugins.get("ok"):
            print(f"  ERROR {source_plugins.get('error', 'plugin verification failed')}")
        for result in source_plugins.get("marketplaces", []):
            print(f"  MARKETPLACE-{str(result['status']).upper():<15} {result['marketplace']}: {result['detail']}")
        for result in source_plugins.get("plugins", []):
            print(f"  PLUGIN-{str(result['status']).upper():<20} {result['plugin_id']}: {result['detail']}")
    for change in report.get("catalog_changes", []):
        verb = "ADOPTED" if report.get("mode") == "apply" else "PLANNED-CATALOG-ADOPTION"
        print(f"  {verb} {change['entry']}: {change['from']} -> {change['to']}")
    for target in report["targets"]:
        print(f"Target: {target.get('display_name') or target.get('id')} ({target.get('id')})")
        if not target.get("ok"):
            print(f"  ERROR {target.get('error', 'target failed')}")
        agent_report = target.get("agent_configuration")
        if agent_report:
            if agent_report.get("skipped"):
                print(f"  AGENT-CONFIG SKIPPED          {agent_report.get('detail')}")
            elif not agent_report.get("ok"):
                print(f"  AGENT-CONFIG ERROR            {agent_report.get('error', 'sync failed')}")
            else:
                for result in agent_report.get("results", []):
                    print(
                        f"  AGENT-{str(result['status']).upper():<21} "
                        f"{result['path']}: {result['detail']}"
                    )
        plugin_report = target.get("plugin_reconciliation")
        if plugin_report:
            if not plugin_report.get("ok"):
                print(f"  PLUGINS ERROR                 {plugin_report.get('error', 'reconciliation failed')}")
            for result in plugin_report.get("marketplaces", []):
                print(
                    f"  MARKETPLACE-{str(result['status']).upper():<15} "
                    f"{result['marketplace']}: {result['detail']}"
                )
            for result in plugin_report.get("plugins", []):
                print(
                    f"  PLUGIN-{str(result['status']).upper():<20} "
                    f"{result['plugin_id']}: {result['detail']}"
                )
            plugin_preflight = plugin_report.get("preflight")
            if plugin_preflight and not plugin_preflight.get("ok", False):
                for check in plugin_preflight.get("checks", []):
                    if check.get("status") != "ready":
                        print(f"  PLUGIN-PREFLIGHT BLOCKED      {check.get('detail')}")
        prerequisites = target.get("prerequisites")
        if prerequisites:
            print(
                "  PREREQUISITES "
                f"git={prerequisites.get('git')} codex={prerequisites.get('codex')} "
                f"auth={prerequisites.get('codex_auth')}"
            )
        for result in target.get("results", []):
            print(f"  {str(result['status']).upper():<27} {result['path']}: {result['detail']}")
        project_paths = target.get("project_paths", [])
        if project_paths:
            print("  Save as ChatGPT projects:")
            for project_path in project_paths:
                print(f"    {project_path}")
        history = target.get("history")
        if history:
            outcome = "recorded" if history.get("recorded") else f"failed: {history.get('error', 'unknown error')}"
            print(f"  HISTORY {outcome} [{history.get('root', 'unknown path')}]")
        preflight = target.get("preflight")
        if preflight and not preflight.get("ok", False):
            print("  PREFLIGHT BLOCKED: noninteractive Git access is unavailable")
            for check in preflight.get("results", []):
                if check.get("status") != "reachable":
                    print(f"    {check.get('path')}: {check.get('detail')}")
    source_history = report.get("source_history")
    if source_history:
        outcome = "recorded" if source_history.get("recorded") else f"failed: {source_history.get('error', 'unknown error')}"
        print(f"Source history: {outcome} [{source_history.get('root', 'unknown path')}]")


def add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", help="catalog profile; defaults to default_profile")
    parser.add_argument("--entry", action="append", default=[], help="catalog entry ID; repeatable")
    parser.add_argument("--path", action="append", default=[], type=Path, help="repository or recursively scanned path; repeatable")
    parser.add_argument("--source-root", type=Path, help="executing machine's Code root; defaults to the machine registry")
    parser.add_argument("--catalog", type=Path, help="repositories.json override")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--skip-personal-configuration",
        action="store_true",
        help="reconcile workspaces only; agent configuration is owned by fleet sync",
    )


def add_target_arguments(parser: argparse.ArgumentParser, *, mutable: bool) -> None:
    parser.add_argument("--target", action="append", default=[], help="machine ID or display name; repeatable")
    parser.add_argument("--machine-registry", type=Path, help="machines.json override")
    parser.add_argument(
        "--provision-disabled",
        action="store_true",
        help="target exactly one disabled machine during reviewed onboarding",
    )
    if mutable:
        parser.add_argument("--apply", action="store_true", help="apply the planned target changes")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    discover = subparsers.add_parser("discover", help="resolve catalog or recursive paths without contacting targets")
    add_selection_arguments(discover)
    bootstrap = subparsers.add_parser("bootstrap", help="clone missing repositories on targets")
    add_selection_arguments(bootstrap)
    add_target_arguments(bootstrap, mutable=True)
    bootstrap.add_argument("--allow-remote-only-source", action="store_true", help="acknowledge unpublished source state is not transferred")
    bootstrap.add_argument("--allow-dirty-relocation", action="store_true", help="permit moving a dirty matching target checkout")
    bootstrap.add_argument("--adopt-source-layout", action="store_true", help="adopt uniquely detected exact-entry source moves into the catalog")
    reconcile = subparsers.add_parser("reconcile", help="idempotently move matching checkouts or clone missing repositories")
    add_selection_arguments(reconcile)
    add_target_arguments(reconcile, mutable=True)
    reconcile.add_argument("--allow-remote-only-source", action="store_true", help="acknowledge unpublished source state is not transferred")
    reconcile.add_argument("--allow-dirty-relocation", action="store_true", help="permit moving a dirty matching target checkout")
    reconcile.add_argument("--adopt-source-layout", action="store_true", help="adopt uniquely detected exact-entry source moves into the catalog")
    refresh = subparsers.add_parser("refresh", help="fetch and safely fast-forward existing target repositories")
    add_selection_arguments(refresh)
    add_target_arguments(refresh, mutable=True)
    doctor = subparsers.add_parser("doctor", help="diagnose target repository and Codex readiness")
    add_selection_arguments(doctor)
    add_target_arguments(doctor, mutable=False)
    migrate = subparsers.add_parser(
        "migrate-github-remotes",
        help="change same-identity GitHub remotes to the catalog's canonical SSH URLs",
    )
    add_selection_arguments(migrate)
    add_target_arguments(migrate, mutable=True)
    transfer = subparsers.add_parser(
        "transfer-github-owner",
        help="rewrite remotes after a GitHub owner transfer verified by immutable repository ID",
    )
    add_selection_arguments(transfer)
    add_target_arguments(transfer, mutable=True)
    transfer.add_argument("--old-owner", required=True, help="current owner recorded in the workspace catalog")
    transfer.add_argument("--new-owner", required=True, help="new canonical GitHub organization or account")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = vault_root()
        source_id = current_machine_id(root)
        machine_path = getattr(args, "machine_registry", None) or root / "_system/agents/edit/settings/fleet/machines.json"
        machine_registry = load_machines(machine_path.expanduser().resolve())
        source_matches = [machine for machine in machine_registry["machines"] if isinstance(machine, dict) and machine.get("id") == source_id]
        if len(source_matches) != 1:
            raise RuntimeError(f"source machine {source_id!r} did not resolve exactly once")
        source_root = (args.source_root or machine_code_root(source_matches[0])).expanduser().resolve()
        if not source_root.is_dir():
            raise RuntimeError(f"source Code root is not a directory: {source_root}")
        catalog_path = args.catalog or root / "_system/agents/edit/settings/fleet/workspaces.json"
        catalog = load_catalog(catalog_path.expanduser().resolve())
        specs, selection = select_specs(catalog, args, source_root)
        repositories, skipped = discover_specs(specs, source_root)
        if not repositories:
            raise RuntimeError("no repositories with usable canonical remotes were discovered")
        warnings = source_warnings(repositories)
        if args.command == "transfer-github-owner":
            repositories = prepare_github_owner_transfer(repositories, args.old_owner, args.new_owner)
        if args.command == "migrate-github-remotes":
            invalid_transport = [
                str(repo["relative_path"])
                for repo in repositories
                if str(repo["remote_identity"]).startswith("github.com/")
                and not re.fullmatch(r"git@github\.com:[^\s]+\.git", str(repo["remote_url"]))
            ]
            if invalid_transport:
                raise RuntimeError(
                    "GitHub catalog remotes must be canonical SSH before migration: "
                    + ", ".join(invalid_transport)
                )
        report: dict[str, object] = {
            "command": args.command,
            "source_machine": source_id,
            "source_root": str(source_root),
            "selection": selection,
            "repositories": [public_repository(repo) for repo in repositories],
            "skipped": skipped,
            "warnings": warnings,
        }
        if args.command == "discover":
            if args.json:
                json.dump(report, sys.stdout, indent=2)
                sys.stdout.write("\n")
            else:
                print_discovery(report)
            return 2 if any(item["required"] for item in skipped) else 0

        apply = bool(getattr(args, "apply", False))
        relocations = [repo for repo in repositories if repo.get("source_relocated")]
        if relocations and not getattr(args, "adopt_source_layout", False):
            details = ", ".join(
                f"{repo['entry_id']}:{repo['catalog_relative_path']}->{repo['relative_path']}" for repo in relocations
            )
            raise RuntimeError(
                f"source layout differs from exact catalog entries ({details}); review discover, then pass "
                "--adopt-source-layout to use the new layout"
            )
        catalog_changes = [
            {
                "entry": str(repo["entry_id"]),
                "from": str(repo["catalog_relative_path"]),
                "to": str(repo["relative_path"]),
            }
            for repo in relocations
        ]
        report["catalog_changes"] = catalog_changes
        if args.command in {"bootstrap", "reconcile"} and apply and not args.allow_remote_only_source:
            unpublished = [repo for repo in repositories if repo["dirty"] or (isinstance(repo["ahead"], int) and repo["ahead"] > 0)]
            if unpublished:
                raise RuntimeError(
                    f"{len(unpublished)} source repository/repositories have dirty or locally-ahead state; "
                    "review discover output, then pass --allow-remote-only-source only after confirming remote-only bootstrap"
                )
        targets = resolve_targets(
            machine_registry,
            source_id,
            args.target,
            provision_disabled=bool(args.provision_disabled),
        )
        primary_config_source = source_id == machine_registry["primary_machine_id"]
        sync_personal_configuration = (
            primary_config_source
            and args.command not in {"migrate-github-remotes", "transfer-github-owner"}
            and not args.skip_personal_configuration
        )
        agent_bundle = (
            agent_configuration.load_source_bundle(Path.home(), root=root, registry=machine_registry)
            if sync_personal_configuration
            else None
        )
        plugin_inventory = (
            plugin_reconciliation.build_desired_inventory(Path.home(), source_root)
            if sync_personal_configuration
            else None
        )
        if not primary_config_source:
            warnings.append(
                "personal agent configuration and plugins were not synchronized because only the registered primary is authoritative"
            )
        if plugin_inventory is not None:
            selected_paths = {str(repository["relative_path"]) for repository in repositories}
            required_local_paths = {
                str(plugin["repository_relative_path"])
                for plugin in plugin_inventory["plugins"]
                if plugin["source_type"] == "local-repository"
            }
            missing_local_paths = sorted(required_local_paths - selected_paths)
            if missing_local_paths:
                raise RuntimeError(
                    "desired local plugin marketplaces must be selected for repository sync first: "
                    + ", ".join(missing_local_paths)
                )
        agent_suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        agent_eligible = {
            str(machine["id"]): bool(
                primary_config_source
                and (args.provision_disabled or machine.get("global_agents_eligible") is True)
            )
            for machine in targets
        }

        def skipped_agent_configuration(machine: dict[str, object]) -> dict[str, object]:
            reason = (
                "the current machine is not the registered primary"
                if not primary_config_source
                else "machine is not marked global_agents_eligible"
            )
            return {"ok": True, "ready": True, "applied": False, "skipped": True, "detail": reason}

        if agent_bundle is not None:
            source_agent_configuration = agent_configuration.reconcile_source_alias(
                Path.home(),
                agent_bundle,
                source_id,
                root,
                apply=False,
                verify=args.command == "doctor",
                backup_suffix=agent_suffix,
                components={"config", "instructions"},
            )
            report["source_agent_configuration"] = source_agent_configuration
        if plugin_inventory is not None:
            source_plugin_payload = {
                "home": str(Path.home()),
                "platform": "macos",
                "inventory": plugin_inventory,
                "planned_repositories": [str(repository["relative_path"]) for repository in repositories],
                "apply": False,
                "preflight_only": apply,
            }
            report["source_plugins"] = plugin_reconciliation.reconcile(source_plugin_payload)
            if not report["source_plugins"].get("ok"):
                report["mode"] = "preflight-failed"
                report["targets"] = []
                if args.json:
                    json.dump(report, sys.stdout, indent=2)
                    sys.stdout.write("\n")
                else:
                    print_target_report(report)
                return 1
        run_id = new_run_id() if apply else None
        selections = [(machine, repositories_for_machine(repositories, str(machine["id"]))) for machine in targets]
        if args.command in {"migrate-github-remotes", "transfer-github-owner"}:
            source_preflight = workspace_worker.preflight_repositories(repositories)
            source_repositories = [repository for repository in repositories if repository.get("source_present")]
            source_remote_results = [
                (
                    workspace_worker.reconcile_github_owner_transfer
                    if args.command == "transfer-github-owner"
                    else workspace_worker.reconcile_remote
                )(source_root / str(repository["relative_path"]), repository, False)
                for repository in source_repositories
            ]
            report["source_remote_preflight"] = source_preflight
            report["source_remote_results"] = source_remote_results
            if apply and (
                not source_preflight["ok"]
                or any(result.get("status") in BLOCKING_STATUSES for result in source_remote_results)
            ):
                report["mode"] = "preflight-failed"
                report["targets"] = []
                if args.json:
                    json.dump(report, sys.stdout, indent=2)
                    sys.stdout.write("\n")
                else:
                    print_target_report(report)
                return 2

        if apply:
            preflight_reports: list[dict[str, object]] = []
            for machine, selected_repositories in selections:
                if agent_bundle is not None and agent_eligible[str(machine["id"])]:
                    agent_preview = agent_configuration.invoke_target(
                        machine,
                        agent_bundle,
                        apply=False,
                        verify=False,
                        backup_suffix=agent_suffix,
                    )
                else:
                    agent_preview = skipped_agent_configuration(machine)
                plugin_preview = (
                    invoke_plugin_target(
                        machine,
                        plugin_inventory,
                        selected_repositories,
                        apply=False,
                        preflight_only=True,
                    )
                    if plugin_inventory is not None and agent_eligible[str(machine["id"])]
                    else {"ok": True, "ready": True, "applied": False, "skipped": True}
                )
                if not selected_repositories:
                    preflight_reports.append(
                        {
                            "id": machine["id"],
                            "display_name": machine.get("display_name"),
                            "ok": True,
                            "mode": "preflight",
                            "preflight": {"ok": True, "results": []},
                            "results": [],
                            "project_paths": [],
                            "applied": False,
                            "agent_configuration": agent_preview,
                            "plugin_reconciliation": plugin_preview,
                        }
                    )
                    continue
                workspace_preview = invoke_target(
                        machine,
                        selected_repositories,
                        args.command,
                        False,
                        source_id=source_id,
                        run_id=None,
                        allow_dirty_relocation=bool(getattr(args, "allow_dirty_relocation", False)),
                        preflight_only=True,
                    )
                workspace_preview["agent_configuration"] = agent_preview
                workspace_preview["plugin_reconciliation"] = plugin_preview
                preflight_reports.append(workspace_preview)
            preflight_fatal = any(
                not target.get("ok")
                or not target.get("agent_configuration", {}).get("ok")
                or not target.get("plugin_reconciliation", {}).get("ok")
                for target in preflight_reports
            )
            preflight_blocked = any(
                not target.get("preflight", {}).get("ok", False)
                or any(result.get("status") in BLOCKING_STATUSES for result in target.get("results", []))
                for target in preflight_reports
                if target.get("ok")
            )
            if preflight_fatal or preflight_blocked:
                report["mode"] = "preflight-failed"
                report["targets"] = preflight_reports
                if args.json:
                    json.dump(report, sys.stdout, indent=2)
                    sys.stdout.write("\n")
                else:
                    print_target_report(report)
                return 1 if preflight_fatal else 2

        if apply and args.command in {"migrate-github-remotes", "transfer-github-owner"}:
            source_repositories = [repository for repository in repositories if repository.get("source_present")]
            report["source_remote_results"] = [
                (
                    workspace_worker.reconcile_github_owner_transfer
                    if args.command == "transfer-github-owner"
                    else workspace_worker.reconcile_remote
                )(source_root / str(repository["relative_path"]), repository, True)
                for repository in source_repositories
            ]
            if any(
                result.get("status") in BLOCKING_STATUSES
                for result in report["source_remote_results"]
            ):
                report["mode"] = "apply-failed"
                report["targets"] = []
                if args.json:
                    json.dump(report, sys.stdout, indent=2)
                    sys.stdout.write("\n")
                else:
                    print_target_report(report)
                return 2

        if apply:
            report["source_runtime_state"] = {"root": str(migrate_runtime_state(source_root))}
        if apply and agent_bundle is not None:
            report["source_agent_configuration"] = agent_configuration.reconcile_source_alias(
                Path.home(),
                agent_bundle,
                source_id,
                root,
                apply=True,
                verify=False,
                backup_suffix=agent_suffix,
                components={"config", "instructions"},
            )
        if apply and plugin_inventory is not None:
            report["source_plugins"] = plugin_reconciliation.reconcile(
                {
                    "home": str(Path.home()),
                    "platform": "macos",
                    "inventory": plugin_inventory,
                    "planned_repositories": [str(repository["relative_path"]) for repository in repositories],
                    "apply": True,
                    "preflight_only": False,
                }
            )
            if not report["source_plugins"].get("ok"):
                report["mode"] = "apply-failed"
                report["targets"] = []
                if args.json:
                    json.dump(report, sys.stdout, indent=2)
                    sys.stdout.write("\n")
                else:
                    print_target_report(report)
                return 1
        if apply and relocations:
            report["catalog_changes"] = adopt_source_layout(
                catalog_path.expanduser().resolve(), source_root, repositories
            )
        target_reports: list[dict[str, object]] = []
        for machine, selected_repositories in selections:
            if agent_bundle is not None and agent_eligible[str(machine["id"])]:
                agent_report = agent_configuration.invoke_target(
                    machine,
                    agent_bundle,
                    apply=apply,
                    verify=args.command == "doctor",
                    backup_suffix=agent_suffix,
                )
            else:
                agent_report = skipped_agent_configuration(machine)
            if not agent_report.get("ok"):
                target_reports.append(
                    {
                        "id": machine["id"],
                        "display_name": machine.get("display_name"),
                        "ok": False,
                        "error": "agent configuration sync failed before repository mutation",
                        "results": [],
                        "project_paths": [],
                        "applied": False,
                        "agent_configuration": agent_report,
                    }
                )
                continue
            if not selected_repositories:
                plugin_report = (
                    invoke_plugin_target(
                        machine,
                        plugin_inventory,
                        selected_repositories,
                        apply=apply,
                    )
                    if plugin_inventory is not None and agent_eligible[str(machine["id"])]
                    else {"ok": True, "ready": True, "applied": False, "skipped": True}
                )
                target_reports.append(
                    {
                        "id": machine["id"],
                        "display_name": machine.get("display_name"),
                        "ok": bool(plugin_report.get("ok")),
                        "ready": bool(agent_report.get("ready", True)) and bool(plugin_report.get("ready", True)),
                        "results": [],
                        "project_paths": [],
                        "applied": apply and bool(plugin_report.get("applied", True)),
                        "agent_configuration": agent_report,
                        "plugin_reconciliation": plugin_report,
                    }
                )
                continue
            workspace_report = invoke_target(
                    machine,
                    selected_repositories,
                    args.command,
                    apply,
                    source_id=source_id,
                    run_id=run_id,
                    allow_dirty_relocation=bool(getattr(args, "allow_dirty_relocation", False)),
                )
            workspace_report["agent_configuration"] = agent_report
            if workspace_report.get("ok"):
                plugin_report = (
                    invoke_plugin_target(
                        machine,
                        plugin_inventory,
                        selected_repositories,
                        apply=apply,
                    )
                    if plugin_inventory is not None and agent_eligible[str(machine["id"])]
                    else {"ok": True, "ready": True, "applied": False, "skipped": True}
                )
            else:
                plugin_report = {
                    "ok": False,
                    "ready": False,
                    "applied": False,
                    "error": "plugin reconciliation skipped because repository reconciliation failed",
                }
            workspace_report["plugin_reconciliation"] = plugin_report
            workspace_report["ok"] = bool(workspace_report.get("ok")) and bool(plugin_report.get("ok"))
            if not plugin_report.get("ok"):
                workspace_report["error"] = plugin_report.get("error", "plugin reconciliation failed")
            workspace_report["applied"] = bool(workspace_report.get("applied")) and (
                bool(plugin_report.get("applied")) if apply and not plugin_report.get("skipped") else True
            )
            workspace_report["ready"] = bool(workspace_report.get("ready")) and bool(
                agent_report.get("ready", True)
            ) and bool(plugin_report.get("ready", True))
            target_reports.append(workspace_report)
        report["mode"] = "apply" if apply else "preview"
        report["targets"] = target_reports
        all_targets_applied = all(target.get("ok") and target.get("applied") for target in target_reports)
        if apply and args.command == "transfer-github-owner" and all_targets_applied:
            report["catalog_owner_changes"] = adopt_github_owner_transfer(
                catalog_path.expanduser().resolve(),
                {
                    str(repository["entry_id"]): str(repository["remote_url"])
                    for repository in repositories
                },
                args.old_owner,
                args.new_owner,
            )
        if apply and run_id and all_targets_applied:
            try:
                report["source_history"] = record_source_run(
                    source_root,
                    source_id,
                    run_id,
                    args.command,
                    repositories,
                    target_reports,
                    report.get("source_remote_results", []),
                )
            except OSError as exc:
                report["source_history"] = {
                    "recorded": False,
                    "root": str(source_root / STATE_DIRECTORY),
                    "error": str(exc)[:500],
                }
        if args.json:
            json.dump(report, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print_target_report(report)
        fatal = any(not target.get("ok") for target in target_reports)
        incomplete = any(
            result.get("status") in BLOCKING_STATUSES
            for target in target_reports
            for result in target.get("results", [])
        )
        if args.command == "doctor" and any(not target.get("ready", False) for target in target_reports):
            incomplete = True
        if args.command == "doctor" and report.get("source_agent_configuration") and not report[
            "source_agent_configuration"
        ].get("ready", False):
            incomplete = True
        if args.command == "doctor" and report.get("source_plugins") and not report["source_plugins"].get(
            "ready", False
        ):
            incomplete = True
        if apply and (not all_targets_applied or not report.get("source_history", {}).get("recorded", False)):
            incomplete = True
        if apply and any(
            target.get("ok") and target.get("results") and not target.get("history", {}).get("recorded", False)
            for target in target_reports
        ):
            incomplete = True
        return 1 if fatal else 2 if incomplete else 0
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
