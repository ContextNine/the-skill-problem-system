#!/usr/bin/env python3
"""Build and reconcile portable point-in-time global skill snapshots."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tarfile
import tempfile
from typing import Any


SCHEMA_VERSION = 1
STATE_RELATIVE = Path(".agents/.vault-agent-skill-snapshot.json")
SKILLS_RELATIVE = Path(".agents/skills")
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IGNORED_NAMES = {".DS_Store", "__pycache__"}
MAX_FILES = 100_000
MAX_EXPANDED_BYTES = 512 * 1024 * 1024


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotBundle:
    manifest: dict[str, str]
    archive: bytes
    file_count: int
    logical_bytes: int


def lexists(path: Path) -> bool:
    return os.path.lexists(path)


def ignored(path: Path) -> bool:
    return path.name in IGNORED_NAMES or path.suffix == ".pyc"


def skill_files(source: Path) -> list[Path]:
    paths: list[Path] = []
    for path in source.rglob("*"):
        if any(part in IGNORED_NAMES for part in path.relative_to(source).parts) or ignored(path):
            continue
        if path.is_symlink():
            raise SnapshotError(f"portable skill snapshots cannot contain symlinks: {path}")
        if not path.is_dir() and not path.is_file():
            raise SnapshotError(f"unsupported skill snapshot entry: {path}")
        paths.append(path)
    return sorted(paths, key=lambda item: item.relative_to(source).as_posix())


def digest_skill(source: Path) -> str:
    if not source.is_dir() or source.is_symlink():
        raise SnapshotError(f"skill source must be a real directory: {source}")
    digest = hashlib.sha256()
    for path in skill_files(source):
        if path.is_dir():
            continue
        relative = path.relative_to(source).as_posix().encode()
        executable = b"1" if stat.S_IMODE(path.stat().st_mode) & 0o111 else b"0"
        digest.update(b"F\0" + relative + b"\0" + executable + b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def validate_sources(sources: dict[str, Path]) -> dict[str, Path]:
    normalized: dict[str, Path] = {}
    for name, raw in sorted(sources.items()):
        if not SKILL_NAME.fullmatch(name):
            raise SnapshotError(f"invalid skill snapshot name: {name!r}")
        source = raw.expanduser().resolve()
        if not (source / "SKILL.md").is_file():
            raise SnapshotError(f"skill snapshot source is missing SKILL.md: {source}")
        normalized[name] = source
    if not normalized:
        raise SnapshotError("skill snapshot is empty")
    return normalized


def tar_info(path: Path, archive_name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(archive_name)
    mode = stat.S_IMODE(path.stat().st_mode) & 0o777
    info.mode = mode
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    if path.is_dir():
        info.type = tarfile.DIRTYPE
        info.size = 0
    else:
        info.type = tarfile.REGTYPE
        info.size = path.stat().st_size
    return info


def build_bundle(sources: dict[str, Path]) -> SnapshotBundle:
    sources = validate_sources(sources)
    manifest = {name: digest_skill(source) for name, source in sources.items()}
    buffer = io.BytesIO()
    file_count = 0
    logical_bytes = 0
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name, source in sources.items():
            root_name = f"skills/{name}"
            archive.addfile(tar_info(source, root_name))
            for path in skill_files(source):
                relative = path.relative_to(source).as_posix()
                info = tar_info(path, f"{root_name}/{relative}")
                if path.is_file():
                    file_count += 1
                    logical_bytes += info.size
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)
                else:
                    archive.addfile(info)
    return SnapshotBundle(manifest, buffer.getvalue(), file_count, logical_bytes)


def safe_home(raw: object) -> Path:
    home = Path(str(raw)).expanduser().resolve()
    if not home.is_absolute() or home != Path.home().resolve():
        raise SnapshotError(f"target home mismatch: expected {home}, process home is {Path.home().resolve()}")
    return home


def load_state(home: Path) -> dict[str, Any]:
    path = home / STATE_RELATIVE
    if not path.is_file() or path.is_symlink():
        return {"schema_version": SCHEMA_VERSION, "skills": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"skill snapshot state is invalid: {path}: {exc}") from exc
    if state.get("schema_version") != SCHEMA_VERSION or not isinstance(state.get("skills"), dict):
        raise SnapshotError(f"skill snapshot state has an unsupported schema: {path}")
    return state


def resolved_link(path: Path) -> Path | None:
    if not path.is_symlink():
        return None
    raw = Path(os.readlink(path))
    return (path.parent / raw).resolve(strict=False) if not raw.is_absolute() else raw.resolve(strict=False)


def legacy_owned_link(path: Path, name: str, legacy_catalog: Path | None) -> bool:
    target = resolved_link(path)
    return bool(target and legacy_catalog and target == (legacy_catalog / name).resolve(strict=False))


def desired_alias(path: Path, canonical: Path) -> str:
    return os.path.relpath(canonical, path.parent)


def discovery_roots(home: Path) -> list[Path]:
    roots = [home / ".claude/skills", home / ".kilo/skills"]
    if (home / ".kilocode").exists():
        roots.append(home / ".kilocode/skills")
    return roots


def inspect_snapshot(
    home: Path,
    manifest: dict[str, str],
    *,
    legacy_catalog: Path | None,
) -> dict[str, object]:
    state = load_state(home)
    prior = {str(name): str(value) for name, value in state["skills"].items()}
    managed = set(prior)
    canonical_root = home / SKILLS_RELATIVE
    changes: list[dict[str, str]] = []
    collisions: list[str] = []

    if lexists(canonical_root) and (canonical_root.is_symlink() or not canonical_root.is_dir()):
        target = resolved_link(canonical_root)
        if not (target and legacy_catalog and target == legacy_catalog.resolve(strict=False)):
            collisions.append(str(canonical_root))

    for name, expected in sorted(manifest.items()):
        target = canonical_root / name
        if not lexists(target):
            changes.append({"status": "missing", "path": str(target), "detail": "skill snapshot would be installed"})
            continue
        if target.is_dir() and not target.is_symlink():
            try:
                actual = digest_skill(target)
            except SnapshotError:
                actual = ""
            if actual == expected:
                if name not in managed or prior.get(name) != expected:
                    changes.append({"status": "adopt", "path": str(target), "detail": "matching snapshot would be recorded as managed"})
                continue
            if name in managed:
                changes.append({"status": "different", "path": str(target), "detail": "managed skill snapshot would be replaced"})
                continue
        elif name in managed or legacy_owned_link(target, name, legacy_catalog):
            changes.append({"status": "different", "path": str(target), "detail": "managed skill entry would be replaced with a snapshot"})
            continue
        collisions.append(str(target))

    for name in sorted(managed - set(manifest)):
        target = canonical_root / name
        if lexists(target):
            changes.append({"status": "stale", "path": str(target), "detail": "stale managed skill would be removed"})

    for directory in discovery_roots(home):
        if lexists(directory) and (directory.is_symlink() or not directory.is_dir()):
            target = resolved_link(directory)
            allowed = target in {
                canonical_root.resolve(strict=False),
                legacy_catalog.resolve(strict=False) if legacy_catalog else None,
            }
            if not allowed:
                collisions.append(str(directory))
                continue
            changes.append({"status": "different", "path": str(directory), "detail": "owned discovery root would become a directory"})
            existing: dict[str, Path] = {}
        else:
            existing = {entry.name: entry for entry in directory.iterdir()} if directory.is_dir() else {}
            if not directory.exists():
                changes.append({"status": "missing", "path": str(directory), "detail": "discovery directory would be created"})
        for name in sorted(manifest):
            path = directory / name
            canonical = canonical_root / name
            entry = existing.get(name)
            if entry is None:
                changes.append({"status": "missing", "path": str(path), "detail": "discovery link would be created"})
            elif entry.is_symlink() and resolved_link(entry) == canonical.resolve(strict=False):
                continue
            elif name in managed or legacy_owned_link(entry, name, legacy_catalog):
                changes.append({"status": "different", "path": str(path), "detail": "managed discovery entry would be replaced"})
            else:
                collisions.append(str(path))
        for name in sorted(managed - set(manifest)):
            path = directory / name
            if lexists(path):
                changes.append({"status": "stale", "path": str(path), "detail": "stale managed discovery entry would be removed"})

    legacy_codex = home / ".codex/skills"
    if legacy_catalog and legacy_codex.is_symlink() and resolved_link(legacy_codex) == legacy_catalog.resolve(strict=False):
        changes.append({"status": "stale", "path": str(legacy_codex), "detail": "legacy Codex skill link would be removed"})

    if collisions:
        raise SnapshotError("unmanaged skill collisions block sync: " + ", ".join(sorted(set(collisions))))
    return {
        "ok": True,
        "ready": not changes,
        "changes": changes,
        "skill_count": len(manifest),
    }


def safe_archive_path(name: str) -> tuple[str, ...]:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2 or path.parts[0] != "skills":
        raise SnapshotError(f"unsafe skill archive path: {name!r}")
    if not SKILL_NAME.fullmatch(path.parts[1]):
        raise SnapshotError(f"invalid skill archive name: {name!r}")
    return path.parts


def extract_archive(encoded: str, staging: Path, manifest: dict[str, str]) -> Path:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise SnapshotError("skill snapshot archive is not valid base64") from exc
    root = staging / "skills"
    file_count = 0
    expanded = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = safe_archive_path(member.name)
            if parts[1] not in manifest:
                raise SnapshotError(f"archive contains an undeclared skill: {parts[1]}")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise SnapshotError(f"archive contains an unsupported entry: {member.name}")
            target = staging.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(member.mode & 0o777)
                continue
            if not member.isfile():
                raise SnapshotError(f"archive contains an unsupported entry: {member.name}")
            file_count += 1
            expanded += member.size
            if file_count > MAX_FILES or expanded > MAX_EXPANDED_BYTES:
                raise SnapshotError("skill snapshot archive exceeds safety limits")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise SnapshotError(f"cannot read archive entry: {member.name}")
            with target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
            target.chmod(member.mode & 0o777)
    for name, expected in manifest.items():
        source = root / name
        if not source.is_dir() or digest_skill(source) != expected:
            raise SnapshotError(f"extracted skill snapshot failed verification: {name}")
    return root


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def replace_directory(target: Path, source: Path, suffix: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    incoming = target.parent / f".{target.name}.incoming-{suffix}-{os.getpid()}"
    previous = target.parent / f".{target.name}.previous-{suffix}-{os.getpid()}"
    if lexists(incoming) or lexists(previous):
        raise SnapshotError(f"temporary skill snapshot path already exists for {target}")
    os.replace(source, incoming)
    moved_previous = False
    try:
        if lexists(target):
            os.replace(target, previous)
            moved_previous = True
        os.replace(incoming, target)
    except Exception:
        if moved_previous and not lexists(target) and lexists(previous):
            os.replace(previous, target)
        raise
    finally:
        remove_path(incoming)
    remove_path(previous)


def write_state(home: Path, manifest: dict[str, str]) -> None:
    path = home / STATE_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "managed_by": "ctx9-agents sync",
        "skills": dict(sorted(manifest.items())),
    }
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_directory(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif path.exists() and not path.is_dir():
        raise SnapshotError(f"discovery path is not a directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def install_alias(path: Path, canonical: Path) -> None:
    expected = desired_alias(path, canonical)
    if path.is_symlink() and os.readlink(path) == expected:
        return
    remove_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.sync-link-{os.getpid()}"
    if lexists(temporary):
        raise SnapshotError(f"temporary discovery link exists: {temporary}")
    temporary.symlink_to(expected, target_is_directory=True)
    os.replace(temporary, path)


def apply_snapshot(
    home: Path,
    manifest: dict[str, str],
    archive: str,
    *,
    legacy_catalog: Path | None,
    suffix: str,
) -> dict[str, object]:
    preview = inspect_snapshot(home, manifest, legacy_catalog=legacy_catalog)
    state = load_state(home)
    managed = {str(name) for name in state["skills"]}
    canonical_root = home / SKILLS_RELATIVE
    if canonical_root.is_symlink():
        canonical_root.unlink()
    ensure_directory(canonical_root)
    staging_parent = home / ".agents"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".vault-skill-stage-", dir=staging_parent))
    try:
        extracted = extract_archive(archive, staging, manifest)
        for name, expected in sorted(manifest.items()):
            target = canonical_root / name
            if target.is_dir() and not target.is_symlink() and digest_skill(target) == expected:
                continue
            replace_directory(target, extracted / name, suffix)
        for name in sorted(managed - set(manifest)):
            remove_path(canonical_root / name)

        for directory in discovery_roots(home):
            if directory.is_symlink():
                directory.unlink()
            ensure_directory(directory)
            for name in sorted(manifest):
                install_alias(directory / name, canonical_root / name)
            for name in sorted(managed - set(manifest)):
                remove_path(directory / name)

        legacy_codex = home / ".codex/skills"
        if legacy_catalog and legacy_codex.is_symlink() and resolved_link(legacy_codex) == legacy_catalog.resolve(strict=False):
            legacy_codex.unlink()
        write_state(home, manifest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {
        "ok": True,
        "ready": True,
        "applied": True,
        "changes": preview["changes"],
        "skill_count": len(manifest),
    }


def reconcile_payload(payload: dict[str, object]) -> dict[str, object]:
    home = safe_home(payload.get("home"))
    raw_manifest = payload.get("manifest")
    if not isinstance(raw_manifest, dict) or not raw_manifest:
        raise SnapshotError("skill snapshot payload has no manifest")
    manifest = {str(name): str(value) for name, value in raw_manifest.items()}
    for name, digest in manifest.items():
        if not SKILL_NAME.fullmatch(name) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SnapshotError(f"invalid skill snapshot manifest entry: {name!r}")
    legacy_raw = payload.get("legacy_catalog")
    legacy_catalog = Path(str(legacy_raw)).expanduser().resolve() if legacy_raw else None
    apply = bool(payload.get("apply"))
    preview = inspect_snapshot(home, manifest, legacy_catalog=legacy_catalog)
    if apply:
        archive = payload.get("archive")
        if not isinstance(archive, str) or not archive:
            raise SnapshotError("apply requires a skill snapshot archive")
        return apply_snapshot(
            home,
            manifest,
            archive,
            legacy_catalog=legacy_catalog,
            suffix=str(payload.get("backup_suffix") or "unknown"),
        )
    return {**preview, "applied": False, "mode": "verify" if payload.get("verify") else "preview"}


def payload_for(
    home: Path,
    bundle: SnapshotBundle,
    *,
    apply: bool,
    verify: bool,
    backup_suffix: str,
    legacy_catalog: Path | None,
) -> dict[str, object]:
    return {
        "home": str(home),
        "manifest": bundle.manifest,
        "archive": base64.b64encode(bundle.archive).decode() if apply else None,
        "apply": apply,
        "verify": verify,
        "backup_suffix": backup_suffix,
        "legacy_catalog": str(legacy_catalog) if legacy_catalog else None,
    }


def reconcile_local(
    home: Path,
    bundle: SnapshotBundle,
    *,
    apply: bool,
    verify: bool,
    backup_suffix: str,
    legacy_catalog: Path | None,
) -> dict[str, object]:
    resolved_home = home.expanduser().resolve()
    preview = inspect_snapshot(resolved_home, bundle.manifest, legacy_catalog=legacy_catalog)
    if apply:
        return apply_snapshot(
            resolved_home,
            bundle.manifest,
            base64.b64encode(bundle.archive).decode(),
            legacy_catalog=legacy_catalog,
            suffix=backup_suffix,
        )
    return {**preview, "applied": False, "mode": "verify" if verify else "preview"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise SnapshotError("payload must be an object")
        report = reconcile_payload(payload)
        json.dump(report, sys.stdout)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)[:1000]}, sys.stdout)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
