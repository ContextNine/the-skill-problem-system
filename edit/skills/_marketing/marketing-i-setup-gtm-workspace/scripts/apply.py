#!/usr/bin/env python3
"""Copy missing GTM or personal-brand scaffold files into a Vault context."""

from __future__ import annotations

import argparse
from pathlib import Path


BUSINESS_PACK = Path("_system/bootstrap/templates/context-folders/business")
PERSONAL_BRAND_PACK = Path("_system/bootstrap/templates/context-folders/personal-brand")
BUSINESS_ROOTS = ("company", "gtm", "relationships", "_obsidian/bases")


def vault_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "_system").is_dir():
            return candidate
    raise SystemExit("Run this script from inside the Vault.")


def validate_context(root: Path, context: str) -> Path:
    if not context or Path(context).name != context:
        raise SystemExit("Context must be one registered top-level folder name.")
    context_root = root / context
    note = context_root / f"{context}.md"
    if not note.is_file():
        raise SystemExit(f"Not a registered context folder: {context}")
    return context_root


def selected_sources(pack: Path, identity_type: str) -> list[Path]:
    if identity_type == "personal-brand":
        return sorted(path for path in (pack / "brand").rglob("*") if path.is_file())
    sources: list[Path] = []
    for root_name in BUSINESS_ROOTS:
        source_root = pack / root_name
        if source_root.is_file():
            sources.append(source_root)
        elif source_root.is_dir():
            sources.extend(path for path in source_root.rglob("*") if path.is_file())
    return sorted(sources)


def destination_relative(relative: Path, context_root: Path) -> Path:
    if relative.parts and relative.parts[0] == "gtm":
        existing = next(
            (path.name for path in context_root.iterdir() if path.is_dir() and path.name.lower() == "gtm"),
            "gtm",
        )
        return Path(existing, *relative.parts[1:])
    return relative


def apply(context: str, identity_type: str, *, write: bool) -> int:
    root = vault_root()
    context_root = validate_context(root, context)
    pack_relative = PERSONAL_BRAND_PACK if identity_type == "personal-brand" else BUSINESS_PACK
    pack = root / pack_relative
    changed = 0
    for source in selected_sources(pack, identity_type):
        relative = destination_relative(source.relative_to(pack), context_root)
        target = context_root / relative
        if target.exists():
            continue
        if source.name == ".gitkeep" and target.parent.is_dir():
            continue
        action = "copy" if write else "[dry-run] copy"
        print(f"{action} {target.relative_to(root)}")
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            content = source.read_bytes().replace(b"{{context}}", context.encode("utf-8"))
            target.write_bytes(content)
        changed += 1
    if changed == 0:
        print(f"{context}: current")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--identity-type", choices=("company", "personal-brand"), required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return 0 if apply(args.context, args.identity_type, write=args.apply) >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
