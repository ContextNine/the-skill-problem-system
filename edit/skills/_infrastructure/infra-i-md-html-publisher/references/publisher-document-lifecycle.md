# Publisher document lifecycle

`publish` is the sole command. Configuration uses the Publisher API, rendered, and public-file origins; authenticate with `publish login --token-stdin`.

Discover documents with `publish list --kind document --json`, then inspect one with `publish read <id> --json` or `publish metadata <id> --json`. Download canonical source with `publish download <id> --version <n> --output <path>`.

Publish uses Publisher `document` with rendered presentation. Use namespace `public` with `unlisted` visibility by default for link-shareable documents and `public` visibility only when the request clearly authorizes public listing. Use namespace `private` with `tenant` or `restricted` visibility for authenticated documents. Stable publication identity comes from the returned ID, not a local path mapping.

Create a new version with the current ETag to keep the same publication identity. Use `publish delete <id> --etag <etag> --yes` only for exact, explicitly requested tombstoning. Historical URLs in dated records remain evidence, not active compatibility routes.
