# Financial statement update reference

## Canonical transaction fields

`transaction_id, entity, account_id, source_path, source_sha256, source_row, source_page, source_candidate_ids, transaction_date, statement_month, tax_year, currency, description_raw, description_normalized, principal_amount, fee_amount, net_amount, balance, direction, flow_type, category_id, model_category, model_amount, reportable, transfer_group_id, recurring_key, recurring_status, rule_id, classification_confidence, classification_reason, status`

Amounts use decimal strings. Dates use ISO format. South African tax year runs March through February.

## Classification precedence

1. Transaction override.
2. Transfer/capital/owner-pay rule.
3. Exact merchant rule.
4. Regex or keyword rule.
5. Legacy personal category alias.
6. Conservative agent fallback.

Confidence below `0.80` is imported and reported. Do not generalize low-confidence one-offs into merchant rules.

`taxonomy/categories.csv` includes `forecastable`. `No` means actual still reports, but category is excluded from automatic forecast baselines. Transfers, tax refunds, cash withdrawals, asset-sale proceeds, unmatched refunds, unidentified flows, owner funding, and ad hoc owner draws use `No`.

`category_rules.csv` includes optional `direction` (`credit` or `debit`). Use it for counterparties where incoming funding and outgoing owner pay must classify differently.

## Accounting

- Personal own-account transfers and savings movements are not income or expenses.
- Business transfers between tracked cash accounts are financing cash movements, not operating expenses.
- Personal funding of business is business capital contribution and personal asset movement.
- Business owner pay is sourced from business once; matching personal receipt is excluded from duplicate income.
- Fees post separately to Bank fees/Bank charges.
- Matched refunds reduce original category; unmatched refunds use explicit adjustment category.
- Business `accrued_bank_charges` is informational only.

## Workbook interface

- `tblBusinessActuals`: monthly business reporting totals plus recurring/variable split.
- `Personal Actuals`: dedicated import sheet containing `tblPersonalMonthly`, with monthly personal totals plus recurring/variable actual splits. Existing manual notes, budget adjustments, and non-pipeline rows are preserved by key before rebuild.
- `Pipeline Lists`: editable validation lists for current personal categories plus compatibility aliases used by preserved recurring commitments.
- `Personal Monthly`: user-facing summary and forecast sheet. Its formulas continue to reference `tblPersonalMonthly` by table name, independent of table location.
- `tblBizForecastInputs`: remains manual and preserves existing scenario overrides and additive adjustments.
- `Business Forecast Baseline`: pipeline-owned trailing-six-month category baselines used by business forecast totals.
- `Personal Forecast Baseline`: pipeline-owned trailing-six-month category baselines used by personal future budget formulas.
- `tblRecurring`: reviewed rows come from `rules/recurring_commitments.csv`. Five current commitments are active; Adobe stays historical/inactive; incomplete rent, internet, insurance, gym, and loan rows stay inactive with `Needs confirmation`. Existing unreviewed workbook labels are retained below them but forced inactive.
- `tblNetWorthSnapshots`: pipeline auto-populates only `Personal bank account`; other asset and liability rows remain manual.

## Forecast and owner pay

- Recurring evidence matching uses `rules/recurring_rules.csv` and respects inclusive start/end months. Historical Adobe actuals can be recurring without creating future forecast.
- Variable forecast baseline uses trailing six months after excluding every category with `forecastable=No`.
- `Setup & Checks!B27` selects `Salary`, `Fixed draw`, or `Ad hoc draw`; default is `Ad hoc draw`.
- Ad hoc draw defaults to zero and is entered by month in `tblBizForecastInputs` under `Owner pay / draw`. Recurring owner-pay contribution is suppressed in ad hoc mode and conflicting active row raises `CHECK`.
- Personal owner income links to Business Forecast row once. Paired personal deposit is non-reportable.

## Business health KPIs

Dashboard separates Customer revenue, Owner funding / capital contributions, Core operating expenses excluding owner pay, and Closing business cash. Monthly trend and chart use same four measures. Selected-FY business spend uses core operating expenses. `Setup & Checks` verifies receipt components reconcile to total cash receipts.

Workbook update is blocked by schema errors, count mismatch, duplicate IDs, balance failures, blank categories, or formula errors. Lint warnings are recorded for review.

On first migration, Witan renames original `Personal Monthly` sheet to `Personal Actuals`, carrying `tblPersonalMonthly` intact, then creates clean `Personal Monthly` summary and copies forecast timeline there. Later runs reuse both sheets and resize same table in place. Table name never changes. If staged save fails, resume from `workbook_checkpoint.json` with last candidate and next phase; reduce only failing chunk.

All candidate workbooks live under a local temporary staging directory so cloud-drive synchronization cannot lock incremental saves. Promotion first copies the verified candidate beside the live workbook, then replaces it atomically.

Witan requests use stateless, generated phase-only scripts. Each generated script contains shared helpers plus one phase block, reducing request compile cost while preserving same reviewed `workbook_update.js` source. Formula lint errors block promotion even when `witan xlsx calc` reports zero errors. Untrusted TLS interception blocks work; do not bypass it.

## PDF routing

Run `documents-reliable-pdf-data-extraction` one page at a time. Store job bundles under `Financial Model Data/extracted/<entity>/<source-hash>/`. Preserve candidate IDs, coordinates, raw text/cells, adapter ID/version, validation, exceptions, and source hash. Never invent balancing records.
