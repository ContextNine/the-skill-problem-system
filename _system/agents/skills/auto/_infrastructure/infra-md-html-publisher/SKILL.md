---
name: infra-md-html-publisher
description: Publishes, discovers, reads, updates, or shares rendered Markdown and safe static HTML through CTX9 Publisher. Use when the user asks to host a readable document, publish Markdown or HTML, find a hosted document, or update an existing live document while preserving its intent.
---

# Infra · MD HTML Publisher

Use `publish` with `kind=document`, `presentation=rendered`, and the supplied document's intent unchanged. Read [[references/publisher-document-lifecycle|Publisher Document Lifecycle]] for discovery, versioning, and exact deletion.

## Preserve intent

- Existing source plus publish/share/view: publish unchanged.
- Explicit create or rewrite request: author only the requested artifact type.
- Never silently summarize, retitle, remove frontmatter, add plan sections, or convert a report into a plan.
- Inspect public source for credentials, private notes, or hidden context before upload. Stop on risk instead of silently redacting.

## Publish

Run `publish doctor --json`, then publish Markdown or safe static HTML:

```bash
publish publish path/to/source.md --kind document --visibility unlisted --purpose document --collection project --owner-domain project --owner-type document --owner-reference stable-name
publish publish path/to/source.html --kind document --visibility unlisted --purpose document --collection project --owner-reference stable-name
```

For generated HTML, start from `assets/dark-monochrome.html`. Require a doctype, non-empty title, semantic responsive markup, and static inline CSS/SVG. Reject scripts, handlers, forms, frames, embeds, objects, meta refresh, and `javascript:` URLs.

## Update

Use the same publication ID and current ETag to preserve the stable URL:

```bash
publish new-version <id> path/to/source.md --etag '<etag>' --kind document --visibility unlisted --purpose document --owner-reference stable-name
```

Keep existing source files. Remove generated temporary source only after successful publication. If publication fails, retain it for diagnosis.

## Return

Return the latest URL, immutable version, publication ID, what was published, and whether source was preserved or a generated temporary file was removed.
