# Set up a company GTM CRM

Create or update a registered company's GTM workspace without overwriting its notes or workbook. Read README-gtm-and-crm and README-crm first. Check the teamspace's existing `company/`, `gtm/`, and any old CRM sources. Use `$witan-xlsx` for workbooks. Setup of an existing teamspace copies only missing scaffold files; moving its real leads requires a separate reviewed reconciliation.

The canonical physical structure is `_system/templates/gtm/scaffold/gtm/`, composed by the business teamspace pack. Shared marketing-stack and CRM rules stay in `_system/templates/gtm/` and are not copied into companies. Personal brands continue to use `brand/`.

From inside the Vault, preview then apply the missing files:

```bash
python3 _system/agents/edit/skills/_vault/vault-i-use-crm/scripts/apply.py --teamspace impression --identity-type company
python3 _system/agents/edit/skills/_vault/vault-i-use-crm/scripts/apply.py --teamspace impression --identity-type company --apply
```

The script installs `company/` and `gtm/`, including the empty `gtm/CRM.xlsx`, without replacing existing files. It copies the generic workbook byte-for-byte. A second run must leave an edited company workbook unchanged. For a personal brand, use `--identity-type personal-brand` and its registered teamspace. Do not copy the editable brand-definition worksheet master.

For a company using the business toolkit, run `vault business-toolkit sync --teamspace-folders <name> --include gtm --apply` to configure campaign note templates. Audience and offers remain flat source files. Preview first. Run the installer again without `--apply`; it should plan no missing files. Open the workbook and confirm its company name and standard tables.

Do not delete source files or merge names during additive setup. For a migration, inventory operational source rows and note bodies, give every real CRM entry a verified workbook row, and switch capture only after the workbook has been checked. Keep bulk profile and prospect exports outside the operational CRM. Never create one CRM row per export row; promote selected rows only when they represent real contacts worth managing. Retire originals only after value-level reconciliation and an explicit retention decision. One row per person or company; reference substantial delivery or partnership documents instead of copying them into the CRM.
