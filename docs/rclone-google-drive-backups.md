# Google Drive ciphertext backups

The maintained controller is `../edit/skills/_fleet/fleet-i-manage-rclone-google-drive/scripts/rclone_google_drive.py`. Its skill routes custody, transfer, verification, and retirement instructions separately.

`backup --machine-id <uploader> --source-machine-id <archive-owner>` uses the uploader's independently encrypted Rclone config, native config unlock, and transient Personal Global OAuth bindings. The archive owner defaults to the uploader. Both identities must be allowed by installed desired state.

The archive owner's ID must match the validated flat bundle witness. It also determines the Drive directory under the exact configured backup prefix and snapshot. This permits uploading already-held remote-origin ciphertext from a storage worker without copying bulk data or Rclone credentials onto a Mac. The operation never rewrites a witness or labels another machine's archive as the uploader's archive.

Before upload, the controller verifies every bound artifact's size and SHA-256. It copies with `--immutable`, verifies remote bytes with a downloaded-content check, and checks aggregate inventory. File identity and timestamp observations must remain unchanged across transfer before success is reported. This proves ciphertext transfer, not decryption or full-tree restore. Backup retirement remains a separate, explicitly approved operation.

The controller has no plaintext credential-file workflow. Personal Globals enter the child transiently; tokens remain in encrypted machine-local configs and config unlocks stay in native custody. Reports contain aggregate sizes, counts, verification state, and uploader/source machine identities, not values or configuration text.

Run its focused integration and custody tests from the repository root:

```sh
python3 -m unittest discover -s edit/skills/_fleet/fleet-i-manage-rclone-google-drive/tests
```

The on-behalf upload scenario forwards the source identity through the managed launch, transfers a real synthetic bundle through a filesystem-backed provider stand-in, and verifies the destination witness. It also rejects an unregistered origin, a witness mismatch, and a bundle changed during verification.
