---
name: code-i-env-tooling
description: Use when the user asks to add, change, migrate, reconcile, publish, load, or troubleshoot Notenv environment contracts, standalone projects, protected bindings, process execution, package authentication, K3s or CI configuration, or legacy plaintext env sources.
---

# Code · Env Tooling

## Safety

- Never read or print plaintext `.env`, tokens, keys, decrypted files, kubeconfig, or protected provider values.
- Use only the fleet-installed `notenv` from `PATH`. `NOTENV_BIN` is limited to isolated integration tests that intentionally select a build.
- Import, equality, deletion, rotation, production, and live-database work keep their separate approval boundaries.
- Standalone operations require the accepted matching signed server, CLI and broker. Check installed readiness and capabilities first. Missing commands or upgrade errors are not permission to install a source binary, switch to Globals or rewrite the project as Git-backed.

## Contract authority

A project has one explicit source kind. Connected projects use accepted Git commits. Standalone projects use immutable database-owned public definitions and need neither a Git provider nor a linked application folder. Provider failure never changes source kind. Both use schema-v5 declarations, environment sets and the same contract rules:

- A non-empty assignment is authoritative public configuration.
- An empty assignment declares a protected slot.
- An optional public variable without a value is absent.
- Legacy `#K!` and `#P!` markers are invalid.

Names, public values, comments, ordering, enabled environments and execution policy belong to the selected public definition. Protected value autosave is separate and may fill only accepted protected slots. Removing a slot makes historical protected copies inaccessible to ordinary resolution without deleting recovery history.

## Connected projects

Every managed runtime repository owns `.ctx9/notenv.yaml` with explicit environment sets. Each independently run process selects one tracked `.env.base`; run profiles are optional shortcuts. Git alone writes the public definition for this source kind.

```bash
notenv validate .
notenv contract check .
notenv reconcile .
notenv exec --environment local --contract apps/server/.env.base -- node apps/server/dist/main.js
```

1. Change the tracked `.env.base` and schema-v5 declaration in Git.
2. Validate locally, commit, and let the registered source synchronization activate one exact default-branch commit. Local hooks may validate but are not the synchronization authority.
3. Edit only protected values in the inline environment editor or with `$notenv-cli`.
4. Reconcile protected-name or execution-policy changes and verify a test-safe consumer through its exact contract. Public-only commits do not invalidate authorization.

## Standalone projects

Select the project explicitly from any intended working directory:

```bash
notenv project create example --sets runtime,web --environments local,prod
notenv project status example
notenv project reconcile example --environment local --set runtime
notenv exec --project example --environment local --set runtime -- pnpm dev
```

Use the project's inline definition sections for environments, variable sets, profiles and file delivery. Save the public definition explicitly. Protected values use the separate encrypted editor; do not put them in definition documents. On lost acknowledgement, retry the captured operation ID and definition. On revision conflict, retain the draft and review the accepted revision rather than overwriting it. Reconcile affected machine/environment/set policies before execution.

The working directory determines process and declared relative file locations, not project identity or authorization. Do not create pointer files, require local contracts, link a folder or discover Git for explicit standalone execution. `notenv run <profile> --project <slug>` is optional when a declared lifecycle is wanted. Provider-free does not mean offline: hosted policy and enrolled-machine authorization still apply.

Git-to-standalone conversion is a separate reviewed operation. Preview the same project's accepted commit, encrypted history, affected grants and outstanding Save/publication work. Retain the project ID and encrypted values, complete pending Git work, then convert with the captured commit and operation ID. Reconcile each intended consumer afterward. Never recreate protected values or request a new GitHub App installation merely to convert.

For reproducible deployment, freeze the accepted revision and resolved encrypted configuration, including inherited Globals. Pin that snapshot independently of the application commit/image. Use only the signed authorized machine or protected CI delivery path. Portable restore requires fresh CI authorization; it does not restore runnable workload authority. CI support also needs a real protected-job acceptance receipt, not just source tests.

## Resolution and organization

Resolution precedence is Tenant shared, Personal shared, Tenant environment, Personal environment, project shared, private authority, then project environment. Public assignments in the accepted source bypass that chain. Empty protected values do not shadow inheritance.

Unresolved protected slots are advisory. Notenv reports their names, removes them from inherited process state, and omits them from generated delivery files. It does not block Save, reconciliation, publication, or an authorized consumer solely for incompleteness. The application owns required-variable validation.

For cross-project equality, origins, duplicate overrides, and reviewed promotion to Globals, use `$notenv-organize-secrets`. Never expose values or stable hashes to perform the comparison.

## Process execution and packages

Run from the intended working directory. Connected execution selects an accepted contract; standalone execution selects project/environment/set. Neither requires a command-specific profile. Preserve intentional detached sessions and declared file-delivery lifecycles instead of mechanically replacing them with foreground injection. The child and its descendants are trusted with supplied values.

Unmanaged Git checkouts can use authorized Globals with a local value-free allowlist. `--globals` explicitly selects that lane and refuses managed repositories. Moving a managed contract to a temporary checkout after failure is not an authorized workaround.

Repository configuration owns public registry routes; Notenv owns credential custody. Use `$notenv-cli` for reusable least-privilege Globals and accepted `package-auth configure` helpers. Review metadata and tarball destinations. Do not substitute management tokens, invoke credential-output helpers directly or expand destinations after a 404 without checking ownership. Verify actual downloads with the repository's pinned package manager. Native installation/recovery custody remains independent.

## Legacy migration

Regular `.env`, `.env.*`, `.decrypted`, and aggregate generated plaintext files are forbidden after migration. Before removing an exact legacy source, complete protected import, value-hidden equality, consumer acceptance, recovery, and reviewed rollback evidence. Never inspect the file to shortcut that process. Declared session-owned temporary file delivery is not a legacy source.

Application-owned environment-loader wrappers, post-update plumbing, and production `NOTENV_BIN` overrides do not belong in consumers. Package scripts call the installed CLI directly. Do not recreate a removed wrapper. Explicit unmanaged `notenv local` remains a separate user-selected plaintext workflow, never fallback after a managed failure.
