---
type: agent-reference
status: enabled
---

## Fleet shell mesh

Every enabled personal fleet machine is both an OpenSSH client and server over its registered Tailscale MagicDNS hostname. The primary remains the controller for enrollment, but communication is not artificially limited to primary-to-worker connections. Disabled machines are never included. This explicit Tailscale acceptance matrix proves a common emergency/control path; canonical aliases separately follow each target machine's selected provider.

Each machine owns one unique fleet-shell Ed25519 identity. Its private key is generated on that machine, never copied, and kept separate from GitHub, signing, deployment, WireGuard, Tailscale, and Secret Bindings identities. The private registry records only its non-secret path:

```json
{
  "fleet_shell": {
    "identity_file": "~/.ssh/id_ed25519_fleet_shell_MACHINE_ID"
  }
}
```

An already verified dedicated fleet-shell identity may retain its reviewed path. Never adopt a GitHub or repository key merely because it already exists.

### Trust directions

Every directed connection requires both gates:

```text
source verifies target host key
target authorizes source public key
```

For each enabled source-target pair:

1. Verify the target's ED25519 host-key fingerprint on the target or through an already trusted route.
2. Pin that exact key for the target's registered Tailscale hostname on the source. Use `trust_known_host_alias.py` when another reviewed hostname already has the same key. Never use `ssh-keyscan`, `accept-new`, or disabled host checking as identity proof.
3. Generate the source's dedicated fleet-shell key locally with `fleet_shell_access.py provision`. Protected native-agent custody is required by default. A passphrase-free exception is a separate explicit approval, never implied by Linux or unattended use.
4. Show the public fingerprint and obtain approval before enrollment.
5. Send only the public key to each other enabled target and use `fleet_shell_access.py authorize` to manage its source-specific `authorized_keys` block.
6. Require a brand-new command with `BatchMode=yes` and `StrictHostKeyChecking=yes` in every direction.

Provision from a target-local terminal or a standalone `ssh -t` session whose stdin is the real terminal:

```bash
helper="$HOME/.agents/skills/infra-i-onboard-machine/scripts/fleet_shell_access.py"
python3 "$helper" provision --machine-id MACHINE_ID --identity-file ~/.ssh/id_ed25519_fleet_shell_MACHINE_ID --dry-run
python3 "$helper" provision --machine-id MACHINE_ID --identity-file ~/.ssh/id_ed25519_fleet_shell_MACHINE_ID --apply
python3 "$helper" inspect --machine-id MACHINE_ID --identity-file ~/.ssh/id_ed25519_fleet_shell_MACHINE_ID
```

The apply command runs `ssh-keygen` interactively and loads the protected key into macOS Keychain's native agent or the current reviewed Linux SSH agent. Never pipe a passphrase, place it in argv, or create a passphrase-free key without explicit approval.

On macOS, source-aware fleet rendering adds `UseKeychain yes` and `AddKeysToAgent yes` to managed routes. Reboot acceptance must remove the fleet-shell identity from the native agent, open a brand-new strict managed connection, and verify that Keychain restored the identity to the agent without prompting. This proves durable custody rather than merely accepting an identity left loaded by provisioning.

Authorize one approved public key on a target without printing or copying private material:

```bash
python3 "$helper" authorize \
  --source-machine-id SOURCE_ID \
  --expected-fingerprint SHA256:FINGERPRINT \
  --public-key-file /reviewed/path/source.pub \
  --dry-run
python3 "$helper" authorize \
  --source-machine-id SOURCE_ID \
  --expected-fingerprint SHA256:FINGERPRINT \
  --public-key-file /reviewed/path/source.pub \
  --apply
python3 "$helper" authorize \
  --source-machine-id SOURCE_ID \
  --expected-fingerprint SHA256:FINGERPRINT \
  --public-key-file /reviewed/path/source.pub \
  --verify
```

The helper owns only its exact `ctx9 fleet shell: SOURCE_ID` marker block, preserves unrelated authorized keys, refuses conflicting managed fingerprints, writes atomically, and enforces `0700`/`0600` SSH permissions.

### Acceptance matrix

For every enabled source and every other enabled target, verify the Tailscale hostname explicitly:

```bash
ssh -o BatchMode=yes \
  -o ConnectionAttempts=1 \
  -o ConnectTimeout=10 \
  -o StrictHostKeyChecking=yes \
  -o IdentitiesOnly=yes \
  -i FLEET_SHELL_IDENTITY \
  USER@TARGET.TAILNET.TS.NET true
```

Record the directed matrix, fingerprints, accepted exceptions, and remaining failures in private machine notes. Full-mesh shell access does not itself broaden Vault authority: only the registered owner may run Vault Git or `vault refresh`. Linux remains Code-only unless schema v7 separately enrolls that machine as a healthy `remote-sshfs` client through [[linux-remote-vault-access|Linux Remote Vault Access]].
