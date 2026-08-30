# Validation contract

CSV is final serialization, not cleanup surface. Validation operates on candidates and canonical records first.

## Generic blocking checks

- source hash matches extraction manifest;
- adapter identity/version matches extraction;
- every candidate accounted for exactly once by record or exception;
- every referenced candidate exists;
- required fields present and non-empty;
- field names and declared types valid;
- record IDs unique;
- page/sequence provenance ordered and valid;
- repairs reference exact candidate IDs and declared fields;
- adapter invariants pass.

Informational exceptions may document headers, footers, blanks, and non-record content. Error exceptions represent unresolved data and block normal export. `--allow-invalid` records override in manifest; it does not turn checks green.

## Transactional document checks

Use only when source document supports them:

- printed transaction count equals extracted record count;
- debit and credit totals reconcile separately;
- signed amount total reconciles to printed turnover;
- opening balance plus net movement equals closing balance;
- each running balance rolls forward from prior record;
- subtotal groups reconcile to statement totals;
- date range and chronological direction match document;
- continuation/page totals do not become transactions;
- duplicate transaction candidates are distinguished from legitimate repeated transactions using provenance and stable keys.

Use `Decimal` with document currency precision. Record displayed rounding rule. Never force reconciliation by inventing balancing rows.

## Other document families

Examples:

- registers: printed row count, unique key constraints, section totals;
- inventories: quantity × unit price, category subtotals, grand total;
- reports: table totals, period coverage, cross-table key reconciliation;
- invoices: line totals, tax basis, tax, subtotal, total, currency consistency;
- logs: sequence continuity, timestamp ordering, event-type counts.

## Review report

`validation.json` contains overall status, candidate/record/exception counts, generic checks, adapter checks, normalized content hash, and timestamp. Review failed checks plus error exceptions. Passing structural checks do not prove semantic accuracy; adapter invariants and representative visual review remain required.
