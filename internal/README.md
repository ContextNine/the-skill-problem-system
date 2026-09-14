# Agent internals

Users normally edit the sibling `edit/` directory. This directory contains the implementation and generated outputs:

- `src/`: Fleet CLI, renderer, installer, sync, update, and export code.
- `schemas/` and `defaults/`: validation and public-safe starter data.
- `tests/`: integration and package tests.
- `release/`: public repository mappings, installer, README, license, and version metadata.
- `generated/`: catalog links, overlays, snapshots, locks, and backups. Never edit these as source.

Operating procedures live in their owning skills. The Fleet templating contract is owned by `$agents-i-write-or-edit-a-skill` in `references/fleet-templating.md`.

Validate source changes with:

```bash
python3 _system/agents/internal/src/fleet.py config validate
fleet sync --dry-run
```

Installed Fleet state lives only under `~/.agents/`. Public release work uses `vault release publish --product skills` or the coordinated `--product all` workflow.
