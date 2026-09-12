---
type: agent-reference
status: enabled
---

## Primary Mac onboarding and acceptance

Use this route when creating, rebuilding, replacing, or recovering the fleet's single primary Mac. Read [[shared-onboarding-and-acceptance|Shared Onboarding and Acceptance]] first.

The primary is the only Mac that owns Vault Git, commits and pushes the Vault, performs pointer-only media maintenance, runs `vault refresh`, and distributes personal agent configuration. A replacement is not accepted until that authority is singular and verified.

### Procedure

1. Confirm whether this is an additive rebuild, a replacement of the registered primary, or disaster recovery. Never erase a Mac or retire the former primary without explicit authorization and verified backups.
2. Follow `_system/bootstrap/README.md` for the base Mac and Vault installation. Use the full iCloud Vault working folder; never create `<resolved Code root>/vault`.
3. Restore or create the primary's machine-local external Git directory at `~/.local/share/vault-git/Vault.git` through the documented Vault Git recovery workflow. Never place that directory in iCloud or copy it to a worker.
4. Verify the shared Vault `.git` file resolves to that external directory only on this Mac. Confirm no other active Mac retains a resolvable Vault Git directory.
5. Set clone-local `vault.machine-id` to the reviewed primary registry ID. Update `primary_machine_id` only as an explicit role-transfer decision, keeping the previous primary disabled until the handoff is complete.
6. Install and verify versioned Git hooks, pointer-only media mode, the media manifest, `origin`, and required local LFS bodies before treating GitHub as a durable metadata backup.
7. Configure primary-side SSH, the explicitly selected personal machine-access provider, Screen Sharing, aliases, and operator dependencies through [[primary-mac-remote-access-prerequisites|Primary Machine Remote Access Prerequisites]] and owning infrastructure repositories. Configure any separate WireGuard cluster route independently; it must not silently become the canonical fleet SSH route.
8. Authenticate Codex, Claude, GitHub, and required providers locally. The primary `~/.codex/AGENTS.md`, `~/.codex/config.toml`, and `~/.claude/settings.json` become authoritative only after review and verification.
9. Run `$infra-i-sync-code-workspaces` in preview and doctor modes against reachable reviewed workers; do not force a fleet rollout merely to accept the primary.
10. Install and verify the primary-only refresh schedule after Vault Git, iCloud materialization, hooks, media state, and machine identity all pass.

### Acceptance

- `vault.machine-id` equals `primary_machine_id`, and the registry contains exactly one primary role.
- The full iCloud Vault is materialized and its `.git` pointer resolves to the expected machine-local external Git directory.
- `vault git-preflight`, `vault git-media verify --ref HEAD`, `fleet sync --dry-run`, fetch, and push verification pass.
- Required local LFS bodies are present; no Git LFS upload is attempted for the private pointer-only Vault.
- Refresh scheduling is primary-eligible and installed exactly once.
- Code workspace and agent configuration source files validate, while authentication and session state remain local.
- Reboot preserves iCloud materialization, Vault Git resolution, hooks, media verification, remote access, and refresh eligibility.

If replacing a former primary, disable its fleet entry or change its role before enabling the new primary, remove its external Vault Git authority only after verified handoff, and record the transfer in both machine notes.
