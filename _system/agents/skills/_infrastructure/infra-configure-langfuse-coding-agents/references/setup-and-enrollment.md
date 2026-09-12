---
type: agent-reference
status: enabled
---

## Langfuse coding-agent setup and enrollment

Langfuse exposes two independent coding-agent integrations:

| Capability | Direction | Codex | Claude Code |
| --- | --- | --- | --- |
| Session observability | Agent session to Langfuse | Official `tracing@codex-observability-plugin` Stop hook | Official `langfuse-observability@langfuse-observability` Stop/SessionEnd hooks |
| Authenticated project access | Agent to Langfuse API | Authenticated MCP or Langfuse CLI | Authenticated MCP or Langfuse CLI |

Public Langfuse documentation access is a third, unauthenticated capability and does not expose the private instance. Do not confuse it with either row above.

Current upstream references:

- https://langfuse.com/integrations/developer-tools/codex
- https://langfuse.com/integrations/developer-tools/claude-code
- https://langfuse.com/docs/api-and-data-platform/features/mcp-server
- https://langfuse.com/agents/agents

### Instance metadata

The selected agent configuration owns `integrations/langfuse.json` beneath `fleet config path`. Agent configuration sync installs it at `~/.config/ctx9/fleet/integrations/langfuse.json` on eligible machines. It contains only instance ID, enabled state, HTTPS base URL when enabled, credential-registry ID, and capture defaults.

The scaffold may create `~/.codex/langfuse.json` only when absent, with `enabled: false`, the base URL, environment, tags, and bounds. It must not add `public_key` or `secret_key`. If that file already exists, the scaffold does not read, replace, merge, or verify its contents.

### Dependencies

- Codex 0.128 or newer and Node.js 22 or newer for the Codex plugin.
- Claude Code and either `uv` or Python 3.10 plus Langfuse SDK 4.x for the Claude plugin. The official Claude hook uses `uv` to resolve and cache its declared SDK automatically.
- Network access to the configured self-hosted HTTPS endpoint.

Node 24 and `uv` are approved direct agent dependencies in `_system/agents/_package/defaults/dependencies.json`. Codex and Claude Code are managed coding tools, not package-manifest dependencies. The scaffold refuses missing commands and never installs a missing coding tool or package manager.

### Install the disabled scaffold

From the skill directory:

```bash
python3 scripts/install_scaffold.py --dry-run
python3 scripts/install_scaffold.py
python3 scripts/install_scaffold.py --verify
```

Apply installs the official Codex marketplace/plugin, enables the Codex `hooks` feature, installs the official Claude marketplace/plugin, disables the unconfigured Claude plugin, and creates the non-secret disabled Codex stub only when absent. Codex's hook is inert while `enabled` is false and no credentials exist. Claude remains disabled until enrollment.

Plugin hook trust is separate from plugin installation. Review the exact Codex hook through `/hooks` after an update; do not bypass hook trust merely to complete setup.

### Credential lifecycle

`langfuse-coding-agent-api` is `reissued`, not guarded-copy. Create a distinct project-scoped key pair for each selected machine through self-hosted Langfuse administration. Deliver it once into native custody, verify the target, and revoke the replaced pair only after acceptance. Never copy another machine's stored credential or reuse an application runtime key as a fleet-machine key.

Do not create separate lifecycle manifests. `_system/agents/_package/instance/fleet/machine-secrets.json` is the single non-secret registry; its `class`, `machines`, `purpose`, `documentation`, custody, verification, and recovery fields make onboarding behavior filterable without duplicating IDs.

### Claude enrollment

The official Claude plugin marks its secret option sensitive and stores it in the OS keychain. On the target, start Claude Code and run:

```text
/plugin configure langfuse-observability@langfuse-observability
```

Enter a target-specific public key, secret key, and the configured self-hosted base URL. Keep skill-content and image capture off unless separately reviewed. Then enable the plugin for the user scope and restart Claude Code.

Do not use the documented `@inline` GUI workaround because it stores the secret in plaintext Claude settings. If GUI plugin identity prevents Keychain delivery, keep GUI tracing disabled and wait for an upstream or native-custody fix.

### Codex and MCP enrollment boundary

The current official Codex plugin accepts shell environment values or plaintext `~/.codex/langfuse.json`. Those are not approved persistent fleet custody. Keep its disabled stub in place until an owning helper can load a target-specific key from macOS Keychain or Linux Secret Service into the hook process without synchronizing or persisting the value.

The authenticated Langfuse MCP requires a Basic authorization header derived from the project keys. Do not write that header into synchronized `~/.codex/config.toml`, Claude settings, this skill, or instance metadata. Enable authenticated MCP only after the same native-store helper can provide the header dynamically and both clients' configuration formats have been verified.

### Acceptance and recovery

After native enrollment:

1. Confirm the plugin and hook are enabled on the exact target.
2. Run one harmless turn containing no sensitive source or user data.
3. Find the resulting trace in the configured Langfuse instance and confirm machine/user labeling, tool observations, truncation, and capture policy.
4. For authenticated data access, list a bounded non-sensitive resource such as prompts and confirm the expected project.
5. Record only sanitized readiness, custody kind, key identifier or expiry when public, and verification time in `_system/agents/_package/generated/state/machine-secrets.lock.json` through the owning procedure.

On compromise or loss, issue a replacement target-specific pair, enroll and verify it, then revoke the prior pair. Removing a plugin or local config does not revoke a Langfuse credential.
