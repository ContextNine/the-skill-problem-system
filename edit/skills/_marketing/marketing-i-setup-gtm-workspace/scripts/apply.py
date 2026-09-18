#!/usr/bin/env python3
"""Copy missing GTM or personal-brand scaffold files into a Vault teamspace."""

from __future__ import annotations

import argparse
from pathlib import Path


BUSINESS_PACK = Path("_system/templates/teamspaces/business")
PERSONAL_BRAND_PACK = Path("_system/templates/teamspaces/personal-brand")
GTM_PACK = Path("_system/templates/gtm/scaffold")
BUSINESS_ROOTS = ("company",)
RELATIONSHIP_ROOTS = ("relationships", "_obsidian/bases")


def vault_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "_system").is_dir():
            return candidate
    raise SystemExit("Run this script from inside the Vault.")


def validate_context(root: Path, context: str) -> Path:
    if not context or Path(context).name != context:
        raise SystemExit("Teamspace must be one registered top-level folder name.")
    context_root = root / context
    note = context_root / f"{context}.md"
    if not note.is_file():
        raise SystemExit(f"Not a registered teamspace folder: {context}")
    return context_root


def selected_sources(pack: Path, identity_type: str, *, relationships: bool) -> list[Path]:
    if identity_type == "personal-brand":
        return sorted(path for path in (pack / "brand").rglob("*") if path.is_file())
    sources: list[Path] = []
    for root_name in (*BUSINESS_ROOTS, *(RELATIONSHIP_ROOTS if relationships else ())):
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


def apply(context: str, identity_type: str, *, write: bool, relationships: bool = False) -> int:
    root = vault_root()
    context_root = validate_context(root, context)
    pack_relative = PERSONAL_BRAND_PACK if identity_type == "personal-brand" else BUSINESS_PACK
    pack = root / pack_relative
    if not pack.is_dir():
        raise SystemExit(f"Missing teamspace pack: {pack}")
    gtm_pack = root / GTM_PACK
    if identity_type == "company" and not gtm_pack.is_dir():
        raise SystemExit(f"Missing GTM scaffold: {gtm_pack}")
    changed = 0
    sources = [(source, pack) for source in selected_sources(pack, identity_type, relationships=relationships)]
    if identity_type == "company":
        sources.extend((source, gtm_pack) for source in sorted(gtm_pack.rglob("*")) if source.is_file())
    for source, source_root in sources:
        relative = destination_relative(source.relative_to(source_root), context_root)
        target = context_root / relative
        if target.exists():
            continue
        if source.name == ".gitkeep" and target.parent.is_dir():
            continue
        action = "copy" if write else "[dry-run] copy"
        print(f"{action} {target.relative_to(root)}")
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            content = source.read_bytes().replace(b"{{teamspace}}", context.encode("utf-8"))
            target.write_bytes(content)
        changed += 1
    if changed == 0:
        print(f"{context}: current")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teamspace", dest="context", required=True)
    parser.add_argument("--identity-type", choices=("company", "personal-brand"), required=True)
    parser.add_argument("--relationships", action="store_true", help="Also add missing relationship CRM files for a company.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.relationships and args.identity_type != "company":
        parser.error("--relationships applies only to company teamspaces")
    return 0 if apply(args.context, args.identity_type, write=args.apply, relationships=args.relationships) >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
