# Publisher file lifecycle

`publish` is the sole command and Publisher policy determines the final delivery origin. Configuration uses `PUBLISHER_API_ORIGIN`, `PUBLISHER_RENDERED_ORIGIN`, `PUBLISHER_PUBLIC_FILE_ORIGIN`, and `PUBLISHER_TOKEN`; authenticate with `publish login --token-stdin` rather than placing tokens on the command line.

Use `unlisted` for PR evidence unless a truly public listing is intended. Use `public` for public resources and lead magnets, with an explicit purpose, collection, and owner reference. The returned publication ID is the lifecycle identity; URLs and object keys are service decisions.

Use `publish metadata <id> --json` before versioning or deletion. `publish new-version <id> <file> --etag <etag>` preserves the publication identity. `publish download <id> --version <n> --output <path>` retrieves an exact version. Deletion tombstones one exact publication identity and does not imply object-store destruction.

The public URL grants no secrecy. Confirmation flow ownership remains with the lead-magnet application; Publisher owns the file and its delivery policy.
