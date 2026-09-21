---
name: marketing-i-setup-gtm-workspace
description: Use when the user asks to create, standardize, repair, or compare a company GTM folder, relationship CRM, lead-import structure, marketing workspace, or a personal-brand marketing folder inside a Vault context.
---

# Marketing · Set up a GTM workspace

Create the smallest consistent marketing and relationship structure for one or
more registered Vault contexts. Preserve existing files and data.

## Read first

1. Run `vault inventory` and read each selected context note.
2. Read GTM and relationship workspace.
3. Inspect the selected context's `company/`, `GTM/` or `gtm/`,
   `relationships/`, and any existing `crm/` paths. Treat existing lead sheets
   as active data unless the user confirms otherwise.
4. For workbook sources, use `$witan-xlsx`. Read CSV headers before rows unless
   the migration requires record-level inspection.

## Apply the canonical structure

The source of truth is `_system/bootstrap/templates/context-folders/`. Do not
copy the structure into this skill or invent a second schema.

The shared marketing stack lives in `_system/docs/marketing-stack/`. Read
README-marketing-stack. Do not copy or create `marketing-stack/` inside a
company or personal-brand context.

Use the included script. It is dry-run by default and copies only missing files:

```bash
python3 scripts/apply.py --context impression --identity-type company
python3 scripts/apply.py --context impression --identity-type company --apply
python3 scripts/apply.py --context matt-derman --identity-type personal-brand --apply
```

Preserve the casing of an existing `GTM/` directory. Never overwrite, rename,
move, merge, or delete existing notes or imports during setup.

For a company context, configure the matching business-toolkit components after
the physical structure exists. Preserve saved components and add the
`relationships` group. Preview first, then apply through `vault
business-toolkit sync`.

## CRM rules

- Keep actionable leads, curated relationships, companies, and qualified
  opportunities as notes under each company's `relationships/`.
- Keep bulk CSV and workbook sources under `relationships/imports/`.
- Do not create one note per unselected bulk-list row. A working lead sheet is
  different: preserve its actionable rows during an approved conversion.
- Match people by email or profile URL when present and companies by domain.
  Review sparse identities manually; never merge on name alone.
- Link GTM campaigns to CRM records. Do not store CRM records inside `gtm/`.
- Treat an external CRM such as Attio as an optional operational layer. Keep the
  Vault structure portable and retain exports.

## Existing data

Inventory existing sources and produce a proposed mapping before conversion. The
setup request alone authorizes additive folders and templates, not bulk record
moves or conversion. Name conflicts, missing identifiers, or mixed person and
company rows require a migration decision from the user.

## Verify

1. Run the script again without `--apply`; it should plan no changes.
2. Run `vault business-toolkit status --context-folders <contexts>` for company
   contexts.
3. Confirm each company has `company/`, `gtm/`, and `relationships/`; confirm a
   personal brand has its marketing state inside `brand/`.
4. Run focused business-toolkit tests after changing the canonical pack.
