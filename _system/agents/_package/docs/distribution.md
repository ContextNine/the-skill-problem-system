# Distribution

The public product preserves the `_system/agents` hierarchy while omitting `_package/instance`, `_package/generated`, every `private/` subtree, catalogs, dormant sources, caches, bytecode, and symlinks. It exports separately maintained blank defaults and schemas.

Every active auto, manual, GitHub-managed, and projected skill is audited. Portable skills with confirmed provenance and redistribution rights are published; every exclusion and its reason appears in `PUBLIC_SKILLS_INVENTORY.json`. Credential-like values, invalid skills, symlinks, unresolved configuration contracts, and silent removal of a previously public skill fail publication.

The Skill Problem System and Context Vault keep independent versions and repositories. `vault release publish --product all` coordinates their preflight and publishes only products with meaningful changes.
