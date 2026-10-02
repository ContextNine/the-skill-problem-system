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

## Exact-adoption checkpoints

The source exact-version path prints one operation reference derived from the requested version,
candidate registry, topology/selected targets, source location and coordinator implementation. Preview
and verify are read-only. Apply uses an owner-only primary-local journal under
`~/.agents/state/fleet-updates/`, never the shared Vault or desired-state registry.

Repeating the same exact command after a known terminal target failure resumes the same request. Every
target is freshly preflighted; already-ready targets receive no activation or reference-file writes.
Pending workers activate before the primary, and the first failed activation stops remaining targets.
An explicit dependency `--target` limits mutation to the named targets, rather than silently upgrading
the primary too. A target-scoped success is not evidence that unselected machines are aligned.

The coordinator checks the topology again for each execution phase. A concurrent desired-registry edit
after target activation is preserved and leaves `recording-conflict`. Desired state is recorded only
after selected apply and verification succeed, then verified again. A post-recording verification failure
remains `verification-failed`, not complete. Changed reviewed inputs produce a new operation reference.

Journal entries contain fixed stages and target statuses, source/policy digests and scope. They contain
no worker error bodies, environment values or protected fingerprints. Files are atomic, flushed,
owner-only and nonsymlink; an OS advisory lock excludes competing exact adoptions on that primary.
The mutation deny marker is written before entering apply.

The journal also binds the authenticated release's component, exact version, full source commit and
canonical catalog SHA-256. Every selected target must observe the same binding before activation. Preview
compares these observations without writing a journal; apply persists the first trusted binding and
requires it again on resume. A changed commit or catalog under the same version stops the operation.
The catalog digest covers value-free release metadata, not protected values or their fingerprints.

The coordinator supplies both pins to each target's fresh preflight, installer command and final
verification. The launcher repeats signature checks and refuses a changed release before running code.
Successful worker reports missing the release binding are invalid. A blocked target is not an excuse to
discard the binding or replace it on retry. A catalog that drifts after preflight cannot silently select
another archive. Matching semantic versions alone remain insufficient release-identity evidence.

Worker responses carry an outcome-known boundary. A preflight failure before mutation is safe to resume;
a missing/malformed response or lost transport cannot certify child termination. Raw transport/worker
error bodies are reduced to fixed references rather than forwarded or stored.

Cancellation after a target begins applying, or a lost coordinator with an applying marker, leaves
`outcome-unknown`. A dead owner PID or released primary lock is not proof that remote children exited.
The coordinator refuses another mutation instead of deleting the marker or retrying blindly. Recovery
of that ambiguous boundary still needs accepted target/installer ownership evidence and a scoped recovery
contract. Do not edit or delete the journal to bypass it.

These are source preparation and synthetic interruption results. Full cutover still needs the real
component's per-target activation serialization, active-consumer approval/health acceptance, primary
execution, actual signed artifacts, both OS families and installed Fleet acceptance. This exact-adoption
lock does not claim to serialize unrelated direct installer or ordinary sync commands. Keep those away
from an active adoption until the owning activation-lock contract is accepted.
