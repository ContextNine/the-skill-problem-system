---
name: finance-gmail-invoice-and-statement-collector
description: Collect unread Gmail invoices, receipts, payment notifications, and bank statements into configured finance records. Use only when explicitly invoked to scan unread Gmail, save invoice or statement PDF attachments into tax-year folders, mark successfully handled messages read, and report purchases whose invoices must be downloaded manually.
---

# Finance · Gmail Invoice and Statement Collector

Read [collection guidance](references/collection-guidance.md) before applying changes. It defines invoice deduplication, payment-notification matching, and the manual bank-statement workflow.

Use the general-tool script for repeatable execution:

```bash
python3 "$(vault root)/_system/tools/gmail-invoice-collector/collect_invoices.py" --dry-run
python3 "$(vault root)/_system/tools/gmail-invoice-collector/collect_invoices.py"
```

Start with `--dry-run` unless the user explicitly asks to process Gmail. Use `--apply` only when the user wants files saved and inspected unread emails marked read.

Read `_system/agents/edit/settings/skills/config/finance-gmail-invoice-and-statement-collector/README.md` and private TOML first. Paths and Google Cloud setup project come from config.

Read Finance & Biz before saving. It owns the canonical record locations and taxpayer boundaries; do not recreate former Drive finance folders.

## Requirements

Read `$gws-shared` and `$gws-gmail` when Gmail command details matter.

`gws` must be installed and authenticated:

```bash
"$(vault root)/_system/deps/install.py"
gws auth login
```

Use `gws auth login` as the normal path. It should open browser OAuth when a GWS client config already exists. If it says no OAuth client is configured, then run:

```bash
gws auth setup --project "<google_cloud_project from config>" --login
```

Prefer configured personal Google Cloud project. Setup flow may ask for Desktop OAuth client ID/secret only when no local client config exists yet.

## Behavior

- Scans only unread Gmail candidate emails in the Inbox. Do not scan archived/all-mail unread by default.
- Uses an invoice/payment query, not a broad `has:attachment` query, because unrelated unread PDFs can be in the Inbox.
- Saves attached invoice or receipt PDFs only when the sender, subject, or attachment filename looks like invoice/receipt/tax/billing material.
- For one transaction, save invoice PDF only when both invoice and receipt exist. Treat receipt as a superseded duplicate and mark all inspected transaction emails read after invoice saves successfully.
- Save receipt only when no invoice was received for that transaction.
- The script ignores normal bank statement emails. If user asks to collect statements, handle those manually from the skill instructions; do not add statement logic to the script.
- Uses Gmail received/internal date in `Africa/Johannesburg` as paid date.
- Routes expense evidence by South African tax year: March through February. Example: `2026-03-01` through `2027-02-28` goes to `2_Expenses/2027`.
- Prefixes saved PDFs with `MM-DD-`.
- Saves duplicate bytes once; if same name has different bytes, appends `-2`, `-3`, etc.
- Reports payment-like emails without PDF invoices for manual follow-up.
- Marks inspected messages read only in `--apply`, after successful save/duplicate handling or manual-needed classification.
- Leaves messages unread if Gmail read/download/marking fails.

## Statements

If the user asks to save bank statements, follow the manual workflow in [collection guidance](references/collection-guidance.md). Do not use or modify `collect_invoices.py` for statement handling.

## Config

Default config:

```text
_system/agents/edit/settings/skills/config/finance-gmail-invoice-and-statement-collector/private/config.toml
```

Config defines invoice root, statement root, report root, candidate query, and Google Cloud setup project.

Override if needed:

```bash
python3 "$(vault root)/_system/tools/gmail-invoice-collector/collect_invoices.py" --dry-run --config /path/to/config.toml
```

## Output

Reports are written to configured `report_root` outside vault.

After a run, tell the user:

- number of invoice files saved;
- exact saved file names/paths;
- duplicate invoice emails skipped;
- bank/payment notifications covered by a provider invoice;
- messages marked read;
- report path;
- manual-needed purchases grouped by vendor/date, with Gmail message IDs and first 15 characters of involved email title(s).
- ignored emails count when a candidate matched the Gmail query but was deliberately skipped.
- saved or duplicate statement files, reported separately from invoices.
