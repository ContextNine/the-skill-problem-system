---
name: creative-i-render-markdown-pdf
description: Renders Markdown as a polished black-background vector PDF. Use when the user asks to export a note as a dark PDF or apply the Vault invoice-inspired document style.
---

# Creative · Render Markdown PDF

Apply `$pdf`, then render without changing the source:

```bash
uv run scripts/render_markdown_pdf.py INPUT.md OUTPUT.pdf \
  --title "OPTIONAL TITLE" \
  --blank-placeholders
```

Omit optional flags when unnecessary. Render every page to PNG, inspect it, and extract the final text to confirm that every substantive section is present. Use `$pdf` directly for tables, images, footnotes or custom layouts.

For Vault notes, save standalone PDFs beside the source note. Use `--embedded-attachment` and the owning context's `_obsidian/attachments/` directory only when the PDF will be embedded from Markdown. Keep QA renders in a system temporary directory outside the Vault.
