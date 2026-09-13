## Agent and fleet dependencies

`dependencies.json` is the complete approved identity and lifecycle registry for software used by agents, distributed skills, onboarding, and fleet operations. It is independent of `_system/deps/packages.yaml`; duplication is intentional when both standalone systems need the same prerequisite.

The registry is standard JSON so the portable worker can parse it before optional libraries exist. Each dependency has one closed `kind`, platform eligibility, consumer IDs, a lifecycle reference, and one typed `contract`. Package recipes accept only supported managers and structured arguments. Arbitrary shell commands, secret values, resolved machine paths, and private desired-state locks are forbidden.

`fleet sync` currently installs entries whose kind is `package`, whose `install_policy` is `required`, and whose eligibility is `enabled-agent-machines`. Other typed adapters are declared here now and are implemented through their named onboarding or specialist lifecycle. Central update orchestration will converge every adapter without changing this ownership model.

Repository-built commands remain transitional recipes in `edit/settings/dependencies/selections.json`. They must reference a logical workspace ID from `edit/settings/fleet/workspaces.json`, never a path or checkout URL. The matching `workspace-command` entry here provides stable identity and lifecycle routing. When an immutable package owns the same accepted command, add its release recipe and remove the workspace recipe in the same change.

Public CTX9 tools use the checksummed `ctx9-launcher` release plus typed `ctx9-component` recipes. The launcher catalog owns component artifact details and doctor behavior; this registry owns fleet eligibility, dependency ordering, the exact accepted versions, and lifecycle routing. See `dependencies/ctx9.md`.

Verified target facts live under machine-local `~/.agents/state/`; sanitized aggregate facts live in `internal/generated/state/`. Locks never drive desired configuration. Read the selected file under `dependencies/` before installing, updating, aligning, recovering, replacing, or removing a complex dependency.

Unknown command-path collisions stop without replacement. The package worker recognizes only its documented historical shims, records recoverable metadata under `~/.agents/state/backups/dependencies/`, and never replaces unrelated files.
