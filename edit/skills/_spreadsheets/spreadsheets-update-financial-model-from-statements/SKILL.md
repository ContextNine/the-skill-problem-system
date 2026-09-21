---
name: spreadsheets-update-financial-model-from-statements
description: Updates configured linked business and personal financial model from statement CSVs or PDFs using persistent categorization rules, validated canonical ledgers, monthly aggregates, and staged Witan workbook updates. Use when explicitly asked to import new financial statements, refresh transaction categories, rebuild financial CSVs, or update model.
---

# Spreadsheets · Update Financial Model from Statements

## Required skills

Read and follow these before acting:

1. `documents-reliable-pdf-data-extraction` for transactional PDFs.
2. `$witan-xlsx` for every workbook read or write.
3. `$witan-read-source` only for non-transaction supporting documents.

Never use `witan read` to replace page-streaming bank-statement extraction.

## Run

```bash
python3 scripts/update_financial_model.py --config "$(vault root)/_system/agents/edit/settings/skills/config/spreadsheets-update-financial-model-from-statements/private/workflow.json" --update-workbook
```

Use `--prepare-only` to rebuild and validate CSV artifacts without touching workbook. Use `--force-workbook` only when workbook must be regenerated despite unchanged inputs.

If a staged Witan save exhausts retries, resume from its checkpoint without repeating earlier writes:

```bash
python3 scripts/update_financial_model.py \
  --resume-run /absolute/path/to/runs/<run-id> \
  --resume-candidate /absolute/path/to/candidate-stage-N.xlsx \
  --resume-from-phase <failed-phase>
```

Read `workbook_checkpoint.json` for last completed phase and candidate path. Resume from next phase. Re-running failed phase is safe because phase writes are idempotent.

Witan save defaults: five table rows per phase, staged filename rotation every save, 20-second request timeout (service maximum), and one outer attempt (Witan already retries internally). Runtime sends generated phase-only scripts from `runs/<run-id>/phase_scripts/` in stateless mode; this avoids large-dispatcher compile and revision-upload timeouts. `Personal Actuals` holds `tblPersonalMonthly`; `Personal Monthly` remains summary/forecast. Use `--stop-after-phase <phase>` for short checkpointed batches. For pathological table/formula phase, resume with `--chunk-size 1`; do not repeat verified checkpoints.

## Workflow

1. Read `_system/agents/edit/settings/skills/config/spreadsheets-update-financial-model-from-statements/README.md`; load paths and cutoff from `private/workflow.json`.
2. Read the selected context's `_finance/AGENTS.md`. Active inputs and outputs must stay in the registered Vault finance workspace; do not infer a former external Drive folder.
3. Hash source CSV/PDF files. Do not modify source folders.
4. For known CSV schemas, validate and normalize directly.
5. For new PDFs without validated output, run `documents-reliable-pdf-data-extraction` in isolated job folder under data root. Unknown layouts block workbook update until versioned adapter passes validation.
6. Rebuild canonical ledgers from all transactions on or after cutoff.
7. Apply reviewed override, direction-aware transfer/owner-pay rule, merchant rule, alias, then explicit review fallback. Low-confidence generic overrides superseded by v1.1 taxonomy stay disabled.
8. Write low-confidence decisions to run report; never leave blank category.
9. Build monthly aggregates and recurring candidates. Match adopted recurring rules only inside their start/end dates. Populate reviewed commitments from `rules/recurring_commitments.csv`; suggestions stay inactive.
10. Update temporary workbook copy with Witan, checkpoint each phase, run calc/lint/render, then promote it and retain backup.
11. Re-run unchanged workflow to confirm idempotent skip.

If TLS validation fails, never disable certificate checks or trust an intercepted leaf for financial data. Preserve candidate/checkpoint and resume after trusted Witan access returns.

## Updating categories

- Edit `taxonomy/categories.csv` for labels/reporting mappings and `forecastable`. Never reuse stable IDs. Non-forecastable categories remain visible in actuals but stay out of trailing-six-month forecast baselines.
- Edit `rules/category_rules.csv` for reusable merchant and direction rules.
- Edit `rules/transaction_overrides.csv` for one transaction only.
- Adopt recurring candidates by adding match key and effective dates to `rules/recurring_rules.csv`, then add reviewed workbook row to `rules/recurring_commitments.csv`.

See [REFERENCE](REFERENCE.md) for schemas, accounting rules, and failure handling.

Read [OVERVIEW](OVERVIEW.md) when explaining folder layout, workbook sheets, file ownership, or future update flow to Matt.
