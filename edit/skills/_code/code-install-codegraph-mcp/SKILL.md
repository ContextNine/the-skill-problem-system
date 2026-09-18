---
name: code-install-codegraph-mcp
description: Use when the user asks to install CodeGraph, add local code-graph search, configure the CodeGraph MCP for Codex or another coding agent, or initialize a repository's CodeGraph index.
---

# Code · Install CodeGraph MCP

Install and configure CodeGraph from https://github.com/colbymchenry/codegraph for one explicitly selected repository.

## Safety

- Resolve the exact target repository first. Use `$fleet-i-code-folder-and-computer-topology` only when its path or owning machine is unclear.
- Do not target the Obsidian Vault unless the user explicitly asks to index its supported code and accepts modifying managed agent configuration. CodeGraph does not index Markdown, so it cannot search the Vault's notes or documentation.
- Read the target repository's `AGENTS.md` and README breadcrumbs before mutation. Preserve unrelated work and stop if CodeGraph would overlap dirty `AGENTS.md` or `.codex/config.toml` changes.
- State before setup that a local Codex install updates `AGENTS.md` and `.codex/config.toml`, while `codegraph init` creates the local `.codegraph/` index.
- Default to Codex with project-local configuration. Use global configuration, `all`, or another agent only when the user requests it.
- Installation alone must not initialize a repository, start the UI, or leave an MCP server, watcher, or daemon running.
- CodeGraph telemetry defaults to enabled. Keep it off unless the user explicitly opts in.

## Workflow

1. Open the maintained upstream README, release history, installer, and telemetry documentation. Confirm the current release, supported platforms, CLI flags, and files changed. Do not use an unreviewed installer or stale fork.
2. Check `codegraph --version`, `codegraph telemetry status`, and the process table before changing anything. When installation is requested, use a reviewed checkout of the official repository at the release pinned in the typed dependency registry. Confirm that the release checksums in `_system/agents/internal/defaults/dependencies.json` match upstream before running its installer. Never pipe a remote script directly into a shell:

```bash
CODEGRAPH_VERSION=v1.6.0 sh /absolute/path/to/codegraph/install.sh
codegraph telemetry off
codegraph --version
```

Use the current pinned version rather than copying the example version blindly. The upstream installer verifies the release archive checksum and installs the CLI under `~/.codegraph`, with a launcher in `~/.local/bin`. If the user requested only the CLI, stop here. Confirm that no CodeGraph process remains.

3. In the selected repository, inspect Git status, `AGENTS.md`, `.codex/config.toml`, `.gitignore`, and any existing `codegraph.json` or `.codegraph/` directory. Print CodeGraph's proposed Codex config before writing it:

```bash
codegraph install --target codex --location local --print-config codex
```

4. Configure only Codex in that repository, then inspect the exact diff and confirm unrelated instructions and MCP entries remain intact:

```bash
codegraph install --target codex --location local --yes
```

5. CodeGraph honors `.gitignore` and its built-in dependency, build, cache, and size exclusions. Add `codegraph.json` only when tracked generated or vendored paths need `exclude`, or lower-priority helper trees need `deprioritize`. `exclude` removes paths from the graph; `deprioritize` keeps them findable but lowers their rank. Prefer `deprioritize` when vendored code is the only source available to inspect. Do not add speculative configuration.

6. Initialize and build the graph only after the user selected the repository:

```bash
codegraph init --yes /absolute/path/to/repository
```

The command exits after indexing. The file watcher runs only while an agent-launched `codegraph serve --mcp` process is connected. Do not run `codegraph ui` or manually start a daemon unless requested.

7. Verify with `codegraph status --json /absolute/path/to/repository`, a representative `codegraph explore` query, `codex mcp list`, Git status, and a process check. Do not report success if the index or MCP registration is unhealthy.

8. Follow the repository's Git completion rules. Tell the user to restart Codex or open a new task so it loads the project-local MCP configuration.

For removal, inspect the exact target first. `codegraph uninit --force /absolute/path/to/repository` deletes that repository's `.codegraph/` index. `codegraph uninstall --target codex --location local --keep-cli --yes` removes the local Codex configuration while preserving the CLI. Do not remove broader agent configuration or the CLI unless the user explicitly requests it.
