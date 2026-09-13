---
name: infra-i-update-fleet-dependencies
description: Coordinates complete approved dependency, coding-tool, skill-source, workspace-command, application, provider, and public Vault updates across enabled fleet machines. Use when updating everything, aligning fleet dependencies, updating fleet software, or deciding which specialist update workflow owns a dependency.
---

# Infra · Update Fleet Dependencies

## Route the operation

Read [Code Folder and Computer Topology](../infra-i-code-folder-and-computer-topology/SKILL.md), [Agent and Fleet Dependencies](references/dependencies.md), the package's `internal/defaults/dependencies.json`, and Agent Update. The dependency reference owns the registry and lifecycle contract; use its routed lifecycle pages for the selected dependency. Resolve installed configuration with `fleet config`; never construct a private Vault path. This skill is the human-facing umbrella; `fleet update` is the sole fleet update CLI.

- Use the default command for every approved update class on every enabled, agent-eligible machine.
- Use selectors or repeatable `--target` only when the request narrows the operation.
- Invoke [Update Fleet Coding Tools](../infra-i-update-fleet-coding-tools/SKILL.md) whenever `--coding-tools` is selected. It owns Codex provenance, exact T3 nightly alignment, native artifact acceptance, and service-manager handling.
- Route manual application, privilege, login, privacy, or restart checkpoints to the selected dependency's lifecycle reference. Do not turn a checkpoint into an inferred installer command.
- Never target a disabled machine, broaden “everything” to undeclared software, or include production deployment, credential rotation, major OS upgrades, firmware, or account authentication.

## Execute

Start with one immutable preview:

```bash
fleet update --dry-run
```

Resolve blockers without resetting, stashing, overwriting, installing undeclared software, or changing credentials. Apply only after the preview can be accepted:

```bash
fleet update
```

For a new adapter or risky channel, preview and verify fixtures first, then roll out to one named non-primary machine before the enabled fleet. A failed or manual item remains visible and prevents an aligned-fleet claim.

## Report

Return the command scope and a compact matrix of machine, dependency or source, before, after, method, status, blocker, and manual action. Distinguish updated, already current, lifecycle-owned, not installed, and failed. Do not claim fleet alignment unless the command's final sync and verification both pass.
