#!/usr/bin/env python3
"""Render colocated fleet templates without evaluating code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


SEPARATOR = "\n\n***\n\n"
ALLOWED_FORMATS = {"markdown", "json", "text"}
ALLOWED_SELECTORS = {"platform", "role", "machine_id"}


class FleetTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedFile:
    target: str
    content: str
    fragment_ids: tuple[str, ...]


def _safe_path(bundle_root: Path, raw: object, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise FleetTemplateError(f"{label} must be a non-empty relative path")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in {"", "."}:
        raise FleetTemplateError(f"{label} escapes its owning bundle: {raw!r}")
    candidate = bundle_root.joinpath(*relative.parts)
    resolved_root = bundle_root.resolve()
    resolved = candidate.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise FleetTemplateError(f"{label} escapes its owning bundle: {raw!r}")
    return candidate


def _format(value: str, variables: Mapping[str, object], label: str) -> str:
    try:
        return value.format_map(dict(variables))
    except KeyError as exc:
        raise FleetTemplateError(f"{label} uses unknown variable {exc.args[0]!r}") from exc
    except ValueError as exc:
        raise FleetTemplateError(f"{label} has invalid template syntax: {exc}") from exc


def _matches(raw: object, context: Mapping[str, object], label: str) -> bool:
    if raw is None:
        return True
    if not isinstance(raw, dict) or not raw:
        raise FleetTemplateError(f"{label} when must be a non-empty object")
    unknown = set(raw) - ALLOWED_SELECTORS
    if unknown:
        raise FleetTemplateError(f"{label} has unsupported selectors: {sorted(unknown)}")
    for key, expected in raw.items():
        accepted = expected if isinstance(expected, list) else [expected]
        if not accepted or not all(isinstance(item, str) and item for item in accepted):
            raise FleetTemplateError(f"{label} selector {key!r} must use a string or string list")
        if str(context.get(key) or "") not in accepted:
            return False
    return True


def _read(path: Path, label: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise FleetTemplateError(f"{label} is missing or not a real file: {path}")
    return path.read_text(encoding="utf-8")


def _validate_content(target: str, file_format: str, content: str) -> None:
    if file_format == "json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            raise FleetTemplateError(f"rendered JSON is invalid for {target}: {exc}") from exc
    if target.endswith("/SKILL.md") or target == "SKILL.md":
        if not content.startswith("---\n"):
            raise FleetTemplateError(f"rendered skill has no frontmatter: {target}")
        end = content.find("\n---\n", 4)
        if end == -1:
            raise FleetTemplateError(f"rendered skill frontmatter is incomplete: {target}")


def load_config(config_path: Path) -> dict[str, Any]:
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FleetTemplateError(f"fleet template config is missing: {config_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise FleetTemplateError(f"fleet template config is invalid: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise FleetTemplateError("fleet template config needs schema_version 1")
    outputs = value.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise FleetTemplateError("fleet template config needs a non-empty outputs list")
    return value


def render_bundle(
    bundle_root: Path,
    config_path: Path,
    variables: Mapping[str, object],
    *,
    additional_fragments: Sequence[tuple[str, Path]] = (),
    managed_metadata: bool = False,
) -> list[RenderedFile]:
    """Render every explicit output for one owning bundle."""
    bundle_root = bundle_root.resolve()
    config = load_config(config_path)
    outputs = config["outputs"]
    rendered: list[RenderedFile] = []
    targets: set[str] = set()
    for index, raw_output in enumerate(outputs):
        label = f"outputs[{index}]"
        if not isinstance(raw_output, dict):
            raise FleetTemplateError(f"{label} must be an object")
        target_path = _safe_path(bundle_root, raw_output.get("target"), f"{label} target")
        target = target_path.relative_to(bundle_root).as_posix()
        if target in targets:
            raise FleetTemplateError(f"duplicate fleet template output target: {target}")
        targets.add(target)
        file_format = raw_output.get("format", "text")
        if file_format not in ALLOWED_FORMATS:
            raise FleetTemplateError(f"{label} has unsupported format: {file_format!r}")
        base_raw = raw_output.get("base")
        template_raw = raw_output.get("template")
        if (base_raw is None) == (template_raw is None):
            raise FleetTemplateError(f"{label} needs exactly one of base or template")
        if template_raw is not None:
            template_path = _safe_path(bundle_root, template_raw, f"{label} template")
            content = _format(_read(template_path, f"{label} template"), variables, str(template_path))
            fragment_ids: list[str] = []
        else:
            base_path = _safe_path(bundle_root, base_raw, f"{label} base")
            parts = [_read(base_path, f"{label} base").rstrip()]
            fragment_ids = []
            raw_fragments = raw_output.get("fragments", [])
            if not isinstance(raw_fragments, list) or not all(isinstance(item, dict) for item in raw_fragments):
                raise FleetTemplateError(f"{label} fragments must be an object list")
            selected: list[tuple[str, Path]] = []
            for fragment_index, fragment in enumerate(raw_fragments):
                fragment_label = f"{label} fragments[{fragment_index}]"
                if not _matches(fragment.get("when"), variables, fragment_label):
                    continue
                fragment_id = _format(str(fragment.get("id") or ""), variables, f"{fragment_label} id")
                if not fragment_id:
                    raise FleetTemplateError(f"{fragment_label} needs an id")
                path = _safe_path(bundle_root, fragment.get("path"), f"{fragment_label} path")
                selected.append((fragment_id, path))
            selected.extend(additional_fragments)
            if len({item[0] for item in selected}) != len(selected):
                raise FleetTemplateError(f"{label} selected duplicate fragment ids")
            fragment_ids.extend(item[0] for item in selected)
            if managed_metadata:
                metadata = "<!-- fleet.managed instruction-fragments: base"
                if fragment_ids:
                    metadata += "," + ",".join(fragment_ids)
                parts.append(metadata + " -->")
            for fragment_id, path in selected:
                parts.append(_format(_read(path, f"fragment {fragment_id}"), variables, str(path)).strip())
            content = SEPARATOR.join(parts) + "\n"
        _validate_content(target, str(file_format), content)
        rendered.append(RenderedFile(target, content, tuple(fragment_ids)))
    return rendered
