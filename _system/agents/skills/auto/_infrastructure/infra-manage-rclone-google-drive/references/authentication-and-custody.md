# Authentication and custody

The desired file contains only non-secret policy: logical remote name, allowed machine IDs, OAuth client ID, `drive.file` scope, Shared Drive ID, dedicated root folder ID, backup prefixes, and no-delete retention policy. It never contains the OAuth client secret, OAuth token, Rclone config password, or age private identity.

Use a dedicated Google OAuth desktop client. Start and remain on `drive.file` unless Matt explicitly approves a broader scope after the dedicated-root acceptance test. Rclone documents that this scope can read and modify only files created by that client, making it the narrow backup default. A Shared Drive ID and dedicated root folder ID are both exact desired-state boundaries, not discovery guesses.

Each enabled machine completes OAuth locally and keeps its token only in that machine's encrypted Rclone config. Never copy an Rclone config. The shared desktop-client secret is a guarded application credential enrolled into native custody through `$infra-onboard-machine`; the controller supplies it only in the Rclone child environment. Each machine independently generates its config-unlock value in Keychain or Secret Service. Rclone receives that value only through the absolute password command.

Native records:

- macOS config unlock: Keychain generic password service `ctx9-rclone-config-unlock`, account `<machine-id>`.
- Linux config unlock: Secret Service attributes `ctx9-provider=rclone-config-unlock`, `ctx9-resource=codefoldersync-backups`, `ctx9-machine=<machine-id>`.
- macOS OAuth client secret: Keychain service `ctx9-rclone-google-drive-client-secret`, account `<machine-id>`.
- Linux OAuth client secret: Secret Service attributes `ctx9-provider=rclone-google-drive-client-secret`, `ctx9-resource=codefoldersync-backups`, `ctx9-machine=<machine-id>`.

Run `configure --approve` only after the desired IDs and both native records exist. It opens Rclone's target-local interactive configuration with protected secret injection. Create exactly the desired remote, authorize that target's account, omit a persisted `client_secret`, enable configuration encryption, then let `verify` reject any mismatch. Do not display redacted configuration without reviewing it again; Rclone warns that redaction is not a proof that every sensitive field is safe to publish.

