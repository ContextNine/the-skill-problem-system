---
type: agent-reference
status: enabled
---

## Code Workspace Catalog Schema

The private or installed `fleet/workspaces.json` uses schema version 2 and Code-root-relative entries:

```json
{
  "schema_version": 2,
  "default_profile": "core",
  "defaults": {
    "clone_mode": "partial",
    "profiles": ["core"],
    "machines": ["*"],
    "codex_project_root": "."
  },
  "entries": {
    "example": {
      "path": "example",
      "discovery": "repository",
      "remote": "git@github.com:owner/example.git"
    },
    "group": {
      "path": "group",
      "discovery": "recursive"
    }
  }
}
```

### Fields

- `schema_version`: must be `2`.
- `default_profile`: profile used when the command receives no `--profile` or `--entry`.
- `defaults`: values inherited by every entry.
- `entries.<id>.path`: relative path below each selected machine's Code root; absolute paths, `~` and `..` are invalid.
- `discovery`: `repository` for one checkout, or `recursive` for every physical Git checkout below the path. Dynamic `--path` uses `auto`.
- `remote`: optional canonical remote for `repository`; required to bootstrap when the source checkout is absent. Recursive members discover their own remotes.
- `profiles`: catalog profiles that select the entry.
- `machines`: target machine IDs or `"*"`.
- `clone_mode`: `partial` or `full`; partial adds `git clone --filter=blob:none` and keeps full history.
- `codex_project_root`: `.` by default. A relative subdirectory may identify the folder to save as the Codex project.
- `required`: when true, missing source paths or empty recursive discovery are reported prominently.

Paths outside the configured source Code root, overlapping parent/child repositories, credential-bearing remotes, duplicate target-relative paths, and one canonical remote assigned to multiple desired paths are invalid. Recursive discovery skips known dependency, build, cache, `.workspace-sync`, symlinked, and already-discovered repository subtrees; pass an excluded directory itself with `--path` when it intentionally owns repositories. A recursive entry is intentionally source-observed; use exact entries with `remote` when bootstrap must work without that source collection being present.

Personal-fleet GitHub entries use canonical `git@github.com:OWNER/REPO.git` URLs. HTTPS and SSH forms retain the same repository identity, but an existing literal HTTPS checkout is transport drift and must be reconciled only through the documented preflighted migration.

When a thin workspace repository contains ignored child Git repositories and owns its own manifest/sync command, keep that hierarchy in one ownership layer. Do not select both the parent and its children in this catalog. If an installed local Codex marketplace lives in one child, select that exact child here so plugin reconciliation can guarantee its target-local path, and leave the remaining workspace membership to the owning workspace manifest.

For exact entries, `remote` is also the stable identity used to detect a uniquely moved source checkout. Applying with `--adopt-source-layout` updates that entry's relative `path`; it never rewrites the remote or changes recursive entries.

### Logical references from dependencies

`dependencies/selections.json` may refer to an owning checkout only through `workspace: <entries ID>`. Its installer is repository-relative. Never copy `entries.<id>.path`, an expanded home path, or a remote URL into a dependency entry. The sync worker resolves the logical ID against this catalog on each machine and rejects unknown IDs or escaping installer paths.

The aggregate dependency lock may contain resolved command paths because it records verified actual state. Those observed paths are disposable evidence, not source identity and never input to reconciliation. This boundary permits future checkout relocation or replacement of a workspace-built tool by a published package without changing its logical dependency identity prematurely.
