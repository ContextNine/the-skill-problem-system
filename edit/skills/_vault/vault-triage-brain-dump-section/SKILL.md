---
name: vault-triage-brain-dump-section
description: Explicit-only workflow for reviewing one `***`- or `---`-delimited section of BRAIN_DUMP.md, recommending 3–5 ranked vault destinations, waiting for user choice, then transforming, writing, verifying, and removing only that source section. Use only when user explicitly invokes `$vault-triage-brain-dump-section` or names this manual skill.
---

# Vault · Triage Brain Dump Section

Handle one live Brain Dump section with review before mutation. Do not run whole-inbox `vault triage prepare`, `clear-import`, or `apply` commands.

## Prepare

1. Read [[_system/docs/workflows/README-brain-dump-routing|Brain Dump Routing]] completely.
2. Run `vault inventory`, then read relevant context-folder and library routing notes.
3. Read `_system/inbox/BRAIN_DUMP.md` and identify requested section between full-line `***` or `---` separators. File boundary can replace outer separator.
4. If description matches multiple sections, show short opening previews and ask user to identify one. Do not guess.
5. Search filenames first with `rg --files`; inspect likely existing notes, tasks, projects, content items, and nearest READMEs.

## Recommend

Return 3–5 ranked destinations. Include for each:

- exact existing or proposed vault-relative path;
- append/create/split/skip operation;
- proposed title or heading;
- transformation plan for raw text;
- fit, tradeoff, and confidence from `0` to `1`.

Name preferred option. Recommendations may include existing task, project note, context note, library topic note, `_templates` file, new TaskNotes task, content item, split route, or visible skip.

Do not edit target or Brain Dump during recommendation phase. Wait for user selection unless invocation already supplies exact destination and approval to apply.

## Apply Chosen Route

1. Re-read source and target to detect concurrent Brain Dump sync changes.
2. Transform capture as approved: preserve useful information, improve structure, fix obvious typos, and avoid invented claims.
3. Require exact target path for append and confirm it exists.
4. Write target first. Use `vault task create` for new TaskNotes task; use existing routing names from inventory. Never overwrite unrelated note.
5. Route associated embeds and attachments to owning top-level `_obsidian/attachments/brain-dump/` path and rewrite links before source removal.
6. Re-read target and audit source facts and attachments against transferred result.
7. Remove only transferred section after target verification. Follow separator-collapse rules in Brain Dump Routing.
8. Preserve unrelated captures, backup folders, and original attachments unless user approved their deletion. Do not call external LLM API for classification.
9. Report target path, transformation, verification, and removed source opening words.

If target write fails or exact source section changed or disappeared, do not delete source. Report conflict and ask user to reselect section when needed.
