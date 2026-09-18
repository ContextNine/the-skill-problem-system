---
type: agent-reference
status: enabled
---

## WireGuard machine access

Version one joins an existing WireGuard network. Before selection, tell the user they need a reachable WireGuard server or network; one possible approach is deploying an existing Kubernetes WireGuard Helm chart. The portable Vault workflow does not provision a generic public server. A private enrollment adapter remains owned by its infrastructure repository.

Generate a unique private identity on the target. Never copy another machine's private key, preshared key, or configuration. Store only the reviewed mesh address and client variant under `machine_access.providers.wireguard`.

For a NATed worker expected to accept inbound traffic, require `PersistentKeepalive = 25`. Verify actual unattended behavior rather than accepting a configuration line or Connected label.

On macOS, prefer the official WireGuard application, its native login helper, and On-Demand Activation for Ethernet and Wi-Fi. Do not add a parallel `wg-quick` or LaunchAgent service. On Linux, use the owning network's supported package and service procedure.

After enrollment:

1. Configure the route with `vault machine access configure MACHINE_ID wireguard --host ADDRESS --client-variant native-app|wg-quick`.
2. Render source-aware aliases across every enabled machine and verify `MACHINE_ID-mesh`, then the canonical alias from every other enabled source.
3. Disconnect Screen Sharing and existing SSH streams, wait beyond the NAT idle window, and open a brand-new inbound `MACHINE_ID-mesh` connection.
4. On a worker Mac, first complete [worker-mac-power-and-sleep](worker-mac-power-and-sleep.md). Confirm no matching system-sleep or WireGuard Network Extension suspension event occurred.
5. Run `vault machine access inspect MACHINE_ID --provider wireguard`. On Linux this reports sanitized handshake age and 25-second-keepalive counts without printing keys or endpoints; on the native macOS client it reports connected-tunnel counts plus fresh inbound SSH evidence. Record the accepted evidence and latency in the private machine note.
6. When the primary selects WireGuard, open a new canonical reverse tunnel from every enabled worker to the primary. Prove its primary-loopback listener reaches the worker-loopback target, then close it and prove cleanup. Reverse forwarding uses the primary target's selected provider; `-R` never changes route selection.

If the native macOS client reports Connected but fresh peer TCP probes fail, treat the session as stale. Confirm the exact tunnel name with `scutil --nc list`, restart only that existing client with `scutil --nc stop TUNNEL` then `scutil --nc start TUNNEL`, and repeat hub, peer, canonical SSH, and reverse-forward checks. Do not change the server, peer registry, or tunnel configuration merely to clear stale client state.

WireGuard Connected state, an outbound target ping, and an existing SSH stream are not inbound acceptance.
