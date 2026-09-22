---
name: integrations-i-google-sheets
description: Use when the user asks to create, inspect, edit, format, validate, or automate a native Google Sheet, provides a Google Sheets URL, or asks which Google Sheets workflow to use.
---

# Integrations · Google Sheets

Use the simplest native Google Sheets route that can complete the request. This is Matt's preferred Google Sheets workflow and overrides generic spreadsheet instructions that require creating or importing an XLSX first. Do not add a local workbook conversion step unless Matt explicitly asks for a file-based spreadsheet workflow.

## Route

1. Use the `gws` CLI by default for creating, reading, writing, formatting, and validating native Google Sheets. Read `$gws-sheets` for exact commands and request bodies. Create the spreadsheet natively and use Sheets API batch operations when several related writes or formatting changes belong together.
2. Use a native platform integration, such as the Codex Google Drive plugin or a Claude Google Workspace connector, when the user explicitly asks for it, `gws` is unavailable, or the integration is clearly better for the requested interaction. Inspect its advertised actions before choosing it because some integrations can search and read Sheets but cannot edit them.

For missing or insufficient `gws` authentication, use `$fleet-i-onboard-machine` and its Google Workspace CLI Authentication reference. Preserve the complete everyday service grant and never reauthorize narrowly for Sheets alone.

## Operating rules

- Treat a Google Sheets URL or spreadsheet ID as a native Sheet unless the user asks for export.
- Inspect the relevant sheets, ranges, formulas, and formatting before changing an existing spreadsheet.
- Prefer one structured batch update over many small mutations when the API supports it.
- Verify writes with a targeted read of the changed range or spreadsheet metadata.
- Export to `.xlsx`, `.csv`, or another local format only when the user requests a local artifact or a downstream workflow requires one.
