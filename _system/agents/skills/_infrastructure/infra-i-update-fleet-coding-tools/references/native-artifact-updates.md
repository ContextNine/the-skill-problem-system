# Native Artifact Updates

## T3 Code nightly desktop on macOS

1. Search `/Applications` and the target user's `~/Applications` for app bundles. An app qualifies only when `Info.plist` reports bundle identifier `com.t3tools.t3code`, a version containing `-nightly.`, and `Resources/app-update.yml` identifies the GitHub nightly prerelease channel.
2. Resolve the exact T3 nightly once as directed by the parent skill. Query the configured GitHub repository's releases API for the single prerelease tagged `v<exact-version>`. Select the DMG matching `uname -m` (`arm64` or `x64`), and require the API's nonempty `sha256:` asset digest.
3. Prefer the app's built-in updater when it can install and verify that exact version. Otherwise download the matching DMG to a new temporary directory, compare its SHA-256 with the API digest, and mount it read-only without browsing.
4. Before replacement, require the candidate's bundle identifier and version to match expectations. Run `codesign --verify --deep --strict`; require `spctl --assess --type execute` to pass; and require the candidate's signing TeamIdentifier to equal the installed app's TeamIdentifier.
5. If the app is running, quit it cleanly and confirm it exited. Preserve the installed bundle as a same-volume temporary backup, install the candidate at the identical path, and verify identifier, version, signature, TeamIdentifier, and launchability. Restore the backup if any check fails; remove it only after all checks pass.
6. Detach the image and remove temporary downloads. Do not alter app preferences, updater configuration, or user data.

## Legacy Codex machine-image recovery on Linux

Current `codex-machine-image` installations use OpenAI's official user-owned standalone layout under `~/.codex/packages/standalone`, exposed through `~/.local/bin/codex`. The procedure below exists only to recover older images that still have a single root-owned binary. Do not prefer it over an explicitly authorized migration with OpenAI's official standalone installer.

Treat this channel as confirmed only when all of these hold:

- `/etc/codex-machine-image-version` is a readable regular file containing a `codex=` image pin.
- `/usr/local/bin/codex` is the resolved command, a root-owned regular executable, and not owned by an OS package manager.
- The target is a registered machine whose provisioning source is the topology registry's logical `codex-machine-image` repository.

Legacy recovery procedure:

1. Query the official `openai/codex` latest GitHub release API. Require a stable tag shaped `rust-v<version>`, then select exactly one `codex-<architecture>-unknown-linux-musl-bundle.tar.zst` asset (`x86_64` or `aarch64`) with a nonempty `sha256:` digest.
2. Download into a new temporary directory with redirect following, failure-on-HTTP-error, and retries. Compare the archive SHA-256 with the API digest before extraction.
3. Extract without writing outside the temporary directory. Require exactly one executable named `codex`; run that candidate's `--version` and require it to equal the release version.
4. Require authorized privilege elevation. Install the candidate to a new root-owned mode-`0755` sibling path under `/usr/local/bin`, verify that staged executable again, then atomically rename it over `/usr/local/bin/codex`. The existing executable remains untouched until every download, digest, extraction, and candidate-version check passes.
5. Verify `command -v codex` is still `/usr/local/bin/codex`, `codex --version` equals the release version, and ownership/mode remain correct. A failed post-replacement check is a failed update and must restore the prior executable retained in the temporary backup.
6. Do not edit `/etc/codex-machine-image-version`; it records immutable installation provenance and the original image pin, not the currently installed tool version.

Never use this native procedure for an unmarked standalone executable or guess an asset architecture, repository, digest, or privilege method.
