---
type: agent-reference
status: enabled
---

## CodeFolderSync backup age recovery

Mattbook and Wootbook each own one independent age identity at `~/.config/ctx9/codefoldersync/backup-recovery.agekey`. The directory is mode `0700`; the identity is a regular, non-symlink file with mode `0600`. Never copy either identity. Distribute only its public `age1...` recipient and SHA-256 recipient fingerprint.

Use `scripts/codefoldersync_backup_age.py`. Every mutation is preview-first, and an existing canonical identity is always `existing-unverified`: presence never proves enrollment and generation never overwrites it.

### Initial enrollment

Run these commands locally on the named target, or stage the reviewed script and invoke it with a separate strict SSH command:

```bash
python3 scripts/codefoldersync_backup_age.py generate --machine-id <mattbook|wootbook>
python3 scripts/codefoldersync_backup_age.py generate \
  --machine-id <mattbook|wootbook> \
  --report <absolute-run-root>/<machine-id>-generation.json \
  --apply
```

The generated report is mode `0600` and contains only public recipient metadata. On a controller with both recipients, preview and create one unique non-secret fixture:

```bash
python3 scripts/codefoldersync_backup_age.py create-fixture \
  --fixture-id <run-qualified-id> \
  --recipient <mattbook-recipient> \
  --recipient <wootbook-recipient> \
  --output <absolute-run-root>/recovery-fixture.age

python3 scripts/codefoldersync_backup_age.py create-fixture \
  --fixture-id <run-qualified-id> \
  --recipient <mattbook-recipient> \
  --recipient <wootbook-recipient> \
  --output <absolute-run-root>/recovery-fixture.age \
  --report <absolute-run-root>/recovery-fixture.json \
  --apply
```

Copy only that ciphertext and manifest to each target's disposable run root. Each target independently runs:

```bash
python3 scripts/codefoldersync_backup_age.py verify-fixture \
  --machine-id <mattbook|wootbook> \
  --ciphertext <absolute-run-root>/recovery-fixture.age \
  --fixture-manifest <absolute-run-root>/recovery-fixture.json \
  --report <absolute-run-root>/<machine-id>-acceptance.json
```

Return only the sanitized reports. Preview their exact match before recording accepted state:

```bash
python3 scripts/codefoldersync_backup_age.py accept \
  --report <mattbook-acceptance.json> \
  --report <wootbook-acceptance.json> \
  --state-output <machine-secrets.lock.json>

python3 scripts/codefoldersync_backup_age.py accept \
  --report <mattbook-acceptance.json> \
  --report <wootbook-acceptance.json> \
  --state-output <machine-secrets.lock.json> \
  --apply
```

Acceptance requires two distinct recipients to decrypt the same ciphertext into the same declared plaintext. The script never prints identity contents or decrypted plaintext.

### Existing identity and recovery

Run `inspect --machine-id <id>` first. An existing identity must pass the same shared-fixture ceremony before acceptance. Do not generate a replacement merely because its sanitized lock record is absent.

For loss or rotation, generate a replacement in a separately reviewed target-local path, add its public recipient to a new recovery set, re-encrypt or supersede every retained snapshot set, and prove a Drive-downloaded restore before retiring the old identity. That destructive rotation is a separate explicit operation; the initial-enrollment helper deliberately has no replace flag.
