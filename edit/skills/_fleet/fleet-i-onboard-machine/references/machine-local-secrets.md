## Machine-local secrets

`../fleet/machine-secrets.yaml` is the single value-free lifecycle registry. It records stable IDs, scope, lifecycle class, eligible machines, issuing authority, native custody, enrollment route, value-free verification, and recovery. It never contains credential values or desired private state.

Use `$fleet-i-onboard-machine` and [machine-local-secrets-and-enrollment](machine-local-secrets-and-enrollment.md) for enrollment and acceptance. Read a focused file under `references/` only when the registry points to it. Generated and reissued credentials are unique per target; guarded copies use only their checksum-verifying owner; interactive sessions are recreated on each machine; service-only authorities are never enrolled into fleet user accounts.

macOS secrets use the owning application's protected store or Keychain. Linux secrets use the owning protected store or Secret Service. File-based guarded authorities use their declared permissions. Never infer enrollment from file presence, copy opaque application state, print values for verification, or convert a target path into desired configuration.

Sanitized verified facts live in `../state/machine-secrets.lock.json`. They may record identity fingerprints, metadata paths, permissions, and acceptance results, never values. Rotation, revocation, account selection, MFA, and protected GUI prompts remain explicit lifecycle checkpoints.
