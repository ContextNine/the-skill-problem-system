---
name: code-i-env-tooling
description: Manages typed repository environment contracts with Secret Bindings. Use when the user asks to add, change, migrate, reconcile, publish, load, or troubleshoot environment variables, .env.base files, protected bindings, K3s or CICD profiles, or legacy plaintext env sources.
---

# Code · Env Tooling

## Safety

- Never read or print plaintext `.env`, tokens, keys, decrypted files, kubeconfig, or provider values.
- Add every application variable to the owning environment set's `.env.base` first. That file is the exact allowlist, not a value store.
- Use only the fleet-installed `secret-bindings` from `PATH`. `SECRET_BINDINGS_BIN` may select an explicitly approved installed binary for an isolated test. Never resolve a source checkout, topology path, pnpm command, or plaintext fallback.
- Real import, equality, deletion, rotation, production, and live-database work keep their separate approval boundaries.

## Schema-v2 workflow

Every migrated repository owns `.context9/secret-bindings.yaml` with exact environment sets and run profiles. A profile declares its environment, command, working directory, lifecycle, and managed delivery paths; it cannot widen secret scope.

```bash
secret-bindings repository-plan /path/to/repository
secret-bindings validate /path/to/repository
secret-bindings contract <profile> /path/to/repository
secret-bindings ui /path/to/repository <environment>
secret-bindings import /path/to/repository
secret-bindings reconcile /path/to/repository
cd /path/to/repository && secret-bindings run <profile>
secret-bindings audit <profile> /path/to/repository NAME:left-layer:right-layer
```

1. Add or remove names in the exact `.env.base` contract.
2. Review the matching schema-v2 environment set and only the profiles that consume those names.
3. Use `ui` for protected edits, then review encrypted projections and value-free publication metadata.
4. Run `validate`, `reconcile`, `contract`, and the test-safe profile.
5. Use `audit` only for explicitly granted layers when equality evidence is required.

`repository-plan` and `contract` are value free. `import` moves existing encrypted material inside the broker but does not claim equality. `run` injects one versioned snapshot into a broker-owned child and never mutates the parent shell.

## Legacy migration

Regular `.env`, `.env.*`, `.decrypted`, and aggregate generated plaintext files are forbidden after migration. Before deleting one, complete protected import, value-hidden equality, profile acceptance, recovery, and reviewed rollback evidence. Never inspect the legacy file to shortcut that process.

Repository wrappers must call only schema-v2 commands. A temporary `load-env.sh` guard may return successfully only when `SECRET_BINDINGS_ACTIVE=1` and a broker session ID prove it already runs inside a broker-owned child. It must not emit shell assignments. K3s `sync-env-files.sh` may delegate to `reconcile`; an edit helper may open `ui`; neither may recreate old `load`, `sync`, `encrypt`, `decrypt`, `post-update`, or `create-next` presets.

## Resolution

Secret Bindings resolves base, shared encrypted, private-authority encrypted, then environment encrypted layers. Empty later values do not override. `#K!` keeps the template value for every target except `.env`; `#P!` keeps it outside local and development overlays. Markers never authorize a plaintext target.
