# Blog source integration

First resolve the owning checkout and read its `AGENTS.md`, nearest blog README, source configuration, loader, and relevant product/style/analytics docs. Paths below are relative to that checkout, not this reference. Apply an adapter only when the corresponding implementation exists. Inspect current source mode and compiler ownership before editing; structural examples are not frozen site settings.

## Hybrid Markdown and Notion blog

For a repository using `./apps/next/`, read `./.docs/blogs-and-changelog.md`, `./.docs/analytics-and-seo.md`, and `./apps/next/content/blog/README.md`.

- Source config and loaders live under `./apps/next/src/lib/blog/`.
- Handwritten Markdown posts live at `./apps/next/content/blog/<slug>.md`; filename determines the blog URL. Current local posts require `title`, `summary`, and `publishedAt`; use supported `lastUpdated`, `categories`, `author`, and `thumbnail` fields as appropriate.
- The current loader has no local draft-status filter. A review draft belongs outside this directory. Adding `status: draft` does not prevent publication.
- Hybrid mode merges local and Notion posts, with local winning slug collisions. Edit the existing authoritative source rather than create a local override by accident. Inventory both sources for duplicate intent.
- For Notion-authored posts, use `$integrations-i-notion` and the repository's documented property names, site selection, and publication status. Do not change status to published or run a publication operation without authorization. Do not assume the API is configured.
- Authors and images follow the blog docs and source config. Preserve original publication dates and use the supported modified-date field. Run the repository's image-generation command only when Notion media changes need it.
- Public-site GA4 and app-subdomain PostHog have different responsibilities. Use public acquisition/outcome evidence for blog analysis; do not install PostHog on the marketing site or change analytics as part of article editing.

## Typed competitor pages

When the repository uses `./apps/next/src/app/(marketing)/(competitors)/competitor-pages-data.ts`, read that file and its renderer at `./apps/next/src/app/(marketing)/(competitors)/components/competitor-comparison-pages.tsx` before editing.

- These comparisons and alternatives are root-level typed routes, separate from Markdown `/blog` articles. Use the supplied briefs from `$blog-i-02-research-and-brief` and the existing schema.
- Preserve comparison/alternatives discriminants, slug/path agreement, existing media IDs, and registry ordering where practical. Inspect the actual required fields rather than invent a new schema.
- When both pages are requested, provide `/<slug>-vs-impression` and `/best-<slug>-alternatives`. For `all remaining`, compare existing brief pairs against registry entries. Do not create unsupported pairs from missing research.
- Alternatives use a fair, supported candidate set, normally three to five entries. Comparison rows cover one meaningful axis each. Keep shutdown status, weak pricing confidence, planned features, and category mismatch visible where relevant.
- Verdicts must say who should choose each option and why. Do not rank the owner first automatically or claim replacement for adjacent tools.
- Preserve `competitorYoutubeVideoId`, per-page `impressionYoutubeVideoId`, and the global video ID. Do not create Markdown duplicates, old `/blog` competitor routes, redirects, or unrelated renderer changes.
- Format changed TypeScript and run `pnpm --dir apps/next typecheck`. Missing FAQ fields mean the FAQ skill proposes a prose/body edit; it must not extend the renderer just to insert FAQs.

## Tenant monorepo

For a repository using `./apps/next/_multi_tenant/`, read root tenant instructions, the selected tenant's README/style guide, `./.docs/analytics-and-seo.md`, and `./apps/next/_multi_tenant/content/blog/README.md`.

Resolve the selected tenant's blog feature, canonical host, base path, source mode, Notion site name, assets, author, and source directory from its configuration and loaders. Include the base path in links/canonical URLs for path-mounted tenants. Do not enable a disabled blog or mix tenants' content/metrics as an incidental article change.

### Compiler-owned Vault blogs

Inspect `./apps/next/_multi_tenant/src/lib/vault-content/config.ts` and the publishing manifest for the selected tenant. If the tenant is compiler-owned, compose `$context-nine-monorepo-publish-vault-site-content` and edit the configured Vault blog source. Never edit generated blog Markdown or `*.vault-generated.ts`.

- Use the source note's native content status and `publish_date`, not emitted app frontmatter. Keep drafts nonpublished; don't mark published merely to get a preview.
- Preserve original publication date and use supported `updated_date`/`updated` when appropriate. Authors and embedded images follow the projection skill.
- The compiler may take the first heading as the title. Follow root Vault instructions for normal-note titles; don't introduce a new H1 where the Vault forbids it. Check the actual compiler's filename/title behavior. Report a source-convention conflict rather than silently changing the compiler.
- Use Obsidian links in Vault sources and the projection skill's supported public-link/asset resolution. Keep private evidence and agent-process metadata outside normal note bodies.
- For authorized published-source edits, run the projection skill's sync/check commands and inspect emitted content, manifest changes, tenant routes, metadata, authors, links, and assets. Generated application files must remain usable without the private Vault.

### Handwritten Markdown or Notion tenants

If compiler ownership is absent, use the tenant's configured handwritten Markdown directory or Notion source. Do not assume every tenant is Vault-authored. Local Markdown uses the loader's `title`, `summary`, `publishedAt`, and supported optional fields. Keep unapproved drafts outside loaded directories, and avoid creating a local override for a Notion post.

Analytics config/examples do not prove installed GA4/GTM access. Use each tenant's actual property or export; never borrow another project's IDs or aggregate different sites without an explicit reporting scope.
