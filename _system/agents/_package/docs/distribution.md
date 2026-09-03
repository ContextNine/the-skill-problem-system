# Distribution

The public product preserves the `_system/agents` hierarchy while omitting `_package/instance`, `_package/generated`, every `private/` subtree, catalogs, dormant sources, caches, bytecode, and symlinks. It exports separately maintained blank defaults and schemas.

Every canonical Vault and GitHub-managed skill is audited. The exporter publishes eligible sources and excludes local-checkout skills plus generated overlays and snapshots. The inclusion and exclusion report stays under ignored `_system/local/state/`; it is not part of the public repository. Credential-like values, invalid skills, symlinks, and silent removal of a previously public skill fail publication.

The Skill Problem System and Context Vault keep independent versions and repositories. `vault release publish --product all` coordinates their preflight and publishes only products with meaningful changes.
