# Workspace synchronization ownership

The portable workspace controller and target worker live in
`../edit/skills/_fleet/fleet-i-sync-code-workspaces/scripts/`.

Fleet reconciles registered repositories from canonical remotes. It does not
copy dirty working trees, ENV values or Git metadata between machines.
CodeFolderSync independently owns working-file synchronization within a signed
namespace after normal cutover.

## Scoped guard

For each selected repository, inspect its `.codefoldersync/config.json` and
every containing directory through the Code root. Read only the bounded public
projection. Require schema/protocol V3, matching physical namespace, an external
state directory, local enrollment, authority/signature fields, and an explicit
valid `syncPolicy`. This structural guard is not signature verification or a
replacement for CodeFolderSync's own admission checks.

Default-branch and selected-files normal namespaces both make covered
repositories read-only to Fleet. Adoption leaves workspace ownership in place.
Malformed controls, missing policies and unsafe directory paths fail closed.
Recheck target ownership before each repository operation. Source ownership
must remain unchanged across fleet preflight before source mutation starts.

A protected source carries a read-only instruction to every selected target.
A target independently checks its own namespace too. This prevents repository
refresh or cloning into a sync-owned scope merely because only one side has
finished cutover. Matching relocation candidates are checked before movement;
normal namespaces cannot be moved out through workspace reconciliation.

## Mixed selections

Protected repositories can report local checkout, staging and remote-head
drift. Inspection uses optional-lock-free Git reads and `ls-remote`, never
`fetch`. Dirty or remote-drift attention remains visible without blocking an
unrelated repository's mutation preflight.

Unprotected siblings retain ordinary clone, relocation and clean fast-forward
behavior. A wholly protected selection returns `codefoldersync-report-only`
with no history. A mixed run may write machine-local `.workspace-sync` state at
the Code root, outside the protected namespace. Agent configuration and plugin
changes remain preview-only if any selected source or target namespace is
protected. Authentication and sessions never transfer.

## Verification

The existing `test_workspace_reconciliation.py` controller flow exercises both
policy modes with one protected source and an unrelated selected repository.
It verifies per-repository target instructions, continued unrelated apply,
read-only agent/plugin handling, and recorded mixed-run history. A wholly
protected target is handled without requiring or appending mutation history.
The existing relocation flow also preserves a positive checkout witness when
a matching checkout belongs to a containing normal namespace.

One grouped target integration case creates real disposable Git repositories,
different local branches, staged and unstaged changes, and a synthetic ENV
canary. It checks both a repository namespace and a containing workspace
namespace. A malformed policy stops before sibling mutation; restoring the
fixture's valid projection preserves every protected file and Git byte while
the sibling actually fetches and fast-forwards from its independent local bare
remote. Network transport and tool readiness are fixture substitutes; Git
mutation, custody witnesses and namespace inspection are real.

Run from the package root:

```bash
python3 edit/skills/_fleet/fleet-i-sync-code-workspaces/scripts/test_workspace_reconciliation.py
```

Use a disposable bounded `TMPDIR` when another acceptance job owns a strict
aggregate storage reservation. Never target live Code roots for verification.
