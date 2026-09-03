---
name: infra-configure-langfuse-coding-agents
description: Configures Langfuse observability and authenticated data access for Codex and Claude Code. Use when the user asks to install Langfuse coding-agent plugins, trace coding sessions, connect an agent to Langfuse, enroll Langfuse agent credentials, or verify coding-agent traces.
---

# Infra · Configure Langfuse Coding Agents

Read [[setup-and-enrollment|Setup and Enrollment]] before installing, enabling, authenticating, or removing either integration.

The two capabilities are separate: observability plugins send Codex or Claude Code sessions to Langfuse; authenticated MCP or CLI access lets an agent query Langfuse data. Never treat a public docs MCP connection as project-data access.

Non-secret instance metadata lives at `integrations/langfuse.json` below `ctx9-agents config path`. Credential ownership and lifecycle live in `fleet/machine-secrets.json` below the same private or installed config root. Neither file may contain an API key or authorization header. Keep the integration disabled until an authoritative personal HTTPS endpoint is configured; never inherit an application-specific endpoint by guesswork.

Use `scripts/install_scaffold.py` to install the official plugins without credentials and leave tracing unable to transmit:

```bash
python3 scripts/install_scaffold.py --dry-run
python3 scripts/install_scaffold.py
python3 scripts/install_scaffold.py --verify
```

Credential enrollment is a manual checkpoint. Claude may be enabled only after its plugin configurator stores the secret through native OS custody. Keep Codex tracing and authenticated MCP disabled until an approved Keychain or Secret Service loader supplies values without persistent plaintext.

After enrollment, verify one deliberately harmless test turn, locate its exact Langfuse trace, and update sanitized machine acceptance through the owning onboarding workflow. Never enable tracing for sessions whose prompts, code, tool input, or tool output must not be retained in Langfuse.
