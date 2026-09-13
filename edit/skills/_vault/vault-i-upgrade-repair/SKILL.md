---
name: vault-i-upgrade-repair
description: Repair public bootstrap vault upgrades after `vault upgrade` reports skipped files, failed migrations, or conflicts. Use when user mentions vault upgrade repair, `_system/local/state/upgrade-reports`, failed migrations, or asks an agent to fix upgrade fallout.
---

# Vault · Upgrade Repair

## Quick Start

1. Read latest report:

```bash
ls -td _system/local/state/upgrade-reports/* | head -1
sed -n '1,220p' _system/local/state/upgrade-reports/<timestamp>/report.json
```

2. Inspect only paths named in report, migration reports, and relevant policy:

```bash
sed -n '1,220p' _system/bootstrap/upgrade-policy.json
```

3. Repair failed migration outputs, skipped managed files, or broken references.

4. Verify:

```bash
vault upgrade doctor
vault refresh --skip-git-maintenance
```

## Rules

- Preserve user-owned notes by default: tasks, projects, epics, content items, entity operating notes, periodic notes, and normal Markdown notes.
- Do not restore public upstream Git into the vault folder. Hidden upstream state belongs outside iCloud.
- Do not run destructive Git commands in the user vault.
- Use `_system/bootstrap/upgrade-policy.json` as source of truth for replace/create/preserve behavior.
- If migration changes user content, keep edits minimal and explain affected files.
- If report references a missing migration script, run `vault upgrade --dry-run` after public setup scripts are updated.

## Common Repairs

- **Failed migration**: open `migration-*.json`, inspect stderr, patch affected files or migration script, rerun migration dry-run/apply as appropriate.
- **Skipped existing scaffold**: compare current file with upstream intent, merge only structural improvements, preserve user-local content.
- **Broken root wiring**: regenerate links or rerun `vault upgrade` after fixing hidden state.
- **Missing hidden state**: run `vault upgrade init-state --from-current`, then `vault upgrade doctor`.
