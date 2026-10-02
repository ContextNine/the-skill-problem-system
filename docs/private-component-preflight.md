# Private component preflight

Private `ctx9-component` recipes use the installed launcher to check the exact authenticated catalog and
signed release on every selected target. This check runs even when the installed version already matches.
The old helper-file-exists check was not evidence of credential or catalog readiness.

The source implementation requires a launcher with `preflight` and the trusted private-release contract.
Release and accept the launcher, its Cosign verifier and Fleet before adopting this workflow. An older
launcher reports `launcher-upgrade-required`; there is no source-checkout or public-package fallback.

Each private recipe needs:

- An exact credential-free GitLab Generic Package `private_catalog_url`.
- `credential_binding: ctx9-gitlab-group-read`.
- `provenance_project`, the locally reviewed GitLab namespace/project allowed to sign that component.
- The owning contract's `verify.exact` version matching the catalog URL.

The launcher pins the GitLab issuer and exact version-tag CI certificate identity from these settings,
verifies the signed catalog/source/platform/digests, and returns a value-free report. Fleet validates the
report's schema, component, version, full source commit and target platform. Installation receives the same
policy and repeats trust verification before downloading/executing the archive installer. Archive-byte
checksum acceptance happens there; preflight does not claim to have downloaded the archive.

A missing policy, verifier, locked store, rejected credential, inaccessible release, transport failure or
trust mismatch is a visible preflight blocker. Malformed output is not printed. Apply stops before package
or reference-file writes, and verify cannot report aligned while the private preflight is blocked. A failed
installation prints a fixed diagnostic and asks for fresh exact preflight instead of echoing raw child output.

Primary-owned source/configuration and desired-state recording remain unchanged. Do not run worker Vault
Git/sync, silently enroll a helper or rotate a credential to bypass a blocker. Updating the public Fleet
source does not update installed private recipes. Migrate the primary's reviewed policy as part of release
acceptance, without changing its chosen dependency version in this source-only implementation step.

Run the focused synthetic journey and complete package suite with Python 3.12:

```bash
python3.12 -m unittest discover -s internal/tests -v
```

The synthetic journey verifies already-current targets still authenticate, blocked applies write nothing,
wrong-version/malformed responses fail closed, and an accepted no-install apply records factual state. It
does not prove live signing, real Cosign trust, native-store recovery or fleet-wide rollout.
