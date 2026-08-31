---
name: spreadsheets-housing-decision-model
description: Maintains and analyzes configured housing, business, tax, and investment decision workbook. Use when explicitly invoked to change assumptions, run housing what-ifs, explain scenario math, test buying paths, or identify best feasible decision.
---

# Spreadsheets · Housing Decision Model

## Required skills

Read and follow before acting:

1. `spreadsheets-witan-xlsx` for every workbook read, trace, edit, calculation, lint, and render.
2. `spreadsheets-witan-read-source` when local PDF, DOCX, PPTX, HTML, or Markdown evidence must feed assumptions.
3. Web search using official primary sources when rates, taxes, product limits, or laws need current verification.

Never inspect this workbook with normal file readers or generic XLSX libraries. Never modify another finance workbook.

## Files

- Read `_system/agents/_package/instance/skills/config/spreadsheets-housing-decision-model/README.md` and `private/config.json` first.
- Read `personal/_finance/AGENTS.md`; the configured workbook is part of that Vault workspace. Do not recreate former Drive finance folders.
- Workbook and finance folder come from config; set `WORKBOOK` from `.workbook` before commands.
- Durable model map and assumptions: [[MODEL-REFERENCE]]
- Reusable Witan scripts: `scripts/read-summary.js` and `scripts/update-global-inputs.js`

## Standard workflow

1. Read [[MODEL-REFERENCE]] completely.
2. Run `scripts/read-summary.js` against workbook; never rely only on stored snapshot.
3. Locate requested input/output cells with Witan search and read neighboring formulas.
4. Trace requested Dashboard output to edited inputs.
5. Run edit ephemerally first. Confirm expected outputs appear in `result.touched` and `result.errors` is empty.
6. Explain any surprising result before saving. Check feasibility separately from terminal wealth.
7. Persist only intended hardcoded inputs using `--save`; retain formulas and workbook styling.
8. Run `witan xlsx calc` until zero errors. Run `witan xlsx lint`; review every diagnostic. Render Dashboard and edited assumptions sheet.
9. Re-run summary script. Report old → new assumptions, feasible ranking, nominal/real wealth, affordability reason, selected optimizer policy, and material caveats.

## Global versus decision changes

- Global defaults live in `Global Assumptions`, mostly column C.
- Scenario overrides live in `Decision Assumptions` columns C:H. Blank means inherit global; J:O show effective values.
- Future revenue resets live in `Revenue Path` blue override columns. Entered year becomes new base; later years resume scenario growth.
- Use global changes only when user says change assumption across all decisions.
- Use override cells when user names one scenario. Do not duplicate global values into override cells.

## Safe commands

Read live summary:

```bash
witan xlsx exec "$WORKBOOK" --script "$SKILL_DIR/scripts/read-summary.js"
```

Prototype global edits without `--save`, review output, then repeat with `--save`:

```bash
witan xlsx exec "$WORKBOOK" \
  --script "$SKILL_DIR/scripts/update-global-inputs.js" \
  --input-json '{"as_of":"YYYY-MM-DD","source":"User instruction","edits":{"revenue_growth":0.07}}'
```

## Decision rule

Rank only feasible scenarios by after-tax real year-40 net worth. Show infeasible terminal values for diagnosis, never present them as attainable. Separate financial winner from Green Point lifestyle premium. Results are planning estimates, not tax, legal, or investment advice.
