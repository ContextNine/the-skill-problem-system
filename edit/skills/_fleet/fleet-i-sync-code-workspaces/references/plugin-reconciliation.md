---
type: agent-reference
status: enabled
---

## Fleet Codex plugin reconciliation

Primary machine's installed plugin list is desired state. Applied `bootstrap`, `reconcile`, and `refresh` runs normalize `codex plugin marketplace list --json` plus `codex plugin list --json`, preflight every target, reconcile repositories, then reconcile plugins.

### Ownership

- Primary-owned: installed plugin IDs, enabled state, plugin versions, marketplace source identity, and resolved Git revisions.
- Codex CLI-owned per host: `[plugins.*]`, `[marketplaces.*]`, downloaded marketplaces, plugin caches, and runtime-bundled sources.
- Machine-local: Codex and connector authentication, OAuth, desktop-app sessions, and runtime availability.
- Fleet-owned record: `<resolved Code root>/.workspace-sync/plugin-state.json`, containing only plugins and marketplaces previously managed by this workflow.

Agent configuration sync copies normal settings and `[mcp_servers.*]`, but removes primary `[plugins.*]` and `[marketplaces.*]` subtrees before merging the target's exact local copies. Never copy `~/.codex/plugins/cache`, `~/.codex/.tmp`, auth, or session state.

### Portable sources

- Git marketplace: record the source URL and exact checked-out SHA. Targets validate a temporary checkout before replacing a broken or stale registration.
- Registered local repository: require the repository beneath Primary machine's Code root to be selected for workspace sync, then install from the equivalent target-local path after repository reconciliation.
- OpenAI bundled, curated, or primary runtime: verify and install through the target Codex runtime. Never project Primary machine runtime paths.
- Other local path: stop before fleet mutation with an unsupported-source error.

Only plugins in the prior machine-local fleet record are eligible for removal when absent from Primary machine. Unknown target-local plugins remain untouched. A marketplace remains when any installed target plugin still uses it.

### Preflight and repair

An apply starts only after every target passes SSH, Codex CLI/config parsing, Git repository access, Git marketplace access, and target-local marketplace path checks. A desired broken marketplace is repairable even when `codex plugin list --json` cannot read its missing cache: marketplace metadata is inspected independently, the exact revision is downloaded to a temporary checkout, `.agents/plugins/marketplace.json` is validated, and only then is the old registration replaced and its plugins reinstalled.

The distributed run is idempotent, not atomic. A later host race can still fail after preflight; per-machine output and state make reruns safe.

### Readiness

Report installation separately from local connection state:

```text
installed-and-ready
installed-authentication-required
installed-runtime-unavailable
installation-failed
unsupported-platform
```

Authentication is never copied. A plugin with machine-local auth policy is not reported ready until that local requirement is satisfied.

Runtime marketplaces are platform-specific. Reconciliation reads each target's actual marketplace manifest before installing a runtime plugin. When Primary machine's desired plugin is not published there, preserve any existing installation and report `unsupported-platform` without failing the fleet run or repeatedly attempting installation.

`paper-desktop@paper` needs Paper Desktop logged in with a file open and its MCP listener on `127.0.0.1:29979`. The plugin can be installed while that runtime is unavailable. macOS Intel receives the plugin but reports `unsupported-platform` for local Paper Desktop; a Primary machine MCP tunnel remains an optional separate workflow because it would operate Primary machine's open file.
