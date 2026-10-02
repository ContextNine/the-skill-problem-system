"""Machine-local, value-free checkpoints for primary-owned exact adoption."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Iterator


class AdoptionError(RuntimeError):
    pass


STAGES = {"prepared", "preflight", "preflight-blocked", "applying", "partial", "outcome-unknown", "recording", "recording-conflict", "verifying", "verification-failed", "complete"}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_scope(request: dict[str, Any], report: dict[str, Any]) -> None:
    if report.get("topology_digest") != request["topology_digest"] or report.get("targets") != request["targets"]:
        raise AdoptionError("adoption-topology-changed")


def validate_release(request: dict[str, Any], release: Any) -> dict[str, str]:
    if (
        not isinstance(release, dict)
        or release.get("component") != request["component"]
        or release.get("version") != request["version"]
        or any(
            not isinstance(release.get(field), str) or re.fullmatch(rf"[a-f0-9]{{{length}}}", release[field]) is None
            for field, length in (("source_commit", 40), ("catalog_sha256", 64))
        )
    ):
        raise AdoptionError("adoption-release-invalid")
    return {key: release[key] for key in ("component", "version", "source_commit", "catalog_sha256")}


def report_release(request: dict[str, Any], report: dict[str, Any]) -> dict[str, str] | None:
    if report.get("ok") is not True:
        return None
    if report.get("can_apply") is not True:
        if report.get("ready") is True:
            raise AdoptionError("adoption-release-invalid")
        return None
    preflight = report.get("preflight")
    if not isinstance(preflight, list) or not all(isinstance(item, dict) for item in preflight):
        raise AdoptionError("adoption-release-invalid")
    matches = [item for item in preflight if item.get("id") == request["dependency"]]
    if len(matches) != 1 or matches[0].get("installable") is not True:
        raise AdoptionError("adoption-release-invalid")
    return validate_release(request, matches[0].get("release"))


class ReleaseBinding:
    """Bind all target observations to one signed release, including read-only previews."""
    def __init__(self, request: dict[str, Any], release: dict[str, str] | None = None):
        self.request = request
        self.release = validate_release(request, release) if release is not None else None

    def observe(self, report: dict[str, Any]) -> None:
        release = report_release(self.request, report)
        if release is not None:
            if self.release is not None and self.release != release:
                raise AdoptionError("adoption-release-changed")
            self.release = release

    def expectations(self) -> dict[str, dict[str, str]]:
        return {self.request["dependency"]: {key: self.release[key] for key in ("source_commit", "catalog_sha256")}} if self.release is not None else {}


def read_state(path: Path) -> dict[str, Any] | None:
    if not path.exists() and not path.is_symlink():
        return None
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise AdoptionError("adoption-state-unsafe")
    try:
        contents = path.read_bytes()
        if len(contents) > 1024 * 1024:
            raise ValueError
        value = json.loads(contents)
    except (OSError, ValueError):
        raise AdoptionError("adoption-state-invalid") from None
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise AdoptionError("adoption-state-invalid")
    return value


def atomic_state(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        read_state(path)
    fd, name = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


class Adoption:
    def __init__(self, root: Path, request: dict[str, Any]):
        self.root = root
        self.operation = digest(request)
        self.path = root / f"{self.operation}.json"
        previous = read_state(self.path)
        if previous is not None and (previous.get("request") != request or previous.get("operation") != self.operation or previous.get("stage") not in STAGES or previous.get("values_returned") is not False or not isinstance(previous.get("targets"), dict)):
            raise AdoptionError("adoption-request-mismatch")
        if previous and any(machine_id not in request["targets"] or not isinstance(item, dict) or item.get("mode") not in {"dry-run", "verify", "apply"} or item.get("status") not in {"checking", "applying", "ready", "preflight-ready", "blocked"} for machine_id, item in previous["targets"].items()):
            raise AdoptionError("adoption-state-invalid")
        if previous and previous["stage"] in {"applying", "outcome-unknown"}:
            raise AdoptionError("adoption-outcome-unknown; confirm prior owner and children exited before recovery")
        self.state = previous or {"schema_version": 1, "operation": self.operation, "request": request, "stage": "prepared", "targets": {}, "release": None, "values_returned": False}
        self.binding = ReleaseBinding(request, self.state.get("release"))

    def stage(self, stage: str) -> None:
        if stage not in STAGES:
            raise AdoptionError("adoption-state-invalid")
        self.state.update(stage=stage, updated_at=timestamp())
        active = {"schema_version": 1, "operation": self.operation, "stage": stage, "values_returned": False}
        # Write the deny marker before entering mutation. Terminal checkpoints are journal-first.
        if stage in {"applying", "outcome-unknown"}:
            atomic_state(self.root / "active.json", active)
        atomic_state(self.path, self.state)
        if stage not in {"applying", "outcome-unknown"}:
            atomic_state(self.root / "active.json", active)

    def target(self, mode: str, event: str, report: dict[str, Any]) -> None:
        if event == "scope":
            validate_scope(self.state["request"], report)
            return
        machine_id = report.get("id")
        if not isinstance(machine_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", machine_id) or machine_id not in self.state["request"]["targets"]:
            raise AdoptionError("adoption-target-mismatch")
        if event == "started":
            status = "applying" if mode == "apply" else "checking"
        elif mode == "apply" and report.get("outcome_known") is not True:
            status = "applying"
        else:
            status = "ready" if report.get("ok") is True and report.get("ready") is True else "preflight-ready" if report.get("ok") is True and report.get("can_apply") is True else "blocked"
        # Store closed status only, never an error, environment or arbitrary worker report.
        self.state["targets"][machine_id] = {"mode": mode, "status": status, "updated_at": timestamp()}
        atomic_state(self.path, self.state)
        if event == "finished":
            self.binding.observe(report)
            self.state["release"] = self.binding.release
            atomic_state(self.path, self.state)

    def interrupted(self) -> None:
        if self.state["stage"] in {"preflight-blocked", "recording-conflict", "verification-failed"}:
            return
        unknown = any(item.get("status") == "applying" for item in self.state["targets"].values())
        self.stage("outcome-unknown" if unknown else "partial")


@contextmanager
def adoption_lock(home: Path, request: dict[str, Any]) -> Iterator[Adoption]:
    root = home / ".agents/state/fleet-updates"
    if any(path.is_symlink() for path in (root, root.parent, root.parent.parent)):
        raise AdoptionError("adoption-state-unsafe")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = root.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise AdoptionError("adoption-state-unsafe")
    fd = os.open(root / "adoption.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        lock_info = os.fstat(fd)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.getuid() or stat.S_IMODE(lock_info.st_mode) != 0o600:
            raise AdoptionError("adoption-state-unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AdoptionError("adoption-already-active") from None
        active = read_state(root / "active.json")
        if active and (active.get("stage") not in STAGES or not isinstance(active.get("operation"), str) or not re.fullmatch(r"[a-f0-9]{64}", active["operation"])):
            raise AdoptionError("adoption-state-invalid")
        if active and active.get("stage") in {"applying", "outcome-unknown"}:
            raise AdoptionError("adoption-outcome-unknown; confirm prior owner and children exited before recovery")
        if active:
            active_journal = read_state(root / f"{active['operation']}.json")
            if active_journal and active_journal.get("stage") in {"applying", "outcome-unknown"}:
                raise AdoptionError("adoption-outcome-unknown; confirm prior owner and children exited before recovery")
        adoption = Adoption(root, request)
        adoption.stage("prepared")
        try:
            yield adoption
        except BaseException:
            adoption.interrupted()
            raise
    finally:
        os.close(fd)
