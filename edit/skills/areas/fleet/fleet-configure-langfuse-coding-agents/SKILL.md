---
name: fleet-configure-langfuse-coding-agents
description: Use when the user asks to trace Codex or Claude Code sessions in Langfuse, configure the official observability plugins, enroll machine-specific keys, verify traces and costs, temporarily pause or enable tracing across the fleet, or remove a tracing integration.
---

# Fleet · Configure Langfuse Coding Agents

Read `./references/setup-and-enrollment.md` before configuring, enabling, rotating or removing an integration. Instance metadata belongs in `integrations/langfuse.json` below `fleet config path`; credential lifecycle belongs in `fleet/machine-secrets.json`. Neither contains credentials.

Use the official observability plugins. Codex loads its machine-specific project keys directly from local `~/.codex/langfuse.json`, with mode 0600, outside Git and fleet sync. Matt explicitly approved this plaintext local configuration on 2026-10-10. Do not install a custom launcher, credential loader or replacement Stop hook. Claude retains its native plugin configurator and OS custody; change it only when requested.

Tracing sends full conversation and tool contents. Enable it only for the machines and material the user authorizes. Review the exact official hook normally, then verify two harmless turns in a fresh session against server-side traces, machine labels, provider usage and model prices. CLI verification does not establish desktop acceptance; restart Codex and verify a fresh desktop chat separately.

When replacing functionality, remove obsolete hooks, launchers, local state and code, delete only the superseded native credential items, and revoke replaced project keys after the new setup passes. Update the registry, references and installed skills together. Authenticated MCP access is a separate capability and remains disabled until explicitly configured.

## Temporarily pause or enable Codex tracing

For a fleet-wide request, use the registered machines with Codex tracing configured. On each machine, change only `enabled` in its local `~/.codex/langfuse.json`: `false` pauses uploads; `true` enables them. Preserve that machine's keys and settings, write atomically with mode 0600, and never print or synchronize the file. Keep the official plugin installed and trusted.

Follow the pause/resume section in `./references/setup-and-enrollment.md` for overrides and verification. Report each machine's result, including unreachable machines. Start a fresh chat when enabling again: resuming a chat used while paused can upload its previously unuploaded turns.
