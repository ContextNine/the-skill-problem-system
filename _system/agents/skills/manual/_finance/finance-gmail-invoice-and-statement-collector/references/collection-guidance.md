# Collection Guidance

## Invoice Judgment

Expect multiple unread emails for the same purchase. A common pattern is one bank/payment notification and one provider invoice or receipt.

- Prefer the provider invoice over a provider receipt for the same transaction. Compare vendor, transaction date, amount or total, invoice or order number, and surrounding email context. The same amount from the same vendor on a nearby date normally means one transaction.
- Save a receipt only when no invoice exists for that transaction. When both exist, report the receipt as a superseded duplicate.
- Treat bank/payment notifications without an attached invoice as manual-needed unless a matching provider invoice was clearly saved in the same run.
- Match bank/payment notifications to provider invoices by vendor and nearby date. Suppress manual follow-up when the provider invoice clearly covers the notification.
- Do not save bank proof-of-payment PDFs as invoices unless the user asks or no provider invoice exists and the document is clearly useful for tax records.
- When multiple emails point to the same invoice, summarize all involved emails together. Include the first 15 characters of each subject so the user can recognize the notification/invoice pair.
- If the relationship is ambiguous, preserve enough detail in the manual-needed report for the user to decide.

Example: a provider email contains an invoice and receipt for the same total and transaction, alongside a matching bank notification. Save the invoice only, classify the receipt as a superseded duplicate, treat the bank notification as covered, and mark all involved emails read only after the invoice saves successfully.

## Bank Statements

The invoice script ignores ordinary bank-statement emails. Handle statements manually with `gws`. The statement root comes from `statement_root` in private config.

- Find unread statement emails, usually from `fnbstatements.co.za` or subjects such as `FNB Statement:`.
- Read the message with `gws gmail users messages get` and download the PDF with `gws gmail users messages attachments get`.
- Save it into the correct `Tax Year YYYY` folder under the statement root. Choose the South African tax year from the statement period when clear; create the folder only when it is missing and clearly correct.
- Preserve a useful bank filename, for example `account-number YYYY-MM-DD.pdf`.
- Before saving, check whether the same statement already exists. Skip identical bytes; if different bytes have the same name, add a suffix.
- Summarize saved statements separately from invoices, including the saved name/path and first 15 characters of each involved email subject.
- Mark a statement email read only after the PDF is saved or confirmed as a duplicate.
