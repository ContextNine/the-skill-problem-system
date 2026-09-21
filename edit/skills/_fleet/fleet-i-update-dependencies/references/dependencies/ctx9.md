## Public CTX9 tools

Dependency IDs: `ctx9-launcher`, `fleet-cli`, `vault-cli`, `codex-repo-sync`, `codefoldersync`, and `publisher-cli`.

`ctx9-launcher` is installed from the exact public `ContextNine/ctx9` GitHub release declared in `../dependencies.json`. The fleet worker downloads the archive, verifies its pinned SHA-256, rejects unsafe archive entries, and invokes the release-owned Python installer. The accepted command is `~/.local/bin/ctx9`. Verification uses the declared version as a minimum so a newer launcher catalog can remain installed without creating a release cycle between the launcher and its Fleet component.

Components remain independently released. The launcher catalog owns their exact artifact URL, integrity digest, supported platforms, installer, provided commands or capabilities, and doctor contract. Fleet recipes use `ctx9 install <component>` and `ctx9 doctor <component>` instead of duplicating a component's release logic or depending on a workspace checkout. Private component recipes additionally declare one exact GitLab generic-package catalog URL and the `ctx9-gitlab-group-read` binding. The dependency worker invokes those recipes through `ctx9 auth`, while the public launcher continues to validate the private overlay, exact host artifact, and checksum.

Fleet itself is a declared component dependency, so a newer launcher catalog can converge the same exact Fleet release across enabled machines. Vault is also declared for supported macOS machines. This keeps installation ownership in `ctx9` while desired versions and multi-machine rollout remain owned by Fleet.

Updating a pinned public tool is deliberate:

1. prove the component's clean public release, checksum, fresh install, doctor, and second-run no-op on every claimed platform;
2. update the public launcher catalog and release the launcher;
3. update the pinned launcher recipe, its minimum accepted version, and the exact component versions in `dependencies.json`;
4. run `fleet update --dependencies`, normal sync, and verify on one worker before the enabled fleet;
5. record factual target and aggregate locks only after acceptance.

Codex Repo Sync additionally requires an installed Codex CLI and one protected system-policy write on first setup. Its public installer owns the `ctx9` Codex marketplace, managed hook, and marked block in `/etc/codex/requirements.toml`. An unrelated marketplace collision is never replaced. Account login, credentials, production deployment, and workspace checkouts are outside this dependency lifecycle.

Public tools may be developed from registered repositories, but runtime availability never depends on those checkouts. Removing a tool or its system policy requires separate authorization.
