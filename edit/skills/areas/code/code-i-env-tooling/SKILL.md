---
name: code-i-env-tooling
description: Use when the user asks to add, change, migrate, reconcile, publish, load, or troubleshoot environment variables, .env.base contracts, protected bindings, arbitrary process execution, package authentication, K3s or CI configuration, or legacy plaintext env sources.
---

# Code · Env Tooling

## Safety

- Never read or print plaintext `.env`, tokens, keys, decrypted files, kubeconfig, or protected provider values.
- Use only the fleet-installed `notenv` from `PATH`. `NOTENV_BIN` is limited to isolated integration tests that intentionally select a build.
- Import, equality, deletion, rotation, production, and live-database work keep their separate approval boundaries.

## Schema v4 contract

Every managed runtime repository owns `.ctx9/notenv.yaml` with explicit environment sets. Every independently run process selects one tracked `.env.base`. Named run profiles are optional shortcuts, not a prerequisite for executing a command:

- A non-empty assignment is authoritative public Git configuration.
- An empty assignment declares a protected slot.
- An optional public variable without a value is absent.
- Legacy `#K!` and `#P!` markers are invalid.

Git is the only writer for names, public values, comments, ordering, enabled environments, and execution policy. Notenv stores sparse protected values and may edit only active empty slots. Removing a protected slot from Git makes any historical ciphertext inaccessible.

```bash
notenv repository-plan /path/to/repository
notenv validate /path/to/repository
notenv contract check /path/to/repository
notenv ui /path/to/repository local
notenv import /path/to/repository
notenv reconcile /path/to/repository
cd /path/to/repository
notenv exec --environment local --contract apps/server/.env.base -- node apps/server/dist/main.js
```

1. Change the tracked `.env.base` and schema-v5 declaration in Git.
2. Validate locally, commit, and let the registered source synchronization activate one exact default-branch commit. Local hooks may validate but are not the synchronization authority.
3. Edit only protected values in the inline repository environment editor or with `$notenv-cli`.
4. Reconcile protected-name or execution-policy changes and verify a test-safe consumer through its exact contract. Public-only commits do not invalidate authorization.

Resolution precedence is Tenant shared, Personal shared, Tenant environment, Personal environment, repository shared, private authority, then repository environment. Public Git assignments bypass that chain. Empty protected values do not shadow inheritance.

Unresolved protected slots are advisory. Notenv reports their names, removes them from inherited process state, and omits them from generated delivery files. It does not block Save, reconciliation, publication, or an authorized consumer solely for incompleteness. The repository owns required-variable validation.

For cross-repository equality, origins, duplicate overrides, and reviewed promotion to Globals, use `$notenv-organize-secrets`. Never expose values or stable hashes to perform the comparison.

## Legacy migration

Regular `.env`, `.env.*`, `.decrypted`, and aggregate generated plaintext files are forbidden after migration. Before removing an exact legacy source, complete protected import, value-hidden equality, consumer acceptance, recovery, and reviewed rollback evidence. Never inspect the file to shortcut that process.

Application-owned `run-notenv.mjs`, `load-env.sh`, post-update plumbing, and production `NOTENV_BIN` overrides do not belong in consumers. Package scripts call the installed CLI directly. Do not recreate a removed wrapper.

## Arbitrary process execution

Use `notenv exec --environment <environment> --contract <repository-relative-contract> -- <command> <args>`. The accepted Git snapshot, declared environment set, enrolled machine and installed contract grant determine eligibility, not a command-specific task. Synchronize and reconcile contract changes before execution. Adding a name locally cannot grant access.

Run from the intended working directory. If `--contract` is omitted, the nearest declared contract must be unambiguous. Preserve application-specific runtime selection. Keep `notenv run <profile>` only where an intentional shortcut, detached session or declared file-delivery lifecycle is useful; do not mechanically replace those lifecycles with foreground injection.

Unmanaged Git checkouts use the same command with authorized Globals only. `--globals` explicitly selects that lane and refuses managed repositories. A managed failure never authorizes moving a contract into a temporary repository to bypass its policy. The contract is an injection allowlist, not a sandbox; descendants can inherit supplied values.

## Package authentication

Repository configuration owns public scope and registry routes. Notenv owns credential custody. pnpm's trusted user configuration owns the narrow authentication helper binding. Do not make application launch profiles or the native bootstrap helper install packages on behalf of ordinary consumers.

After accepted signed Notenv 2.0.0 or later is installed, configure each machine once with a reusable least-privilege package-read Global:

```sh
notenv package-auth configure --name PACKAGE_READ_TOKEN \
  --registry https://registry.example.com/packages/npm/ \
  --registry https://registry.example.com/downloads/
pnpm install
```

Bind every reviewed metadata and tarball destination. Do not substitute a management token or expand destinations after a 404 without checking ownership and routing. Helpers persist only credential-free contracts and executable paths; pnpm receives the token at invocation time. Never invoke `package-auth emit` or a generated helper directly from an agent terminal. Native bootstrap custody remains separate for installing and recovering Notenv.

Validate actual downloads with the repository's pinned pnpm version on each eligible machine. A source fixture or successful configuration command does not prove installed authentication. Return only public version, machine, scope and success/failure evidence.
