"""Browse managed skills and edit ratings without changing skill bundles."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time

from package_layout import AGENTS_ROOT, resolve_agents_root, load_instance


METADATA_RELATIVE = Path("edit/settings/skills/skill-metadata.json")
CATALOG_RELATIVE = Path(".agents/state/skill-catalog.json")
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SOURCE_ORDER = {"vault": 0, "repo": 1, "gh": 2}


def score(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 5:
        raise ValueError("rating must be a whole number from 0 to 5")
    return value


def read_metadata(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or set(value) != {"schema_version", "skills"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not isinstance(value["skills"], dict)):
        raise ValueError(f"invalid skill metadata envelope: {path}")
    for name, record in value["skills"].items():
        if not NAME_RE.fullmatch(name) or len(name) > 64:
            raise ValueError(f"invalid metadata skill name: {name}")
        if not isinstance(record, dict) or set(record) - {"rating"}:
            raise ValueError(f"invalid skill metadata record: {name}")
        if "rating" in record:
            score(record["rating"])
    return value["skills"]


def source_root(home: Path) -> Path | None:
    from package_installer import installed_source

    identity = home / ".agents/state/machine-id"
    settings = home / ".agents/settings"
    if identity.is_file() and settings.is_dir():
        machine = load_instance(settings)["fleet"]["machines"].get(identity.read_text().strip())
        if machine and machine["role"] != "primary":
            return None
    owner = installed_source(home)
    candidate = owner if owner is not None else AGENTS_ROOT
    if (candidate / "edit/skills").is_dir() and (candidate / "internal/src").is_dir():
        return candidate
    return None


def rows_from_skills(root: Path, skills: list, records: dict[str, dict]) -> dict[str, dict]:
    root = resolve_agents_root(root)
    rows = {}
    for skill in skills:
        record = records.get(skill.name, {})
        rows[skill.name] = {
            "name": skill.name,
            "area": skill.area,
            "collection": skill.collection,
            "rating": record.get("rating"),
            "source": skill.source,
            "mode": skill.mode,
        }
    return rows


def source_catalog(root: Path, *, home: Path | None = None) -> dict[str, dict]:
    import sync_skills

    root = resolve_agents_root(root)
    try:
        _, skills = sync_skills.discover_skills(root, home=home)
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    return rows_from_skills(root, skills, read_metadata(root / METADATA_RELATIVE))


def catalog(home: Path) -> dict[str, dict]:
    root = source_root(home)
    if root is not None:
        return source_catalog(root, home=home)
    import skill_snapshots

    rows = skill_snapshots.load_catalog(home)
    owned = skill_snapshots.load_state(home)["skills"]
    return {name: row for name, row in rows.items()
            if name in owned and (home / ".agents/skills" / name / "SKILL.md").is_file()}


def group_key(row: dict, group_by: str) -> tuple:
    if group_by == "source":
        return (SOURCE_ORDER[row["source"]], row["source"])
    if group_by == "none":
        return ()
    return (0, row["area"]) if row["area"] else (1, row["collection"])


def group_label(row: dict, group_by: str) -> str:
    if group_by == "source":
        return {"vault": "Locally maintained", "repo": "Repository", "gh": "GitHub"}[row["source"]]
    return f"Area: {row['area']}" if row["area"] else f"Collection: {row['collection']}"


def select(rows: dict[str, dict], *, areas: list[str], collections: list[str],
           rating: int | None, minimum: int | None, maximum: int | None,
           unrated: bool, sort: str, descending: bool, group_by: str) -> list[dict]:
    numeric = any(value is not None for value in (rating, minimum, maximum))
    if unrated and numeric:
        raise ValueError("--unrated cannot be combined with numeric rating filters")
    if rating is not None and (minimum is not None or maximum is not None):
        raise ValueError("--rating cannot be combined with range filters")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("--min-rating must not exceed --max-rating")
    if sort == "preferred" and descending:
        raise ValueError("--descending requires --sort name, rating, or source")
    selected = []
    for row in rows.values():
        value = row["rating"]
        if (areas or collections) and row["area"] not in areas and row["collection"] not in collections:
            continue
        if unrated and value is not None:
            continue
        if numeric and value is None:
            continue
        if rating is not None and value != rating:
            continue
        if minimum is not None and value < minimum:
            continue
        if maximum is not None and value > maximum:
            continue
        selected.append(row)
    selected.sort(key=lambda row: row["name"])
    if sort == "preferred":
        selected.sort(key=lambda row: (SOURCE_ORDER[row["source"]], row["rating"] is None,
                                       -(row["rating"] or 0)))
    elif sort == "rating":
        rated = [row for row in selected if row["rating"] is not None]
        rated.sort(key=lambda row: row["rating"], reverse=descending)
        selected = rated + [row for row in selected if row["rating"] is None]
    elif sort == "source":
        selected.sort(key=lambda row: SOURCE_ORDER[row["source"]], reverse=descending)
    else:
        selected.sort(key=lambda row: row["name"], reverse=descending)
    selected.sort(key=lambda row: group_key(row, group_by))
    return selected


def print_listing(rows: list[dict], group_by: str) -> None:
    columns = ["Name", "Area", "Collection", "Rating", "Source", "Mode"]
    values = [[row["name"], row["area"] or "", row["collection"] or "",
               "unrated" if row["rating"] is None else f"{row['rating']}/5",
               row["source"], row["mode"]] for row in rows]
    widths = [max(len(row[i]) for row in [columns, *values]) for i in range(len(columns))]
    previous = None
    for row, values_row in zip(rows, values):
        key = group_key(row, group_by)
        if previous != key:
            if previous is not None:
                print()
            if group_by != "none":
                print(group_label(row, group_by))
            print("  ".join(value.ljust(width) for value, width in zip(columns, widths)).rstrip())
            previous = key
        print("  ".join(value.ljust(width) for value, width in zip(values_row, widths)).rstrip())


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def metadata_lock(root: Path):
    # Keep the persistent lock outside the editable Git/iCloud worktree.
    import hashlib

    key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()
    lock = Path(tempfile.gettempdir()) / f"fleet-skill-metadata-{os.getuid()}-{key}.lock"
    with lock.open("a") as handle:
        deadline = time.monotonic() + 5
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError("skill metadata is busy; retry after the other write finishes")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def update(home: Path, name: str, value: object, *, clear: bool) -> dict:
    root = source_root(home)
    if root is None:
        raise ValueError("editable skill source is unavailable; change metadata on the source owner")
    if not clear:
        value = score(value)
    with metadata_lock(root):
        if name not in source_catalog(root, home=home):
            raise ValueError(f"unknown active skill: {name}")
        path = root / METADATA_RELATIVE
        records = read_metadata(path)
        record = records.setdefault(name, {})
        if clear:
            record.pop("rating", None)
        else:
            record["rating"] = value
        if not record:
            del records[name]
        atomic_json(path, {"schema_version": 1, "skills": records})
    return {"name": name, **records.get(name, {})}


def exported_metadata(root: Path, inventory: list[dict]) -> dict:
    records = read_metadata(root / METADATA_RELATIVE)
    included = {item["name"] for item in inventory if item["status"] == "included"}
    return {"schema_version": 1, "skills": {
        name: records[name] for name in sorted(included & records.keys())
    }}
