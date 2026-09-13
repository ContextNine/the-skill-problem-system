## Secret Bindings

Dependency ID: `secret-bindings`. Fleet desired state installs the exact accepted private machine release through the public `ctx9` launcher and the narrow `ctx9-gitlab-group-read` credential binding. The dependency registry stores only the immutable value-free private catalog URL, accepted semantic version, and lifecycle metadata.

The desired fleet release is `1.3.2`, source `d147433233d8e10048e66756b50bb7105bf1e205`. Its release pipeline published signed, value-free machine artifacts and an exact private component catalog. Mattbook, Worker Mac Air, and Wootbook all run `1.3.2`; the CLI and broker verify through the Fleet dependency contract.

`fleet update --dependency secret-bindings --version <exact-version>` records and adopts one release; narrow fleet sync then verifies the installed semantic version. When installation is required, the adapter passes the credential-free catalog URL to `ctx9`, which authenticates internally, verifies the exact host archive checksum, and delegates atomic activation to the release-owned installer. A missing narrow credential is a hard onboarding checkpoint with no source-checkout or broad-token fallback. Machine identities remain in native Keychain or Secret Service custody and follow machine-local-secrets-and-enrollment.

The `secret-bindings` workspace remains an ordinary development checkout and does not own runtime availability. A later public conversion changes the catalog/access contract only after identical macOS and Linux acceptance. Routine dependency work never rotates identities, revokes credentials, or touches production.
