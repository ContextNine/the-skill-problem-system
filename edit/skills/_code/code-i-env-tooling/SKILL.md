---
name: code-i-env-tooling
description: Manages typed repository environment contracts with Secret Bindings. Use when the user asks to add, change, migrate, reconcile, publish, load, or troubleshoot environment variables, .env.base files, protected bindings, K3s or CI profiles, or legacy plaintext env sources.
---

# Code · Env Tooling

## Safety

- Never read or print plaintext `.env`, tokens, keys, decrypted files, kubeconfig, or protected provider values.
- Use only the fleet-installed `secret-bindings` from `PATH`. `SECRET_BINDINGS_BIN` is limited to isolated integration tests that intentionally select a build.
- Import, equality, deletion, rotation, production, and live-database work keep their separate approval boundaries.

## Schema v4 contract

Every managed runtime repository owns `.context9/secret-bindings.yaml` with explicit environment sets and run profiles. Every environment set has one tracked `.env.base`:

- A non-empty assignment is authoritative public Git configuration.
- An empty assignment declares a protected slot.
- An optional public variable without a value is absent.
- Legacy `#K!` and `#P!` markers are invalid.

Git is the only writer for names, public values, comments, ordering, enabled environments, and execution policy. Secret Bindings stores sparse protected values and may edit only active empty slots. Removing a protected slot from Git makes any historical ciphertext inaccessible.

```bash
secret-bindings repository-plan /path/to/repository
secret-bindings validate /path/to/repository
secret-bindings contract check /path/to/repository
secret-bindings ui /path/to/repository local
secret-bindings import /path/to/repository
secret-bindings reconcile /path/to/repository
cd /path/to/repository && secret-bindings run <profile>
```

1. Change the tracked `.env.base` and schema-v4 declaration in Git.
2. Validate locally, commit, and let the registered source synchronization activate one exact default-branch commit. Local hooks may validate but are not the synchronization authority.
3. Edit only protected values in the inline repository environment editor or with `$secret-bindings-cli`.
4. Reconcile protected-name or execution-policy changes and verify a test-safe consumer profile. Public-only commits do not invalidate authorization.

Resolution precedence is Tenant shared, Mine shared, Tenant environment, Mine environment, repository shared, private authority, then repository environment. Public Git assignments bypass that chain. Empty protected values do not shadow inheritance.

Unresolved protected slots are advisory. Secret Bindings reports their names, removes them from inherited process state, and omits them from generated delivery files. It does not block Save, reconciliation, publication, or an authorized consumer solely for incompleteness. The repository owns required-variable validation.

For cross-repository equality, origins, duplicate overrides, and reviewed promotion to Globals, use `$secret-bindings-organize-secrets`. Never expose values or stable hashes to perform the comparison.

## Legacy migration

Regular `.env`, `.env.*`, `.decrypted`, and aggregate generated plaintext files are forbidden after migration. Before removing an exact legacy source, complete protected import, value-hidden equality, profile acceptance, recovery, and reviewed rollback evidence. Never inspect the file to shortcut that process.

Application-owned `run-secret-bindings.mjs`, `load-env.sh`, post-update plumbing, and production `SECRET_BINDINGS_BIN` overrides do not belong in consumers. Package scripts call the installed CLI directly. Do not recreate a removed wrapper.
