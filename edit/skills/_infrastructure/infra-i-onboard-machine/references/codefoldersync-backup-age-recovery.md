---
type: agent-reference
status: enabled
---

## CodeFolderSync backup age recovery

Each machine selected in `$(fleet config path)/skills/config/infra-i-onboard-machine/backup-recovery.json` owns an independent age identity at `~/.config/ctx9/codefoldersync/backup-recovery.agekey`. Configure at least two recovery machines before enrollment. The directory is mode `0700`; the identity is a regular, non-symlink file with mode `0600`. Never copy an identity. Distribute only its public `age1...` recipient and SHA-256 recipient fingerprint.

Use `scripts/codefoldersync_backup_age.py`. Every mutation is preview-first, and an existing canonical identity is always `existing-unverified`: presence never proves enrollment and generation never overwrites it.

### Initial enrollment

Run these commands locally on the named target, or stage the reviewed script and invoke it with a separate strict SSH command:

```bash
python3 scripts/codefoldersync_backup_age.py generate --machine-id <recovery-machine-id>
python3 scripts/codefoldersync_backup_age.py generate \
  --machine-id <recovery-machine-id> \
  --report <absolute-run-root>/<machine-id>-generation.json \
  --apply
```

The generated report is mode `0600` and contains only public recipient metadata. On a controller with all configured recipients, preview and create one unique non-secret fixture. Repeat `--recipient` for each configured recovery machine:

```bash
python3 scripts/codefoldersync_backup_age.py create-fixture \
  --fixture-id <run-qualified-id> \
  --recipient <first-recipient> \
  --recipient <second-recipient> \
  --output <absolute-run-root>/recovery-fixture.age

python3 scripts/codefoldersync_backup_age.py create-fixture \
  --fixture-id <run-qualified-id> \
  --recipient <first-recipient> \
  --recipient <second-recipient> \
  --output <absolute-run-root>/recovery-fixture.age \
  --report <absolute-run-root>/recovery-fixture.json \
  --apply
```

Copy only that ciphertext and manifest to each target's disposable run root. Each target independently runs:

```bash
python3 scripts/codefoldersync_backup_age.py verify-fixture \
  --machine-id <recovery-machine-id> \
  --ciphertext <absolute-run-root>/recovery-fixture.age \
  --fixture-manifest <absolute-run-root>/recovery-fixture.json \
  --report <absolute-run-root>/<machine-id>-acceptance.json
```

Return only the sanitized reports. Preview their exact match before recording accepted state:

```bash
python3 scripts/codefoldersync_backup_age.py accept \
  --report <first-acceptance.json> \
  --report <second-acceptance.json> \
  --state-output <machine-secrets.lock.json>

python3 scripts/codefoldersync_backup_age.py accept \
  --report <first-acceptance.json> \
  --report <second-acceptance.json> \
  --state-output <machine-secrets.lock.json> \
  --apply
```

Acceptance requires every configured recovery machine to decrypt the same ciphertext into the same declared plaintext with a distinct identity. The script never prints identity contents or decrypted plaintext.

### Existing identity and recovery

Run `inspect --machine-id <id>` first. An existing identity must pass the same shared-fixture ceremony before acceptance. Do not generate a replacement merely because its sanitized lock record is absent.

For loss or rotation, generate a replacement in a separately reviewed target-local path, add its public recipient to a new recovery set, re-encrypt or supersede every retained snapshot set, and prove a Drive-downloaded restore before retiring the old identity. That destructive rotation is a separate explicit operation; the initial-enrollment helper deliberately has no replace flag.
