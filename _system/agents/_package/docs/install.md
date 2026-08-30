# Installation

Run `./install.sh` from the fresh user-owned repository. The wizard creates managed runtime under the user's data directory, initializes private configuration under the user's config directory, installs the `ctx9-agents` launcher, and makes every public skill globally discoverable.

The installer asks about optional global instructions, the Claude alias, and a local Context Vault. Existing unmanaged files are preserved and block only the conflicting integration. Run the same command again to verify convergence.

Use `ctx9-agents verify` to check ownership and configuration. Preview removal with `ctx9-agents uninstall`, then apply with `ctx9-agents uninstall --apply`.
