# Verification and retirement

`verify` first checks that the Rclone configuration is encrypted through the absolute password command. It reads `rclone config redacted` only inside the process and compares the remote type, client ID, scope, Shared Drive ID, and root folder ID to desired state. Output contains match booleans, never IDs, tokens, secrets, paths, or configuration text. `--live` adds a read-only list of the dedicated backup prefix.

`acceptance-test --approve` creates random local bytes, uploads one immutable sentinel under the dedicated acceptance prefix, downloads it, compares SHA-256, runs a downloaded-content check, and deletes only the exact run-owned sentinel and empty run directory. A failed cleanup is reported for manual review; it never widens the deletion target.

`retirement-plan` is value-free and non-mutating. Retirement requires a separate request naming the exact remote and disposition of retained snapshots. Before credential revocation, prove an accepted restore through both recovery identities and record the final remote inventory witness. Disable new uploads first. Revoke each machine's OAuth authorization independently, remove native records through `$infra-onboard-machine`, and remove the remote only after preserved snapshots have an explicitly approved disposition. Never infer archive deletion from remote retirement.

