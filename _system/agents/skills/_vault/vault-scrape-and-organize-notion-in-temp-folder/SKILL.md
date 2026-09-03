---
name: vault-scrape-and-organize-notion-in-temp-folder
description: Scrape public Notion pages into `.agents/temp` exports, download assets, convert Notion databases to CSV, OCR useful image text, and organize the result into clean final Markdown volumes with tracking. Use when the user asks to save, scrape, archive, export, OCR, or organize a public Notion page/site/database into a temp folder or FINAL notes.
---

# Vault · Scrape And Organize Notion In Temp Folder

## Quick Start

1. Read `references/notion-copy-paste-vault-workflow.md` for the exact scrape and organization workflow.
2. Create or reuse a folder under `.agents/temp/<slug>/`.
3. Install crawler deps inside the export folder if needed:

```bash
npm init -y
npm install notion-client notion-utils got sanitize-filename mime-types
```

4. Run `scripts/crawl-notion.mjs` from the export folder:

```bash
node /path/to/skill/scripts/crawl-notion.mjs --url '<public-notion-url>' --out .
```

5. If the task asks for organized final notes, run:

```bash
node /path/to/skill/scripts/organize-final.mjs --export-dir . --out FINAL
```

## Workflow

- Preserve raw evidence: keep `root.html`, `raw_record_maps/`, `raw_html/`, `all-record-map.json`, `manifest.json`, and `assets_manifest.json`.
- Treat collection/database CSVs as row authority when organizing database pages.
- Use OCR only for images likely to carry content: screenshots, posts, carousels, diagrams, and visual-only social posts.
- Skip decorative covers, Notion icons, generic social previews, and empty/low-information OCR results unless the visual itself is source content.
- Always create `_tracking.md` for final organization; append one entry per processed page/database with status, target file, assets inspected, OCR kept/dropped, and notes.
- Verify coverage: every source page is mapped to a final file or explicitly marked duplicate/index/root in `_tracking.md`.

## Scripts

- `scripts/crawl-notion.mjs`: public Notion crawler using `notion-client`, recursive page/collection traversal, asset download, raw HTML snapshots, Markdown/HTML/CSV export, and rate-limit backoff.
- `scripts/organize-final.mjs`: deterministic organizer for the LinkedIn Copy N Paste Vault export shape; writes 10 topic files plus `_tracking.md` and OCRs content-bearing images with `tesseract`.

## Notes

- If `tesseract` is missing, still organize Markdown and assets; mark OCR unavailable in tracking.
- If Notion asset URLs return `403`, record them as blocked source assets, not local failures.
- Do not read or store private credentials; only public Notion content should be scraped by this skill.
