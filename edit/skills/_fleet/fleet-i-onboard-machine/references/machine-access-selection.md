---
type: agent-reference
status: enabled
---

## Machine access selection

Select exactly one provider for each target machine's personal fleet access: `wireguard` or `tailscale`. Neither is the default. The target's choice owns its canonical SSH route from every enabled source machine, including Codex, T3 Code, Claude Code, Screen Sharing, terminal, workspace-sync, notification, and reverse-forward connections. It does not replace a separate WireGuard tunnel used only for Kubernetes or business infrastructure.

Enabled personal machines additionally follow [Fleet Shell Mesh](fleet-shell-mesh.md): every machine can initiate regular OpenSSH connections to every other enabled machine over registered Tailscale MagicDNS. This symmetric shell reachability does not transfer primary-only Vault authority.

The Git-backed private machine registry owns every non-secret reproducibility fact:

```json
{
  "ssh_alias": "worker",
  "machine_access": {
    "provider": "tailscale",
    "ssh_user": "matt",
    "identity_file": "~/.ssh/codex_fleet_ed25519",
    "lan_host": "worker.local",
    "providers": {
      "wireguard": {"state": "configured", "host": "10.13.13.10"},
      "tailscale": {
        "state": "configured",
        "host": "worker.example.ts.net",
        "client_variant": "standalone",
        "desired_state": {
          "device_name": "worker",
          "accept_dns": true,
          "accept_routes": false,
          "tailscale_ssh": false
        }
      }
    }
  }
}
```

Never store WireGuard private keys, preshared keys, Tailscale auth keys, node keys, login sessions, or account tokens in the registry, notes, Git, generated SSH configuration, or agent output.

Canonical `Host worker` is the durable application identity. `worker-lan` forces the reviewed LAN route and `worker-mesh` forces that target's selected provider. A source machine's own provider choice never overrides the target's choice. Provider-specific aliases such as `-wg` or `-tailscale` are unsupported. Full-mesh Tailscale acceptance uses the registered MagicDNS hostname explicitly and remains separate from canonical route selection.

Render source-aware aliases on the primary and every enabled worker with:

```bash
vault machine access render --dry-run
vault machine access render
```

The renderer runs from the registered primary, owns only `~/.ssh/config.d/vault-machine-access.conf` on each enabled source, and ensures the top-level `Include ~/.ssh/config.d/*` line. It preserves unrelated SSH configuration, uses each source machine's own fleet-shell identity, excludes the source itself, and disables password and keyboard-interactive fallback. Use repeated `--target SOURCE_ID` only to narrow a repair or verification; the default covers every enabled source.

Every managed route enforces strict host-key checking. On a macOS source, the rendered route also enables `UseKeychain` and `AddKeysToAgent` so a protected fleet-shell identity already enrolled in Keychain is recovered on the first connection after login or reboot. Linux sources never receive those Apple-only options.

Configure a second provider without changing consumers:

```bash
vault machine access configure MACHINE_ID tailscale \
  --host MACHINE.EXAMPLE.TS.NET \
  --client-variant standalone \
  --dry-run
vault machine access configure MACHINE_ID tailscale \
  --host MACHINE.EXAMPLE.TS.NET \
  --client-variant standalone
```

Switch only after the new provider is installed and authenticated:

```bash
vault machine access switch MACHINE_ID tailscale --dry-run
vault machine access switch MACHINE_ID tailscale
```

The apply path verifies the new route from every other enabled source, atomically updates the registry, renders every enabled source's managed SSH include, verifies fresh canonical connections, and restores the old provider automatically if verification fails. Keep the old provider configured for rollback until Codex, T3 Code, Claude Code, terminal, workspace sync, Screen Sharing, notifications, and reverse forwarding pass. Retiring an old route is separate explicit work.

`-L` and `-R` do not select a transport. SSH resolves the target alias first, so `ssh -R ... PRIMARY_ID` uses the primary target's selected provider. Acceptance must start a new passwordless reverse tunnel from every enabled non-primary source to the canonical primary alias, prove the listener on primary loopback, close the temporary tunnel, and confirm the listener disappears. Do not accept an already-running tunnel, direct provider hostname, or password fallback as evidence.

Record direct/relay classification and latency evidence in the private machine note. Store a stable MagicDNS FQDN or reviewed provider address in the registry, not a transient endpoint or public NAT address.
