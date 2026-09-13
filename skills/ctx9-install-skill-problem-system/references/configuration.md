# Configuration

Editable desired configuration lives in the repository's `edit/settings/`. Run `fleet sync --dry-run`, then `fleet sync` to project it into the installed settings directory printed by `fleet config path`. The installed copy is not another editing location.

Machine records own the absolute home plus `~`-relative Code and optional Vault roots. Workspace paths are relative to the selected machine's Code root. Use `fleet config get fleet.machines.<id>.resolved_roots.code` and the corresponding Vault key to read resolved paths.

Integration files contain stable non-secret metadata only. Credentials remain in approved machine-local custody. Machine-local state lives under `~/.agents/state/` and never belongs in the editable repository.
