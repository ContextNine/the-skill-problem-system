# Backup and restore

The transfer unit is a flat directory containing `witness.json` and one or more `.age` files. The witness schema is:

```json
{
  "schema_version": 1,
  "snapshot_id": "snapshot-safe-id",
  "machine_id": "mattbook",
  "artifacts": [
    {
      "name": "code.tar.zst.age",
      "size": 123,
      "sha256": "64 lowercase hex characters"
    }
  ]
}
```

The controller rejects nested entries, symlinks, non-`.age` artifacts, unbound files, size mismatches, and digest mismatches before contacting Drive. The capture workflow must encrypt both the archive and any path-bearing semantic manifest to the Mattbook and Wootbook recipients accepted through [[codefoldersync-backup-age-recovery|CodeFolderSync Backup Age Recovery]] before placing them in this bundle. `witness.json` may contain only ciphertext names, sizes, digests, machine ID, and snapshot ID.

`backup` copies to `<backup-prefix>/snapshots/<snapshot-id>/<machine-id>` with `--immutable`, then runs `rclone check --download --one-way`. It compares only aggregate remote counts and bytes in its report. It never syncs, overwrites, or deletes a snapshot.

`download` requires a nonexistent destination, creates it with mode `0700`, downloads with `--immutable`, then validates the same witness locally. Successful download proves the ciphertext transfer, not plaintext recovery. Pass the accepted bundle to the CodeFolderSync platform-faithful restore harness, which owns age decryption, archive extraction, portable semantic comparison, and matching-platform metadata checks.
