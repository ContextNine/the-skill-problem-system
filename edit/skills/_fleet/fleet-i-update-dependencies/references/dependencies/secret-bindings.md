## Secret Bindings

Dependency ID: `secret-bindings`. Fleet desired state installs the exact accepted private machine release through the public `ctx9` launcher and the narrow `ctx9-gitlab-group-read` credential binding. The dependency registry stores only the immutable value-free private catalog URL, accepted semantic version, and lifecycle metadata.

Read the installed dependency registry for the selected Secret Bindings version and source. Its release pipeline publishes signed, value-free machine artifacts and a private component catalog. Verify the CLI and broker on each eligible machine through the Fleet dependency contract; do not assume a particular fleet's installed state.

`fleet update --dependency secret-bindings --version <exact-version>` records and adopts one release; narrow fleet sync then verifies the installed semantic version. When installation is required, the adapter passes the credential-free catalog URL to `ctx9`, which authenticates internally, verifies the exact host archive checksum, and delegates atomic activation to the release-owned installer. A missing narrow credential is a hard onboarding checkpoint with no source-checkout or broad-token fallback. Machine identities remain in native Keychain or Secret Service custody and follow machine-local-secrets-and-enrollment.

The `secret-bindings` workspace remains an ordinary development checkout and does not own runtime availability. A later public conversion changes the catalog/access contract only after identical macOS and Linux acceptance. Routine dependency work never rotates identities, revokes credentials, or touches production.
