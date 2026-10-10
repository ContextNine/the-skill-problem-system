# Backup and restore

The transfer unit is a flat directory containing `witness.json` and one or more `.age` files. The witness schema is:

Snapshot IDs are case-preserving safe path components containing letters, digits, dots, underscores, and hyphens, beginning with a letter or digit. Preserve timestamp IDs including uppercase ISO `T`/`Z` exactly; do not rename an original snapshot or rewrite its witness to satisfy a lowercase-only validator.

```json
{
  "schema_version": 1,
  "snapshot_id": "snapshot-safe-id",
  "machine_id": "primary-mac",
  "artifacts": [
    {
      "name": "code.tar.zst.age",
      "size": 123,
      "sha256": "64 lowercase hex characters"
    }
  ]
}
```

The controller rejects nested entries, symlinks, non-`.age` artifacts, unbound files, size mismatches, and digest mismatches before contacting Drive. The capture workflow must encrypt both the archive and any path-bearing semantic manifest to the recipients configured and accepted through CodeFolderSync Backup Age Recovery before placing them in this bundle. `witness.json` may contain only ciphertext names, sizes, digests, machine ID, and snapshot ID.

`backup` copies to `<backup-prefix>/snapshots/<snapshot-id>/<machine-id>` with `--immutable`, then runs `rclone check --download --one-way`. It compares only aggregate remote counts and bytes in its report. It never syncs, overwrites, or deletes a snapshot.

`--machine-id` selects the uploading machine's independently encrypted config and native unlock. Optional `--source-machine-id` selects the archive owner, whose identity must match `witness.json` and determines the final Drive machine directory. It defaults to the uploader for locally captured bundles. Both IDs must be in `allowed_machines`. This lets a storage worker upload already-held Mac ciphertext without allocating a bulk copy on either Mac. It transfers no credential or config between machines. A bundle whose files change during upload/check is not accepted as verified.

`download` requires a nonexistent destination, creates it with mode `0700`, downloads with `--immutable`, then validates the same witness locally. Successful download proves the ciphertext transfer, not plaintext recovery. Pass the accepted bundle to the CodeFolderSync platform-faithful restore harness, which owns age decryption, archive extraction, portable semantic comparison, and matching-platform metadata checks.
