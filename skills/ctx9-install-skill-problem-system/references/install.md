# Installation

Run `./install.sh` from the fresh user-owned repository. The wizard initializes the editable source under `edit/`, installs runtime, settings, instructions, skills, and state under `~/.agents/`, installs the `fleet` launcher, and makes every public skill globally discoverable.

To add the skill system inside an already installed Vault, run the public release's `./install.sh --vault-source '/absolute/Vault/path'`. The editable source becomes `<vault>/_system/agents/` without a nested `.git`. The same wizard installs runtime under `~/.agents/`. A later run from another public clone recognizes and verifies the active source.

The installer asks about optional global instructions, the Claude alias, and a local Context Vault. Existing unmanaged files are preserved and block only the conflicting integration. Run the same command again to verify convergence.

Check `fleet source path` before choosing a new destination. An existing installation owns one editable source. Reuse that source; do not create another repository pointing at the same `~/.agents/` runtime. If the source is inside a Vault, it lives at `<vault>/_system/agents/`. If it is standalone, it remains in the user-chosen repository. The Vault installer can connect either source later.

Use `fleet verify` to check ownership and configuration. Preview removal with `fleet uninstall`, then apply with `fleet uninstall --apply`.
