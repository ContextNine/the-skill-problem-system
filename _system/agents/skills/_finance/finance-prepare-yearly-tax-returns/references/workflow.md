# Yearly Tax-Control Workflow

## Standard

Every top-level context with `_finance/` is a tax-reporting workspace. Its local `AGENTS.md` owns the taxpayer mapping. Each relevant tax year has one `0_Yearly_Returns/YYYY.md` control note.

The local finance `AGENTS.md` also owns the legal year-end. Never assume a company uses the individual 1 March to February period. Allocate transactions by legal period and transaction date even when historical folder labels are wrong.

The control note must record:

- taxpayer, tax reference when appropriate, period, required forms, and current status;
- statutory and practical due dates verified from current official sources;
- source coverage and gaps;
- gross receipts/income reconciliation;
- excluded funding, transfers, refunds, loans, and gifts;
- supported deductions or costs requiring tax classification;
- IRP6 working capture and payment calculation when relevant;
- annual-return working figures, unresolved decisions, and completion checklist;
- exact proof used for filed, paid, and assessed claims.

## Evidence hierarchy

1. Submitted eFiling return, SARS assessment, statement of account, payment confirmation.
2. Bank statement, issued invoice, provider invoice/receipt, tax certificate, financial statements.
3. Practitioner correspondence and contemporaneous notes.
4. Memory or inference.

Never promote a lower-level source into a higher-confidence status. A note saying “submitted” remains `needs proof` until the return or SARS record is present.

## Personal allocation

- One ITR12 covers all personal income sources and the net result of personally conducted trades.
- Personal IRP6 estimates total personal taxable income for the full year, not just one client or bank account.
- Do not include Friday Studios company revenue or expenses.
- Do not deduct private spending. Confirm business purpose, supporting evidence, and any apportionment.

## Company allocation

- Owner deposits are financing, not turnover.
- Reconcile shareholder loans as opening balance plus owner funding, less personal costs or withdrawals paid by the company. State whether linked savings transfers remain company cash or reduce the shareholder loan.
- Personal invoices do not become company revenue because they are stored in the company/context folder.
- Refunds reduce the related cost.
- Personal tax paid from the company account is a shareholder/director item, not a company deduction.
- A cash loss is not automatically an assessed loss. Determine trade commencement, deductibility, capital allowances, pre-trade treatment, and the assessed result.

## Status vocabulary

- `working`: calculated from incomplete or unreconciled evidence.
- `ready`: reconciled and reviewed for capture, but not submitted.
- `submitted`: supported by the submitted return or eFiling history.
- `paid`: supported by payment and SARS allocation evidence.
- `assessed`: supported by the SARS assessment.
- `needs-efiling-proof`: claimed in correspondence or memory only.

## Refresh cadence

- Period 1: update actuals to date, full-year estimate, basic amount, and expected credits.
- Period 2: replace forecasts with near-final full-year figures and reconcile period-1 payment.
- Annual return: complete source year, tax adjustments, certificates, provisional credits, and assessment follow-up.
