# Agent internals

Users normally edit the sibling `edit/` directory. This directory contains the implementation and generated outputs:

- `src/`: Fleet CLI, renderer, installer, sync, update, and export code.
- `src/skill_catalog.py`: offline skill browsing, ratings, areas/collections, and filtered public metadata. Skill snapshots distribute a derived catalog separately from skill content.
- `schemas/` and `defaults/`: validation and public-safe starter data.
- `tests/`: integration and package tests.
- `repairs/`: reviewed, explicit host-package repairs, including the [GNOME Secret Service missing-client fix](repairs/gnome-keyring-50.0/README.md).
- `release/`: public repository mappings, installer, README, license, and version metadata.
- `generated/`: catalog links, overlays, snapshots, locks, and backups. Never edit these as source.

Operating procedures live in their owning skills. The Fleet templating contract is owned by `$skills-i-write-or-edit-a-skill` in `references/fleet-templating.md`.

Validate source changes with:

```bash
python3 _system/agents/internal/src/fleet.py config validate
fleet sync --dry-run
```

Installed Fleet state lives only under `~/.agents/`. Public release work uses `vault release publish --product skills` or the coordinated `--product all` workflow.

Authenticated private component preflight and exact-adoption ownership follow README-private-component-preflight. Source checks do not authorize installation or change a daily Fleet runtime.

The shared maintenance runtime is `src/maintenance_runtime.py`. The K3s skill scripts load this installed package. It owns machine-local queues, mutation locks, private run records and configurable coding-agent execution. Triage starts in the registered Vault after its access check; Cluster Wizard starts in the infrastructure checkout. `src/maintenance_issues.py` delivers sanitized unfinished outcomes to GitHub or GitLab independently of the coding agent. See README-maintenance for timers, configuration, issue delivery, state ownership and verification.

`src/maintenance_ai.py` owns value-free managed-profile requests and existing-checkout execution. `src/ai_quality/` owns generic Langfuse triage, trace export, redaction and native runtime-error collection. Repository adapters supply managed credentials and environment/retention mappings. The declared `maintenance-tsx` and `maintenance-zod` dependencies run these collectors without depending on an application's node_modules. Focused verification:

```bash
python3 -m unittest discover -s internal/tests -p test_maintenance_runtime.py
NODE_PATH="$HOME/.local/lib/node_modules" tsx --test internal/tests/maintenance_ai.integration.test.ts
```
