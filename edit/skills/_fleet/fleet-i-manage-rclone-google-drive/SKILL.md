---
name: fleet-i-manage-rclone-google-drive
description: Configures, verifies, uploads, downloads, restore-checks, and retires encrypted CodeFolderSync backups in the dedicated Google Drive root. Use for Rclone Google Drive setup, backup transfer, ciphertext verification, restore downloads, acceptance sentinels, or backup-remote retirement.
---

# Fleet · Manage Rclone Google Drive

Read [Authentication and Custody](references/authentication-and-custody.md) before setup or credential work. Read [Backup and Restore](references/backup-and-restore.md) before moving backup artifacts. Read [Verification and Retirement](references/verification-and-retirement.md) before live acceptance, recovery, or retirement.

## Workflow

1. Load the installed instance configuration with `fleet config path`; never infer provider IDs or machine eligibility.
2. Preview the local machine without reading secrets:

```bash
python3 scripts/rclone_google_drive.py plan --machine-id <machine-id>
```

3. Stop on missing Rclone, desired IDs, Personal Globals, target-local config unlock, or explicit approval. Use `$fleet-i-update-dependencies` for installation, `$secret-bindings-cli` for the OAuth application bindings, and `$fleet-i-onboard-machine` for the config unlock.

Preview and create the independent target-local unlock with `scripts/rclone_config_unlock.py generate --machine-id <machine-id>` and the reviewed `--apply` form. Never replace an existing value automatically.
4. After target-local enrollment and OAuth authorization, verify the encrypted configuration and exact policy:

```bash
python3 scripts/rclone_google_drive.py verify --machine-id <machine-id> --live
```

5. Run the approved random sentinel acceptance test before any real backup:

```bash
python3 scripts/rclone_google_drive.py acceptance-test --machine-id <machine-id> --approve
```

6. Upload only a validated flat ciphertext bundle whose `witness.json` binds every `.age` artifact:

```bash
python3 scripts/rclone_google_drive.py backup --machine-id <machine-id> --snapshot-id <snapshot-id> --source <bundle> --approve
```

7. Download into a new local directory and revalidate the witness before handing ciphertext to the CodeFolderSync restore harness:

```bash
python3 scripts/rclone_google_drive.py download --machine-id <recovery-machine-id> --source-machine-id <source-machine-id> --snapshot-id <snapshot-id> --destination <new-directory> --approve
```

## Safety

- Google Drive receives ciphertext and a sanitized ciphertext witness only. Reject plaintext, symlinks, nested payloads, and unbound files.
- Use the exact dedicated remote and root from desired state. Never enumerate or mutate another Drive hierarchy.
- Upload with `--immutable`; verify with `rclone check --download`. Automatic retention deletion is forbidden.
- OAuth tokens are created independently on each target. Never copy Rclone configs or tokens between machines.
- The OAuth client ID and secret live only in the configured Secret Bindings personal globals and enter the Rclone child environment transiently. Target OAuth tokens stay in independently encrypted Rclone configs. Config passwords stay in native custody. Do not use plaintext environment files or persistent secret environment variables.
- Live create, upload, download, delete, OAuth, or config writes require explicit approval. Retirement is plan-only until separately approved.
