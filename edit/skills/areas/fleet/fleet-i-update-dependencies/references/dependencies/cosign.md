## Cosign release verifier

Dependency ID: `cosign`.

Fleet installs the exact upstream 3.1.3 executable using its `github-binary`
recipe and architecture-specific SHA-256. Supported recipes cover Linux x86_64
and macOS arm64. Additional architectures require reviewed upstream artifacts,
not architecture substitution or a source build.

The adapter downloads only a public versioned GitHub release asset, verifies it
before making it executable, stages a versioned directory and atomically selects
its managed command. Verification checks both the selected file digest and its
reported version. A checksum mismatch or an unmanaged command collision stops
without replacing that command. A damaged retained version requires reviewed
recovery, not silent overwrite.

Cosign is an explicit prerequisite for private component preflight. Enroll it
through the primary-owned Fleet workflow before attempting a private component
adoption. No missing-verifier bypass, task-cache binary or application checkout
belongs on the normal command path.

Older Ubuntu-packaged 2.6.2 is not accepted. Upstream fixed its legacy-bundle
identity bypass in 2.6.5 and 3.1.3. The fleet selects the same patched 3.1.3 line
as hosted release checks. See the [upstream advisory](https://github.com/sigstore/cosign/security/advisories/GHSA-fx35-mq7g-6g98).

This dependency verifies signatures. It does not enroll signing keys or obtain
publication, registry or deployment credentials. Native Notenv/bootstrap custody
and actual component installation retain their separate acceptance gates.
