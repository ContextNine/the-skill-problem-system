---
name: finance-prepare-yearly-tax-returns
description: Create or refresh the personal and company yearly tax-control notes from Vault finance evidence. Use only when explicitly invoked to prepare an IRP6, ITR12, or ITR14; reconcile a tax year; create the next year's finance return files; or update filing and payment status.
---

# Finance · Prepare Yearly Tax Returns

Use this skill for preparation and recordkeeping. Never submit, amend, or pay a SARS return unless the user separately authorizes that external action.

## Required reading

1. Use `$vault-i` to enter the Vault and complete its host checks.
2. Read Finance & Biz for taxpayer ownership and record locations, then the applicable personal or company steps in Finance SOPs.
3. Read [workflow](references/workflow.md) completely.
4. Resolve and read the requested year's control note and the immediately preceding control note from the locations owned by Finance & Biz.
5. Use current official SARS sources for deadlines, rates, forms, and penalty rules. Tax rules and filing dates are time-sensitive.

## Create a new year

Run once for each current entity. The command refuses to overwrite an existing file:

```bash
python3 scripts/scaffold_tax_year.py --vault-root "$(vault root)" --context personal --year YYYY --taxpayer "M J Derman" --kind individual
python3 scripts/scaffold_tax_year.py --vault-root "$(vault root)" --context outsource-think --year YYYY --taxpayer "Friday Studios (Pty) Ltd" --kind company --year-end-month 3 --year-end-day 31
```

Use `--dry-run` first. Add a new context only after its `_finance/AGENTS.md` defines its legal taxpayer, period, returns, and source folders.

## Refresh a year

1. Verify the legal year-end from the entity's finance `AGENTS.md` and current CIPC or SARS evidence. Never reuse the individual February year-end for a company.
2. Inventory source completeness before calculating.
3. Allocate each transaction by legal issuer, account holder, transaction date, and substance. Personal-name invoices remain personal even when stored under OutsourceThink.
4. Reconcile invoices, receipts, statements, refunds, funding, transfers, and practitioner correspondence. Never use total bank credits as gross income.
5. Separate evidence totals from return-ready figures. Label unknowns and assumptions.
6. Calculate IRP6 gross income, taxable income, tax, credits, and payment from current official rates. Compare with the eFiling basic amount.
7. For a personal IRP6, include the expected deductible retirement-fund contribution in estimated taxable income and distinguish paid contributions from planned contributions. For ITR12, reconcile the paid total to the provider's IT3(f), include all personal income sources once, and claim only supported deductions.
8. For ITR14, distinguish revenue, operating deductions, capital items, shareholder transactions, pre-trade expenditure, and assessed losses.
9. Update the existing year file in place. Preserve submitted values and add dated reconciliation/amendment notes rather than silently replacing history.
10. Store proof references. Correspondence is supporting evidence; only the submitted return, assessment, statement of account, or payment confirmation proves filing/payment.
11. Report ready-to-capture values separately from unresolved blockers. Do not present a working floor or estimate as a filed fact.

## Finish

Confirm both yearly files exist, contain required returns and dates, reconcile to named sources, and clearly distinguish `working`, `ready`, `submitted`, and `assessed` values.
