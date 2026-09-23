# Authentication and custody

The desired file contains only non-secret policy: logical remote name, allowed machine IDs, Secret Bindings variable names, the reviewed OAuth scope, Shared Drive ID, dedicated root folder ID, backup prefixes, and no-delete retention policy. It never contains OAuth application credentials, an OAuth token, an Rclone config password, or an age private identity.

Use a dedicated Google OAuth desktop client. Start and remain on `drive.file` unless Matt explicitly approves `drive.file,drive.readonly` after the dedicated-root acceptance test proves the narrow scope cannot initialize the Shared Drive. The broader option keeps writes limited to app-created items but can read Drive metadata and content. Google classifies `drive.readonly` as restricted. No other scope is accepted. A Shared Drive ID and dedicated root folder ID are both exact desired-state boundaries, not discovery guesses.

Each enabled machine completes OAuth locally and keeps its token only in that machine's encrypted Rclone config. Never copy an Rclone config. The shared desktop-client ID and secret live in the configured Secret Bindings personal globals. The controller creates an ephemeral value-free contract, launches itself through `secret-bindings exec --globals`, then maps both values into remote-specific variables for the Rclone child only. Neither application credential is written to desired state or Rclone configuration. Each machine independently generates its config-unlock value in Keychain or Secret Service. Rclone receives that value only through the absolute password command.

Native records:

- macOS config unlock: Keychain generic password service `ctx9-rclone-config-unlock`, account `<machine-id>`.
- Linux config unlock: Secret Service attributes `ctx9-provider=rclone-config-unlock`, `ctx9-resource=codefoldersync-backups`, `ctx9-machine=<machine-id>`.

Preview target-local creation, then apply it on the target. The helper refuses to replace an existing value and reports only sanitized state:

```bash
python3 scripts/rclone_config_unlock.py generate --machine-id <machine-id>
python3 scripts/rclone_config_unlock.py generate --machine-id <machine-id> --apply
python3 scripts/rclone_config_unlock.py inspect --machine-id <machine-id>
```

On macOS, run the apply command from the logged-in user's GUI session if Keychain rejects an SSH process with `User interaction is not allowed`. Do not work around that boundary by placing the generated value in argv, a file, shell history, or synchronized settings.
Run `configure --approve` only after the desired IDs, both Personal Globals, and the target-local config unlock exist. It encrypts a new empty Rclone config before OAuth, refuses to replace an existing remote, creates exactly the desired Drive remote, opens target-local browser authorization, and verifies the result. No credential-bearing Rclone process inherits the terminal. OAuth output is captured and exact application credential values are scrubbed before safe progress text is shown. The protected child-only injection leaves persisted `client_id` and `client_secret` fields empty.

When an existing exact remote needs the explicitly approved broader scope, run `reauthorize --approve` in the signed-in target session. It rejects a remote whose type, Shared Drive, root folder, or persisted-credential policy differs, then updates only the scope and OAuth token before re-verifying the complete policy.

For a headless target, run `remote-configure --approve` on the signed-in source machine with the registered SSH alias and the absolute path to the same controller source on the target. Rclone creates a fresh authorization in the source browser. The controller parses it in memory and sends it to `configure-token` through authenticated SSH stdin. The target writes it directly into its independently encrypted config. Neither controller returns the token or places it in the clipboard, a file, an argument, or logs.
