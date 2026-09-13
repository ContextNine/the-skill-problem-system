---
name: finance-generate-invoice
description: Generate and verify a monthly client invoice with the Vault invoice generator. Use only when explicitly invoked to prepare or regenerate an invoice from client, service month, invoice number, and line-item details.
---

# Finance · Generate Invoice

## Workflow

1. Read `_system/tools/invoice-generation/README.md` completely. It is the source of truth for invoice configuration, CLI usage, output paths and verification.
2. Resolve the client, invoice mode, service month, invoice number and line items from the user's request and source notes. The service month is the month the work was performed, never the date the PDF happens to be generated.
3. Read Finance & Biz for the canonical record location and taxpayer boundary. The selected invoice mode controls the legal issuer and taxpayer; folder location alone does not.
4. Pass the service month with `--invoice-month YYYY-MM`. Let the generator derive the `MM-YYYY-<client>-Invoice_<number>.pdf` filename, month-only header and due date on the 22nd of the following month.
5. Use the documented CLI directly. Do not create a one-off wrapper or duplicate stable configuration outside the invoice generator.
6. Verify the generated filename, header month, invoice number, due date, line items and total as documented, then report the final file path and material inputs.
7. Do not send or publish the invoice unless the user explicitly asks.
