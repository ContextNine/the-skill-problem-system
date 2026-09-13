## Package-managed dependencies

The authoritative IDs and exact platform recipes are in `../dependencies.json`. `fleet sync --dependencies` installs missing required entries and verifies commands before writing factual locks. `--dry-run` is non-mutating and `--verify` never installs or updates.

Homebrew and Homebrew cask are used on macOS, APT on Linux, npm and uv only through the approved user-local prefixes, and release archives only when the manifest supplies an official URL and checksum. Package updates remain inside the declared channel. Do not substitute an editable workspace checkout, arbitrary installer pipe, or unverified archive.

Authentication is separate from installation. Use [[machine-local-secrets-and-enrollment]] for GitHub, cloud, package-registry, or provider sessions. Removal is never implied by sync or update and needs an explicit request plus ownership verification.
