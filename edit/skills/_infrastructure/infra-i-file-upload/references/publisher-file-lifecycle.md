# Publisher file lifecycle

`publish` is the sole command and Publisher policy determines the final delivery origin. Configuration uses `PUBLISHER_API_ORIGIN`, `PUBLISHER_RENDERED_ORIGIN`, `PUBLISHER_PUBLIC_FILE_ORIGIN`, and `PUBLISHER_TOKEN`; authenticate with `publish login --token-stdin` rather than placing tokens on the command line.

Every upload has one organizational namespace and one independent delivery visibility:

- `private` accepts `tenant` or `restricted` visibility.
- `public` accepts `public` or `unlisted` visibility.
- `git` accepts any visibility because repository ownership does not determine delivery access.

These are the only top-level storage namespaces. Publisher chooses immutable object keys below them as `<namespace>/<tenant-id>/<publication-id>/<version>/<name>`; callers do not create purpose folders. Use `git` for PR evidence, `public` for directly shareable resources including lead-magnet files, and `private` for authenticated files.

Use `unlisted` for PR evidence unless a public listing is intended. A lead magnet and an ordinary public resource are uploaded the same way. The difference is outside storage: the lead-magnet application owns consent, confirmation, and delivery eligibility, while Publisher owns the file and its delivery policy. The returned publication ID is the lifecycle identity; URLs and object keys are service decisions.

Omitting expiry keeps a publication available indefinitely. Use `--expires-in <number><m|h|d|w>` for a relative lifetime such as `1w` or `2w`, or `--expires-at <ISO timestamp>` for an exact cutoff. At the cutoff Publisher stops authenticated and public delivery immediately; its existing retention worker later tombstones the publication and deletes its immutable objects. The upload reservation's `uploadExpiresAt` only limits the time available to transfer and finalize the file. It is separate from the publication's optional `expiresAt`.

Use `publish metadata <id> --json` before versioning or deletion. `publish new-version <id> <file> --etag <etag>` preserves the publication identity. `publish download <id> --version <n> --output <path>` retrieves an exact version. Deletion tombstones one exact publication identity and does not imply object-store destruction.

The public URL grants no secrecy. Expiry limits future delivery but cannot revoke copies already downloaded or cached before their allowed cache lifetime.
