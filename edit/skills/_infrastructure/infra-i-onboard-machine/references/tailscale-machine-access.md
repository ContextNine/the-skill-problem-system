---
type: agent-reference
status: enabled
---

## Tailscale machine access

Use Tailscale for personal machines only after the user selects it explicitly. Personal-plan eligibility and account identity are user choices. Stop for sign-in, account selection, MFA, VPN approval, and any Terms of Service checkpoint. Never create or store an auth key unless the user separately requests a reviewed automated-enrollment design.

Use the skill's deterministic setup controller instead of recreating platform commands:

```bash
tailscale_setup="$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/setup_tailscale_access.py"
registry="$(vault root)/_system/agents/edit/settings/fleet/machines.json"
python3 "$tailscale_setup" MACHINE_ID --registry "$registry" --dry-run
python3 "$tailscale_setup" MACHINE_ID --registry "$registry" --apply
```

The controller reads the non-secret desired state from the registry. On macOS it downloads the newest official standalone package recommended by [Tailscale macOS installation](https://tailscale.com/docs/install/mac), verifies Tailscale installer Team ID `W5364U7YZB` and Apple's installer assessment, stages it on the target, and opens Installer. If the existing mesh is too slow to copy the package, the target downloads the same official URL directly and must match the locally verified SHA-256 before the controller rechecks the target-side signer. On Linux it downloads the official [Tailscale Linux installation](https://tailscale.com/docs/install/linux) script, records its SHA-256, validates shell syntax, stages it, and runs it when noninteractive sudo is already available. If sudo needs a password, it prints one standalone `ssh -t` command so stdin remains the real terminal.

The controller stops only for the protected macOS Installer/VPN approval or personal tailnet authentication. It never creates an auth key, chooses an account, or stores login state. Rerun the same `--apply` command after each checkpoint. Once the device is running, it prints the exact `vault machine access configure` command with the sanitized MagicDNS name and reviewed client variant.

The App Store variant remains acceptable when selected deliberately, but the controller does not replace or mix variants. On Linux it applies the registry-owned device name with DNS enabled, subnet routes disabled, and Tailscale SSH disabled. Regular OpenSSH remains the fleet identity.

The private registry tracks those non-secret desired settings. Account identity, device authorization, node keys, control-plane state, and local VPN state remain machine-local and never enter Git. Regular OpenSSH remains the only fleet SSH identity.

After the setup controller reports `Running`:

1. Confirm the intended machine appears in the intended tailnet and MagicDNS is enabled.
2. Record the stable full MagicDNS name or reviewed Tailscale address with:

```bash
vault machine access configure MACHINE_ID tailscale \
  --host MACHINE.TAILNET.TS.NET \
  --client-variant standalone|app-store|linux-package
```

3. Run `vault machine access inspect MACHINE_ID --provider tailscale`. It performs fresh SSH samples plus sanitized `tailscale netcheck` and `tailscale ping` inspection without changing the canonical provider. Do not persist or quote account identifiers, public endpoints, or auth material.
4. Classify the settled path as `direct`, `peer-relay`, or `DERP`. A first DERP packet followed by direct packets is normal coordination. Direct is the latency target, not a guarantee; persistent relay must be reported.
5. Compare `vault machine access inspect MACHINE_ID --provider wireguard` with the Tailscale result from the home LAN and, when available, a genuinely remote network. Record evidence in the private machine note.
6. Preview and apply `vault machine access switch MACHINE_ID tailscale` only after the explicit route works from every other enabled source. The switch renders each source machine's canonical alias and verifies the complete directed target path. Keep WireGuard available for rollback and for unrelated Kubernetes routes.

OpenSSH trust is hostname-specific. If the same reviewed server was already trusted through another provider address, verify its SHA-256 host-key fingerprint on that server and copy only the exact matching trusted record to the Tailscale hostname on each connecting machine:

```bash
helper="$(vault root)/_system/agents/edit/skills/_infrastructure/infra-i-onboard-machine/scripts/trust_known_host_alias.py"
python3 "$helper" --source-host OLD_TRUSTED_HOST --target-host MACHINE.TAILNET.TS.NET --expected-fingerprint SHA256:FINGERPRINT --dry-run
python3 "$helper" --source-host OLD_TRUSTED_HOST --target-host MACHINE.TAILNET.TS.NET --expected-fingerprint SHA256:FINGERPRINT --apply
python3 "$helper" --source-host OLD_TRUSTED_HOST --target-host MACHINE.TAILNET.TS.NET --expected-fingerprint SHA256:FINGERPRINT --verify
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes MACHINE.TAILNET.TS.NET true
```

The helper accepts hashed source entries, refuses target-key conflicts, writes only the exact already trusted key, and records no private material. Do not learn the key from the untrusted route itself.

After provider setup, complete [[fleet-shell-mesh|Fleet Shell Mesh]]. Every enabled machine must pin every other enabled machine's Tailscale host key, authorize its dedicated fleet-shell public key on every peer, and pass the complete directed strict-SSH matrix. Tailscale reachability alone is not fleet-shell acceptance.

Use regular OpenSSH through the canonical alias. Do not make Tailscale SSH a hidden second identity. Tailscale coordination and NAT traversal can improve reachability, but they cannot wake a sleeping Mac; worker Macs must complete [[worker-mac-power-and-sleep]].

Route selection belongs to the SSH target, not the source and not the `-L` or `-R` forwarding option. Reverse forwarding works normally over Tailscale: `ssh -R ... PRIMARY_ID` resolves the primary's canonical alias first and carries the forward inside that Tailscale-backed SSH connection when Tailscale is selected.
