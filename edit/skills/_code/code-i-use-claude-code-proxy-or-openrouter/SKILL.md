---
name: code-i-use-claude-code-proxy-or-openrouter
description: Use when the user asks to run Claude Code through a proxy, OpenRouter, Kimi, Codex OAuth, Featherless, an alternate model provider, or a model slug.
---

# Code · Use Claude Code proxy or OpenRouter

Read [Claude Provider Routes](references/README-claude-provider-routes.md) before changing launchers, provider authentication, CLIProxyAPI routing, or fleet acceptance.

- Canonical launchers, the installer, and focused tests live in `scripts/` here. Do not keep provider-launcher copies or SOPs in onboarding, terminal, or general Claude configuration skills.
- Direct `claude` remains unchanged. Provider variables exist only in the launcher child process.
- Keep provider credentials machine-local. Use `scripts/claude-provider-auth` through a real terminal and never print, copy, or persist keys in the Vault.
- Kimi Platform and OpenRouter use native Anthropic-compatible endpoints. `claude-kimi-proxy` preserves the Kimi OAuth route through the shared CLIProxyAPI service. Featherless exposes an OpenAI-compatible endpoint, so its launcher uses the already-approved CLIProxyAPI binary as an isolated loopback translator.
- Do not install a missing Claude Code, `curl`, `jq`, Python, Secret Service, or CLIProxyAPI dependency. Report the missing dependency and stop at that acceptance gate.
- Install locally with `scripts/install-claude-provider-launchers.sh`; pass one canonical SSH alias to install on another enabled machine.
- Verify command resolution, credential status, route banner, Claude `/status`, and one bounded live tool-use request before recording acceptance.
- `$fleet-i-onboard-machine` consumes this capability during machine setup. It does not own these files or procedures.
