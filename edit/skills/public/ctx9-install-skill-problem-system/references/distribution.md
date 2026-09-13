# Distribution

The public product has a simple repository root containing `README.md`, `edit/`, `internal/`, and the required installation entrypoints. It omits private settings, the personal instruction base, every `private/` subtree, generated views, dormant sources, caches, bytecode, and symlinks. Public users receive safe starter settings and the explicit public instruction base.

Every canonical Vault and GitHub-managed skill is audited. The exporter publishes eligible sources and applies user exclusions from `edit/settings/public-skill-repo-export-exclusions.json` before validation. Local-checkout skills, generated overlays, and generated snapshots never export. The inclusion and exclusion report stays under ignored source state; it is not part of the public repository. Credential-like values, invalid skills, symlinks, and unexplained removal of a previously public skill fail publication.

The exporter converts resolvable Obsidian links in public Markdown to repository-relative links. A named note that is not part of the public repository becomes plain text. Public Markdown cannot retain an Obsidian link. An exclusion also fails when a retained skill still names the removed reference or script.

The Skill Problem System and Context Vault keep independent versions and repositories. `vault release publish --product all` coordinates their preflight and publishes only products with meaningful changes.
