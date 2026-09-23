# Release provenance

`vault release publish --product skills` prepares the public source and version
metadata. Pushing that exact version tag runs the public repository's complete
test suite and creates one deterministic source archive. GitHub publishes the
archive with a SHA-256 checksum and a JSON record containing the full tag
commit, then attests all three files.

The tag must match `release.json`. Verify a downloaded archive with its checksum
and compare `source_commit` in the sidecar release record with the tag's commit.
The checked-in `release.json` remains the installer-facing product version; the
sidecar is the immutable artifact provenance record.
