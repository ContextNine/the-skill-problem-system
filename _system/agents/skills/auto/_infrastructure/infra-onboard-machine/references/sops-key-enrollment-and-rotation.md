---
type: agent-reference
status: enabled
---
# SOPS Key Enrollment and Rotation

Primary machine is authority for shared age identities. Canonical active identity file is `~/.sops/key.txt`, directory mode `0700`, file mode `0600`. Never store private identities in Vault, Git, browser profiles, shell history, logs, or machine registry.

## Contents

- [[#Enroll machine]]
- [[#Verify fleet]]
- [[#Rotate identity]]
- [[#Failure rules]]

## Enroll machine

Confirm target identity through [[machine-requirements-and-topology|Machine Requirements and Topology]], then run from Primary machine:

```bash
SKILL_DIR="$(vault root)/_system/agents/skills/auto/_infrastructure/infra-onboard-machine"
python3 "$SKILL_DIR/scripts/enroll_sops_key.py" \
  --host <machine> \
  --verify-repo /absolute/path/to/repository
```

Helper hashes source and target without printing identity, copies directly through SSH, validates every public recipient returned by `age-keygen -y`, enforces permissions, and decrypts one tracked SOPS file from optional verification repository. Different existing target identity stops enrollment. Use `--replace` only after confirming target should adopt Primary machine authority; replacement creates timestamped adjacent backup.

Repositories remain responsible for their own decrypt-only bootstrap. Do not run environment post-update merely to enroll a machine.

## Verify fleet

Rediscover repositories and recipients instead of trusting a static list:

```bash
rg --hidden --files "$HOME/Code" -g '.sops.yaml' -g '!**/.git/**' -g '!**/node_modules/**'
age-keygen -y "$HOME/.sops/key.txt"
```

Observed 2026-07-19: canonical Impression and personal monorepo configurations use same public recipient. Physical clones are not separate rotation authorities; change and commit each canonical repository once, then update clones through Git.

For every enabled machine needing decryption, verify identity digest, recipient, permissions, and a repository decrypt smoke test. Never infer readiness from file presence alone.

## Rotate identity

Rotation is two-phase so old and new identities overlap until every repository and machine accepts new key.

1. Inventory every canonical `.sops.yaml`, tracked encrypted SOPS file, eligible machine, and offline recovery copy. Stop if ownership or repository status is unclear.
2. Generate new identity on Primary machine into protected staged file. Record public recipient only. Preserve old private identity in encrypted offline recovery storage outside Vault and Git.

```bash
install -d -m 0700 "$HOME/.sops"
age-keygen -o "$HOME/.sops/key.next.txt"
chmod 0600 "$HOME/.sops/key.next.txt"
age-keygen -y "$HOME/.sops/key.next.txt"
```

3. Create temporary authority bundle containing old and new identities with mode `0600`. Deploy bundle to every eligible machine using enrollment helper with `--replace`; verify both public recipients and existing decrypts.
4. In each canonical repository, add old and new public recipients to `.sops.yaml`. Update every tracked encrypted SOPS file from repository root:

```bash
git ls-files | rg '(^|/)\.env.*\.sops$|\.sops\.'
sops updatekeys --yes <encrypted-file>
```

Review only recipient metadata changes, test decrypt with old identity alone and new identity alone, then commit repository changes.
5. Promote new identity: distribute new-only file to every eligible machine, verify repository decrypts, and update Primary machine active `~/.sops/key.txt` atomically while preserving protected rollback copy.
6. Remove old public recipient from each canonical `.sops.yaml`, run `sops updatekeys --yes` again for every encrypted file, test new-only decrypt across fleet, then commit.
7. Retire old active copies only after all canonical repositories, clones, machines, CI/deployment consumers, and offline recovery records pass. Keep offline recovery until separately reviewed retention period ends.

`sops updatekeys` changes recipient wrapping without changing environment values. Do not run `run-after-updating-env.sh` for recipient-only rotation. If values also change, follow owning repository env workflow separately.

## Failure rules

- Different target key without explicit reviewed replacement: stop.
- Missing repository recipient, decrypt failure, unsafe permissions, unknown machine, or dirty canonical encrypted files: stop.
- Lost old key before new-only verification: restore protected backup; do not regenerate encrypted values.
- Never delete old identity during overlap phase.
- Never print private identity or decrypted file contents for diagnosis.
