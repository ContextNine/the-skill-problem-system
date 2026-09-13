---
type: agent-reference
status: enabled
---

## Fleet agent configuration sync

This is the only source of truth for distributing personal Codex and Claude Code configuration from the registered primary to reviewed fleet machines. Initial onboarding and normal Code workspace reconciliation use the same script and contract.

### Ownership

| Responsibility | Owner |
|---|---|
| Machine identity, role, platform, home, transport, eligibility | `_system/agents/edit/settings/fleet/machines.json` |
| Repositories and personal agent configuration convergence | `$infra-i-sync-code-workspaces` |
| New-machine gate ordering | `$infra-i-onboard-machine` |
| Worker-Mac applications, GUI consent, and unattended-operation checks | `$infra-i-onboard-machine` worker-Mac route |
| tmux, workmux, Warp, cmux, and terminal profiles | `$infra-i-manage-fleet-terminal-workspaces` |
| Approved recipes and private dependency choices | package `defaults/dependencies.json` plus config `dependencies/selections.json` |
| Versioned global instructions and fleet projection | `edit/root-agents/`, its colocated templates, and agent sync |
| Repo-owned skill selection and portable fleet snapshots | `fleet sync --skills` |

Other repositories own their local `.agents/skills` sources. `skill-sources.json` independently chooses which are globally enrolled and owns their fleet-distribution policy; `workspaces.json` only registers and reconciles repositories.

### Managed configuration

The Vault source and primary home settings are authoritative:

| Source | Target | Behavior |
|---|---|---|
| source `edit/settings/` | `~/.agents/settings/` | Atomically projects the authoritative value-free fleet, workspace, dependency-selection, skill-source, and integration configuration |
| source `edit/root-agents/` | `~/.agents/instructions/AGENTS.md` | Deterministic managed instructions with exact machine identity plus absolute Code and Vault roots |
| source `edit/settings/integrations/langfuse.json` | `~/.agents/settings/integrations/langfuse.json` | Non-secret Langfuse instance metadata and disabled-integration intent; no keys or authorization header |
| `~/.codex/config.toml` | `~/.codex/config.toml` | Primary settings and raw `[mcp_servers.*]`, with the primary home path rebased; target-local `[plugins.*]` and `[marketplaces.*]` are preserved |
| Rendered `~/.agents/instructions/AGENTS.md` | `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md` | Relative symlinks, so personal instructions have one output |
| `~/.claude/settings.json` | `~/.claude/settings.json` | All user settings, with the primary home path rebased to the target home |

Machine sections identify the selected machine, platform, role, enabled peers, connection route, exact resolved Code root, exact resolved Vault root or disabled state, and configured GUI access. When another enabled fleet machine exists, the renderer adds development-preview guidance that binds on worker loopback and reverse-forwards to the registered primary's loopback through its configured SSH alias. Single-machine registries omit that guidance. No machine identity or home path is embedded in this reusable skill.

For a macOS worker, the rendered Codex config enforces `approval_policy = "never"`, `sandbox_mode = "danger-full-access"`, and `[mcp_servers.computer-use] enabled = true`. All other primary settings remain intact. These are target-role overlays, not a second configuration source.

Authentication, OAuth state, sessions, logs, caches, memories, trust databases outside `config.toml`, macOS privacy grants, and Claude's `~/.claude.json` never sync. Inline credential-like `env` values and credential-bearing URLs fail closed before any target mutation. Store shared secrets through their owning env/SOPS workflow and authenticate each machine locally.

Plugin tables are not ordinary configuration. The Codex CLI owns them on each host, while [[plugin-reconciliation|Fleet Codex Plugin Reconciliation]] derives portable desired state from the registered primary and converges installations after repository reconciliation. Primary marketplace timestamps, revisions, cache roots, and runtime paths are never copied into a target config.

### When it runs

`bootstrap`, `reconcile`, and `refresh` preview or apply agent configuration for every selected eligible target. `doctor` verifies it. The explicit onboarding form accepts one disabled reviewed target with `--provision-disabled`; ordinary runs require enabled targets with `global_agents_eligible: true`.

This is convergence on each normal sync run, not a background daemon. `fleet sync` applies approved dependencies, workspaces, workspace-built commands, skills, settings, and instructions to every enabled target by default. Changes made in generated home files are backed up and replaced by the versioned source on the next apply. Each changed target path receives an adjacent UTC-stamped backup before atomic replacement.

### Commands

Normal repository and configuration convergence:

```bash
SKILL_DIR="$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-sync-code-workspaces"
python3 "$SKILL_DIR/scripts/sync_code_workspaces.py" reconcile --target MACHINE
python3 "$SKILL_DIR/scripts/sync_code_workspaces.py" reconcile --target MACHINE --apply
python3 "$SKILL_DIR/scripts/sync_code_workspaces.py" doctor --target MACHINE
```

Configuration-only diagnosis or repair:

```bash
python3 "$SKILL_DIR/scripts/sync_agent_configuration.py" --target MACHINE
python3 "$SKILL_DIR/scripts/sync_agent_configuration.py" --target MACHINE --apply
python3 "$SKILL_DIR/scripts/sync_agent_configuration.py" --target MACHINE --verify
```

During onboarding, add `--provision-disabled` to the explicit target command. After Code reconciliation, run `fleet sync`; for acceptance, require `fleet sync --dry-run --require-repo-sources` first. Linux workers receive point-in-time global skill copies over SSH independently of Vault access. A code-only worker requires no Vault; a registered remote client never follows skill links into its mount.

### Compatibility and rollback

The topology command owns the current registry schema and its migrations. Sync consumers accept any positive integer registry `schema_version` and validate only the fields they use, so an additive registry migration does not break them. A removed or incompatible required field still fails with its exact missing-field error.

To roll back one target file, stop Codex and Claude Code on that machine, restore the chosen adjacent `.backup-<UTC>` path, then rerun configuration preview. Never copy authentication or session files as part of rollback.
