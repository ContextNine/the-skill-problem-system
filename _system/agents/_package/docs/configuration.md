# Configuration

Private desired configuration lives under the directory printed by `fleet config path`. It is separate from package runtime and is never part of a public package export.

Machine records own the absolute home plus `~`-relative Code and optional Vault roots. Workspace paths are relative to the selected machine's Code root. Use `fleet config get fleet.machines.<id>.resolved_roots.code` and the corresponding Vault key to read resolved paths.

Integration files contain stable non-secret metadata only. Credentials remain in approved machine-local custody.
