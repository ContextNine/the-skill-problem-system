#!/usr/bin/env python3
"""Render explicit Fleet expressions in Markdown owned by one bundle."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


TOKEN = re.compile(r"(?<!\\)(\{\{.*?\}\}|\{%.*?%\})", re.DOTALL)
FIELD = re.compile(r"[a-zA-Z_][a-zA-Z_0-9]*(?:\.[a-zA-Z_][a-zA-Z_0-9]*)*")
VARIANT = re.compile(r"[a-z][a-z0-9]*")
INCLUDE = re.compile(r'''include\s+["'](templates/[a-zA-Z0-9_./-]+\.md)["']''')
FOR = re.compile(r"for\s+([a-zA-Z_][a-zA-Z_0-9]*)\s+in\s+(fleet\.[a-zA-Z_0-9.]+)")
EQUALITY = re.compile(r'''(fleet\.[a-zA-Z_0-9.]+)\s*==\s*["']([^"']+)["']''')


class FleetTemplateError(ValueError):
    pass


def has_fleet_syntax(content: str) -> bool:
    if ("\\{{ fleet." in content or "\\{% include \"templates/" in content
            or "\\{% if fleet." in content or "\\{% for " in content):
        return True
    return any(
        token.startswith("{{ fleet.")
        or INCLUDE.fullmatch(token[2:-2].strip()) is not None
        or (token.startswith("{% if ") and token[2:-2].strip()[3:].strip().startswith("fleet."))
        or (token.startswith("{% for ") and FOR.fullmatch(token[2:-2].strip()) is not None)
        for token in TOKEN.findall(content)
    )


def bundle_has_templates(bundle: Path) -> bool:
    return any(
        has_fleet_syntax(path.read_text(encoding="utf-8"))
        for path in bundle.rglob("*.md")
        if "templates" not in path.relative_to(bundle).parts and not path.is_symlink()
    )


def _lookup(expression: str, scope: Mapping[str, Any], source: Path, *, optional: bool = False) -> Any:
    if not FIELD.fullmatch(expression):
        raise FleetTemplateError(f"invalid field {expression!r} in {source}")
    value: Any = scope
    for part in expression.split("."):
        if not isinstance(value, Mapping) or part not in value:
            if optional:
                return None
            raise FleetTemplateError(f"missing field {expression!r} in {source}")
        value = value[part]
    return value


def _include_path(bundle: Path, raw: str, variants: list[str], source: Path) -> Path:
    relative = PurePosixPath(raw)
    if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] != "templates":
        raise FleetTemplateError(f"include escapes {bundle}: {raw!r} in {source}")
    for variant in reversed(variants):
        if not VARIANT.fullmatch(variant):
            raise FleetTemplateError(f"invalid template variant {variant!r} in {source}")
        candidate = bundle / relative.with_name(f"{relative.stem}.{variant}.md")
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    candidate = bundle / relative
    if candidate.is_file() and not candidate.is_symlink():
        return candidate
    raise FleetTemplateError(f"missing include {raw!r} for {source}")


def _parse(tokens: list[str], position: int, source: Path, stops: set[str],
           locals_in_scope: frozenset[str] = frozenset()) -> tuple[list[tuple], int, str | None]:
    nodes: list[tuple] = []
    while position < len(tokens):
        token = tokens[position]
        position += 1
        if token.startswith("{%"):
            directive = token[2:-2].strip()
            keyword = directive.split(maxsplit=1)[0] if directive else ""
            if keyword in stops:
                return nodes, position, keyword
            if keyword in {"else", "endif", "endfor"}:
                nodes.append(("text", token))
                continue
            if keyword == "include":
                match = INCLUDE.fullmatch(directive)
                if not match:
                    raise FleetTemplateError(f"invalid include in {source}: {directive}")
                nodes.append(("include", match.group(1)))
                continue
            if keyword == "if":
                expression = directive[3:].strip()
                if not expression.startswith("fleet.") and expression.split(".", 1)[0] not in locals_in_scope:
                    nodes.append(("text", token))
                    continue
                if not (EQUALITY.fullmatch(expression) or FIELD.fullmatch(expression)):
                    raise FleetTemplateError(f"invalid condition in {source}: {expression}")
                yes, position, stop = _parse(tokens, position, source, {"else", "endif"}, locals_in_scope)
                if stop is None:
                    raise FleetTemplateError(f"unclosed if in {source}")
                no: list[tuple] = []
                if stop == "else":
                    no, position, stop = _parse(tokens, position, source, {"endif"}, locals_in_scope)
                    if stop != "endif":
                        raise FleetTemplateError(f"unclosed if in {source}")
                nodes.append(("if", expression, yes, no))
                continue
            if keyword == "for":
                match = FOR.fullmatch(directive)
                if not match:
                    raise FleetTemplateError(f"invalid loop in {source}: {directive}")
                body, position, stop = _parse(tokens, position, source, {"endfor"},
                                              locals_in_scope | {match.group(1)})
                if stop != "endfor":
                    raise FleetTemplateError(f"unclosed for in {source}")
                nodes.append(("for", match.group(1), match.group(2), body))
                continue
            nodes.append(("text", token))
        elif token.startswith("{{"):
            expression = token[2:-2].strip()
            if expression.startswith("fleet."):
                nodes.append(("value", expression))
            elif FIELD.fullmatch(expression):
                nodes.append(("local-or-text", expression, token))
            else:
                nodes.append(("text", token))
        else:
            nodes.append(("text", token.replace("\\{{", "{{").replace("\\{%", "{%")))
    return nodes, position, None


def _render(nodes: list[tuple], scope: Mapping[str, Any], bundle: Path, source: Path,
            variants: list[str], stack: tuple[Path, ...]) -> str:
    output: list[str] = []
    for node in nodes:
        kind = node[0]
        if kind == "text":
            output.append(node[1])
        elif kind == "value":
            value = _lookup(node[1], scope, source)
            output.append("" if value is None else str(value))
        elif kind == "local-or-text":
            name = node[1].split(".", 1)[0]
            value = _lookup(node[1], scope, source) if name in scope and name != "fleet" else node[2]
            output.append("" if value is None else str(value))
        elif kind == "include":
            included = _include_path(bundle, node[1], variants, source)
            output.append(render_file(bundle, included, scope, variants, stack=stack))
        elif kind == "if":
            equality = EQUALITY.fullmatch(node[1])
            selected = (_lookup(equality.group(1), scope, source, optional=True) == equality.group(2)) if equality else bool(_lookup(node[1], scope, source, optional=True))
            output.append(_render(node[2] if selected else node[3], scope, bundle, source, variants, stack))
        elif kind == "for":
            values = _lookup(node[2], scope, source)
            if not isinstance(values, list):
                raise FleetTemplateError(f"loop value is not a list in {source}: {node[2]}")
            for value in values:
                output.append(_render(node[3], {**scope, node[1]: value}, bundle, source, variants, stack))
    return "".join(output)


def render_file(bundle: Path, source: Path, context: Mapping[str, Any], variants: list[str],
                *, stack: tuple[Path, ...] = ()) -> str:
    bundle = bundle.resolve()
    resolved = source.resolve()
    if resolved in stack:
        raise FleetTemplateError(f"include cycle: {' -> '.join(map(str, (*stack, resolved)))}")
    if bundle not in resolved.parents or not source.is_file() or source.is_symlink():
        raise FleetTemplateError(f"template source escapes bundle: {source}")
    nodes, _, stop = _parse(TOKEN.split(source.read_text(encoding="utf-8")), 0, source, set())
    if stop is not None:
        raise FleetTemplateError(f"unexpected {stop} in {source}")
    content = _render(nodes, context, bundle, source, variants, (*stack, resolved))
    if source.name == "SKILL.md" and (not content.startswith("---\n") or "\n---\n" not in content[4:]):
        raise FleetTemplateError(f"rendered skill frontmatter is invalid: {source}")
    return content


def render_markdown_tree(bundle: Path, context: Mapping[str, Any], variants: list[str]) -> None:
    """Render Fleet-marked Markdown in a staged copy, leaving authored files untouched."""
    for path in sorted(bundle.rglob("*.md")):
        if "templates" in path.relative_to(bundle).parts or path.is_symlink():
            continue
        if has_fleet_syntax(path.read_text(encoding="utf-8")):
            path.write_text(render_file(bundle, path, context, variants), encoding="utf-8")
