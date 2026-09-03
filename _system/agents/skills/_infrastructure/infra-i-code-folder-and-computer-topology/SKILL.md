---
name: infra-i-code-folder-and-computer-topology
description: Discovers the current clone, registered primary and worker machines, connection routes, repository locations, and code-placement policy without provisioning machines. Use when identifying a machine, finding where code lives or belongs, inspecting fleet topology, resolving an SSH or Screen Sharing route, or supplying topology facts to another infrastructure workflow.
---

# Infra · Code Folder and Computer Topology

Read [[README-primary-worker-vault-sync|Primary and Worker Vault Coordination]] for fleet roles, registry routing, Vault host boundaries, and safe Git behavior. Linux machines are Code-only unless schema v7 explicitly selects `remote-sshfs`; that registered mode uses the full exact-path mount described by [[README-vault-host-boundary|Vault Host Boundary]] and [[linux-remote-vault-access|Linux Remote Vault Access]].

Read [[README-github-fleet-authentication|GitHub Fleet Authentication]] before auditing, provisioning, enrolling, verifying, rotating, or revoking GitHub credentials, or changing GitHub Git transport.

- Resolve configuration with `ctx9-agents config path` and validate it with `ctx9-agents config validate`. Read the topology config README beneath `skills/config/infra-i-code-folder-and-computer-topology`, then `fleet/machines.json` and `fleet/workspaces.json`. In the private Vault source these live under `_system/agents/_package/instance`; installed skills must not assume that source path. If configuration is missing, keep fleet automation inactive and show setup guidance.
- Resolve primary identity through local Git setting `vault.machine-id`. Resolve a Gitless iCloud worker or remote client through `~/.config/vault/machine-id`. Never infer identity from hostname when another workflow may mutate remote machines.
- Read a machine's linked `private_notes_path` only when machine-specific facts matter.
- Treat registry roles as generic: one `primary`, zero or more `worker` machines.
- Resolve each machine's absolute Code and Vault roots through `ctx9-agents config get fleet.machines.<id>.roots.<code|vault>`. For `remote-sshfs`, derive the source alias and source Vault root from `vault.remote_access.source_machine_id`; never duplicate them in the client record. Resolve repositories by logical workspace ID; every workspace path is Code-root-relative. Do not hardcode homes, roots, machine IDs, source hosts, or checkout locations into other skills.
- Treat each registry `ssh_alias` as the stable identity consumed by Codex, T3, terminal, sync, and update workflows. Route-specific `-lan`, `-mesh`, hostnames, and addresses are diagnostic overrides and must not become durable application identities.
- Treat `skills/skill-sources.json` repository-skill choices as an explicit allowlist consumed by agent sync. Resolve its literal `~/` paths per machine; never infer enrollment from `workspaces.json` or link across machines.
- Rediscover mutable facts before use and record confirmed private observations in the linked private machine note when the user asks for documentation changes.
- Read [[README-machine-runtime-state|Machine Runtime State]] before assigning machine-local logs, state, locks, caches, or runtime files.
- Read the owning repository `AGENTS.md` and `README.md` before repository changes; keep project-specific operations in that repository.
- For repeat or onboarding synchronization of Code repositories and personal Codex/Claude configuration from the primary, use `$infra-i-sync-code-workspaces`; topology supplies facts but performs no deployment.
- For onboarding, rebuilding, replacing, recovering, or accepting any machine role, use `$infra-i-onboard-machine`.
- For Warp, cmux, tmux, workmux, terminal profiles, or terminal notifications, use `$infra-i-manage-fleet-terminal-workspaces`.
- Keep this skill generic and exported. Keep registries, private notes, addresses, aliases, and personal operational references excluded.
