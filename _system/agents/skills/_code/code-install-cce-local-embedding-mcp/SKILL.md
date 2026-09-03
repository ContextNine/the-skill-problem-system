---
name: code-install-cce-local-embedding-mcp
description: Installs and verifies Code Context Engine (CCE) as a local embedding-backed MCP server for a selected code repository, defaulting to Codex. Use when the user explicitly asks to install CCE, enable local semantic code search, add the CCE MCP, or configure Code Context Engine for Codex or another named coding agent.
---

# Code · Install CCE Local Embedding MCP

Install the maintained Code Context Engine from https://github.com/elara-labs/code-context-engine in one explicitly selected code repository.

## Safety

- Resolve the exact target repository first. Use `$infra-i-code-folder-and-computer-topology` only when its path or owning machine is unclear.
- Do not target the Obsidian Vault unless the user explicitly overrides a warning that CCE may modify managed `AGENTS.md`, Git hooks, and Codex configuration.
- Read the target repository's `AGENTS.md` and README breadcrumbs before mutation. Preserve unrelated work and stop if CCE would overlap dirty or generated instruction files.
- State before running that CCE may update the project `AGENTS.md`, Git hooks, a local index, and the selected agent's MCP configuration.
- Default to Codex. Configure `all` or another agent only when the user requests it.

## Workflow

1. Open the maintained upstream README and release history. Confirm its current installation command, supported Python versions, target-agent flag, and files changed. Do not use a stale fork.
2. In the target repository, inspect Git status and whether `AGENTS.md` is a regular editable file. Run prerequisite checks without reading secrets:

```bash
uv --version
uv python list --only-installed
xcode-select -p  # macOS only
```

3. If a prerequisite is missing, report it and request authorization before installing system tooling. Do not silently install Homebrew, `uv`, Python, Xcode tools, CMake, or Ollama.
4. Review the current installer help, then run the upstream local-embedding setup from the target repository. For Codex, the expected command is:

```bash
uvx --from "code-context-engine[local]" cce init --agent codex
```

Use the current upstream equivalent if the documented CLI has changed. Use a persistent `uv tool install` only when the user asks for a persistent binary.
5. Inspect every repository change plus the relevant MCP configuration. Confirm existing `AGENTS.md` instructions were preserved and that CCE registered only the requested repository and agent.
6. Verify with the current equivalents of `cce status`, a representative `cce search`, and `codex mcp list`. Do not treat installation as complete when the index or MCP registration is unhealthy.
7. Follow the target repository's Git completion rules. Tell the user to restart Codex or open a new task because the current task's MCP and skill catalog may be cached.

If setup partially fails, preserve the diagnostic output and use the upstream uninstall command only after confirming exactly which CCE-owned artifacts it will remove.
