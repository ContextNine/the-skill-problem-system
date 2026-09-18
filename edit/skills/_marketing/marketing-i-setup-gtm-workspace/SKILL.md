---
name: marketing-i-setup-gtm-workspace
description: Use when the user asks to create, standardize, repair, or compare a company GTM folder, relationship CRM, lead-import structure, marketing workspace, or a personal-brand marketing folder inside a Vault teamspace.
---

# Marketing · Set up a GTM workspace

Create the smallest consistent marketing and relationship structure for one or
more registered Vault teamspaces. Preserve existing files and data.

## Read first

1. Run `vault inventory` and read each selected teamspace note.
2. Read GTM and relationship workspace.
3. Inspect the selected teamspace's `company/`, `GTM/` or `gtm/`,
   `relationships/`, and any existing `crm/` paths. Treat existing lead sheets
   as active data unless the user confirms otherwise.
4. For workbook sources, use `$witan-xlsx`. Read CSV headers before rows unless
   the migration requires record-level inspection.

## Apply the canonical structure

The sources of truth are `_system/templates/teamspaces/` and
`_system/templates/gtm/scaffold/`. Do not duplicate their structure here.

Shared marketing-tool rules live in `_system/templates/gtm/marketing-stack/`.
Read README-marketing-stack. Do not copy `marketing-stack/` into a teamspace
or create a second live tool inventory.

Use the included script. It is dry-run by default and copies only missing files:

```bash
python3 scripts/apply.py --teamspace impression --identity-type company
python3 scripts/apply.py --teamspace impression --identity-type company --apply
python3 scripts/apply.py --teamspace impression --identity-type company --relationships --apply
python3 scripts/apply.py --teamspace matt-derman --identity-type personal-brand --apply
```

Preserve the casing of an existing `GTM/` directory. Never overwrite, rename,
move, merge, or delete existing notes or imports during setup.

GTM-only setup adds `company/` and `gtm/` without adopting note-based CRM.
Pass `--relationships` only when the selected company also wants the shared
relationship folders and Base. This remains a separate choice for each company.

For a company teamspace, preview matching business-toolkit components after the
physical structure exists. On a GTM-only setup, select `company,gtm`; add
`relationships` only when that CRM option was chosen. Preserve any saved
components and apply through `vault business-toolkit sync`.

## CRM rules when selected

For one-record capture or updates, use `$vault-i-use-crm` and README-crm.
Keep the operating procedure in the GTM template documentation, not here.

- Keep actionable leads, curated relationships, companies, and qualified
  opportunities as notes under each company's `relationships/`.
- Retain existing working CSV and workbook sources in place. Put new retained
  import or export files under `relationships/imports/` when that CRM option is used.
- Do not create one note per unselected bulk-list row. A working lead sheet is
  different: preserve its actionable rows during an approved conversion.
- Match people by email or profile URL when present and companies by domain.
  Review sparse identities manually; never merge on name alone.
- Link GTM campaigns to CRM records. Do not store CRM records inside `gtm/`.
- An external app may later own operational CRM state. Do not migrate or sync it
  as part of GTM folder setup.

## Existing data

Inventory existing sources and produce a proposed mapping before conversion. The
setup request alone authorizes additive folders and templates, not bulk record
moves or conversion. Name conflicts, missing identifiers, or mixed person and
company rows require a migration decision from the user.

## Verify

1. Run the script again without `--apply`; it should plan no changes.
2. Run `vault business-toolkit status --teamspace-folders <teamspaces>` for configured
   company teamspaces.
3. Confirm each company has `company/` and `gtm/`; check `relationships/` and its
   Base only when CRM was selected. Confirm a personal brand uses `brand/`.
4. Run focused business-toolkit tests after changing the canonical pack.
