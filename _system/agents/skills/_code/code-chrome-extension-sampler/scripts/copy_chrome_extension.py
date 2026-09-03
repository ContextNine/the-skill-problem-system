#!/usr/bin/env python3
"""Copy an installed Chrome extension into a named samples folder."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VAULT_ROOT = Path(__file__).resolve().parents[6]
DEFAULT_CONFIG = VAULT_ROOT / "_system/agents/_package/instance/skills/config/code-chrome-extension-sampler/private/config.json"
EXTENSION_ID_RE = re.compile(r"^[a-p]{32}$")


@dataclass(frozen=True)
class Candidate:
    source: Path
    profile: str
    version: str
    manifest_path: Path
    is_archive: bool = False


def parse_args() -> argparse.Namespace:
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    config_args, _ = config_parser.parse_known_args()
    config = load_json(config_args.config.expanduser())
    if config.get("schema_version") != 1:
        fail(f"unsupported config schema: {config_args.config}")
    default_target = Path(str(config["target"])).expanduser()
    default_chrome_user_data = Path(str(config["chrome_user_data"])).expanduser()
    parser = argparse.ArgumentParser(
        parents=[config_parser],
        description="Copy a Chrome extension by ID from Chrome profile data to a samples folder."
    )
    parser.add_argument("extension_id", help="Chrome extension ID, for example emdlbnkhjpfcooclfbodmhkhkohcjaoa")
    parser.add_argument("--target", type=Path, default=default_target, help=f"Destination samples folder. Default: {default_target}")
    parser.add_argument(
        "--chrome-user-data",
        type=Path,
        default=default_chrome_user_data,
        help=f"Chrome user data folder. Default: {default_chrome_user_data}",
    )
    parser.add_argument("--profile", help="Specific Chrome profile folder name, for example Default or Profile 1")
    parser.add_argument("--version", help="Specific installed extension version folder, for example 1.4.78_0")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing destination folder")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        fail(f"could not parse JSON at {path}: {exc}")
    except OSError as exc:
        fail(f"could not read {path}: {exc}")


def version_key(version: str) -> tuple[Any, ...]:
    parts = re.split(r"([0-9]+)", version)
    key: list[Any] = []
    for part in parts:
        if not part:
            continue
        key.append(int(part) if part.isdigit() else part)
    return tuple(key)


def iter_profile_dirs(chrome_user_data: Path, profile: str | None) -> list[Path]:
    if profile:
        profile_dir = chrome_user_data / profile
        if not profile_dir.exists():
            fail(f"Chrome profile does not exist: {profile_dir}")
        return [profile_dir]

    if not chrome_user_data.exists():
        fail(f"Chrome user data folder does not exist: {chrome_user_data}")

    profile_dirs: list[Path] = []
    for child in sorted(chrome_user_data.iterdir()):
        if (child / "Extensions").is_dir():
            profile_dirs.append(child)
    return profile_dirs


def find_candidates(extension_id: str, chrome_user_data: Path, profile: str | None, version: str | None) -> list[Candidate]:
    candidates: list[Candidate] = []
    for profile_dir in iter_profile_dirs(chrome_user_data.expanduser(), profile):
        extension_dir = profile_dir / "Extensions" / extension_id
        if not extension_dir.exists():
            continue

        if version:
            version_dirs = [extension_dir / version]
        else:
            version_dirs = [item for item in extension_dir.iterdir() if item.is_dir()]

        for version_dir in version_dirs:
            manifest_path = version_dir / "manifest.json"
            if manifest_path.exists():
                candidates.append(
                    Candidate(
                        source=version_dir,
                        profile=profile_dir.name,
                        version=version_dir.name,
                        manifest_path=manifest_path,
                    )
                )

        for archive in extension_dir.glob("*.crx"):
            candidates.append(Candidate(source=archive, profile=profile_dir.name, version=archive.stem, manifest_path=archive, is_archive=True))
        for archive in extension_dir.glob("*.zip"):
            candidates.append(Candidate(source=archive, profile=profile_dir.name, version=archive.stem, manifest_path=archive, is_archive=True))

    return candidates


def choose_candidate(candidates: list[Candidate]) -> Candidate:
    if not candidates:
        fail("no installed extension files were found for that ID")
    return sorted(candidates, key=lambda item: (version_key(item.version), item.source.stat().st_mtime), reverse=True)[0]


def sanitize_folder_name(name: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f:/\\]+", "-", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" .")
    return cleaned[:120] or "unknown-extension"


def localized_message(root: Path, locale: str, message_key: str) -> str | None:
    messages_path = root / "_locales" / locale / "messages.json"
    if not messages_path.exists():
        return None
    messages = load_json(messages_path)
    value = messages.get(message_key)
    if isinstance(value, dict) and isinstance(value.get("message"), str):
        return value["message"]
    return None


def resolve_manifest_name(root: Path, manifest: dict[str, Any]) -> str | None:
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    match = re.fullmatch(r"__MSG_([^_]+(?:_[^_]+)*)__", name)
    if not match:
        return name.strip()

    message_key = match.group(1)
    locales: list[str] = []
    default_locale = manifest.get("default_locale")
    if isinstance(default_locale, str):
        locales.append(default_locale)
    locales.extend(["en", "en_US", "en_GB"])

    locales_dir = root / "_locales"
    if locales_dir.exists():
        locales.extend(child.name for child in sorted(locales_dir.iterdir()) if child.is_dir())

    seen: set[str] = set()
    for locale in locales:
        if locale in seen:
            continue
        seen.add(locale)
        resolved = localized_message(root, locale, message_key)
        if resolved:
            return resolved.strip()
    return None


def extract_crx_or_zip(archive: Path, destination: Path) -> None:
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(destination)
        return

    data = archive.read_bytes()
    if data[:4] != b"Cr24":
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(destination)
        return

    crx_version = struct.unpack("<I", data[4:8])[0]
    if crx_version == 2:
        public_key_length, signature_length = struct.unpack("<II", data[8:16])
        zip_start = 16 + public_key_length + signature_length
    elif crx_version == 3:
        header_length = struct.unpack("<I", data[8:12])[0]
        zip_start = 12 + header_length
    else:
        fail(f"unsupported CRX version {crx_version}: {archive}")

    with tempfile.NamedTemporaryFile(suffix=".zip") as temp_zip:
        temp_zip.write(data[zip_start:])
        temp_zip.flush()
        with zipfile.ZipFile(temp_zip.name) as zip_file:
            zip_file.extractall(destination)


def prepare_source(candidate: Candidate) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if not candidate.is_archive:
        return candidate.source, None

    temp_dir = tempfile.TemporaryDirectory(prefix="chrome-extension-sampler-")
    extract_dir = Path(temp_dir.name)
    extract_crx_or_zip(candidate.source, extract_dir)
    if not (extract_dir / "manifest.json").exists():
        fail(f"archive did not contain manifest.json: {candidate.source}")
    return extract_dir, temp_dir


def copy_source(source_root: Path, destination: Path, overwrite: bool) -> None:
    if destination.exists():
        if not overwrite:
            fail(f"destination already exists, pass --overwrite to replace it: {destination}")
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root, destination, symlinks=True)


def main() -> None:
    args = parse_args()
    extension_id = args.extension_id.strip().lower()
    if not EXTENSION_ID_RE.fullmatch(extension_id):
        fail(f"invalid Chrome extension ID: {args.extension_id}")

    candidates = find_candidates(extension_id, args.chrome_user_data, args.profile, args.version)
    candidate = choose_candidate(candidates)
    source_root, temp_dir = prepare_source(candidate)

    try:
        manifest = load_json(source_root / "manifest.json")
        extension_name = resolve_manifest_name(source_root, manifest) or extension_id
        destination = args.target.expanduser() / sanitize_folder_name(extension_name)
        copy_source(source_root, destination, args.overwrite)

        result = {
            "extension_id": extension_id,
            "extension_name": extension_name,
            "source": str(candidate.source),
            "source_profile": candidate.profile,
            "source_version": candidate.version,
            "destination": str(destination),
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Copied {extension_name}")
            print(f"From: {candidate.source}")
            print(f"Profile: {candidate.profile}")
            print(f"Version: {candidate.version}")
            print(f"To: {destination}")
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    main()
