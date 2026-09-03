---
type: agent-reference
status: enabled
---

## Shared onboarding and acceptance

“Add,” “onboard,” “enroll,” “rebuild,” “replace,” or “recover” a machine means integrate it into the complete personal fleet. Registration alone is not completion.

For a rebuild, preserve the existing machine identity only after confirming it still represents the same physical and operational role. Give a genuinely new machine a new identity. Never reuse another machine's SSH, WireGuard, or Tailscale identity.

### Start

1. Read [[README-primary-worker-vault-sync|Primary and Worker Vault Coordination]], the topology observations README, `_system/agents/_package/instance/fleet/machines.json`, `_system/agents/_package/instance/fleet/workspaces.json`, and `_system/agents/_package/instance/dependencies/selections.json`.
2. Establish whether the target is a primary Mac, worker Mac, or Linux worker, and whether it is new, rebuilt, replaced, or recovered.
3. Select the matching role document and closest private Machine Convention. If no convention fits, define the role decision before mutation.
4. Confirm ownership, architecture, home directory, purpose, access exposure, Vault participation, and any separately authorized destructive installation.
5. Create or update the private machine note with confirmed facts, decisions, evidence, exceptions, and unresolved work.

### Shared gates

Keep a new or rebuilt target disabled until every applicable gate passes:

- **Identity:** unique machine ID, display name, hostname, role, platform, architecture, home, convention, and private note.
- **Dependencies:** supported OS and architecture, shell and noninteractive PATH, fleet commands, Git, GitHub CLI, Codex, Claude, and role-specific tools.
- **Access:** explicit WireGuard or Tailscale choice per target, unique provider identity, reviewed LAN and selected mesh routes, source-aware canonical aliases rendered on every enabled machine, SSH host identity, password fallback disabled, applicable screen access, a fresh reverse-forward proof from every worker to the canonical primary alias, and the complete [[fleet-shell-mesh|Fleet Shell Mesh]] across enabled machines.
- **Registry:** complete disabled record with notes path, transport, SSH alias, home, role, platform, Vault policy, terminal profile, and optional verified VNC definition.
- **Authentication:** follow [[machine-local-secrets-and-enrollment|Machine-local Secrets and Enrollment]] for every selected capability. Prove target-local Codex, Claude, GitHub, and ctx9 GitLab read authentication with the registered custody and acceptance route; keep credentials, sessions, consent, and privacy grants machine-local.
- **Development sync:** run `$infra-i-sync-code-workspaces` from the primary with the explicit onboarding target after authentication. The same apply owns repositories and personal Codex and Claude convergence.
- **Coding apps:** on the primary, add Codex desktop and T3 Code connections with the registry's canonical `ssh_alias`, save the intended project roots under that host identity, and verify one rendered test thread. Treat `-lan` and `-mesh` aliases as route diagnostics, not saved application identities.
- **Skills and terminal:** verify role-appropriate skill availability, then use `$infra-i-manage-fleet-terminal-workspaces` for terminal profiles and saved workspaces.
- **Topology record:** update the private note and [[machine-requirements-and-topology|Machine Requirements and Topology]] only with confirmed current facts.

### Acceptance

1. Reboot and rerun hostname, dependency, authentication, access-route, terminal, development-sync, Vault, agent, and applicable screen/startup checks.
2. Run `vault machine list`, `vault machine status MACHINE_ID`, workspace-sync `doctor`, terminal verification, and the selected role document's acceptance commands.
3. Resolve every failed gate or record the exact blocker and next human action. Mark optional exclusions deliberately with reasons.
4. Set `enabled: true` and reviewed agent-configuration eligibility only after acceptance passes.
5. Finish with a compact report of completed, excluded, and blocked gates and where evidence was recorded.

Ask only for choices that materially affect identity, role, destructive installation, access exposure, or optional capabilities. A password, MFA, CAPTCHA, Touch ID, or protected approval is a temporary handoff, not permission to abandon the remaining workflow.
