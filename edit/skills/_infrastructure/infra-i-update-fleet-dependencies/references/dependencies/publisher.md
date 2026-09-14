## Publisher CLI

Dependency ID: `publisher-cli`. The only executable is `publish`; retired publisher command names are not aliases.

Publisher is installed from the exact immutable public release in the `ctx9` component catalog. The launcher verifies the archive checksum and delegates installation and doctor checks to Publisher's release-owned installer. Fleet state accepts Publisher only when `ctx9 doctor publisher --json` reports the declared `3.1.0` release.

The former File Upload and Artifacts CLI packages are retired. They are not aliases, selected dependencies, or independent installers; one product retains one `publish` command.
