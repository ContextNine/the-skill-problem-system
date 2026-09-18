## WireGuard

Dependency ID: `wireguard`. It is installed only when the machine registry explicitly selects WireGuard. wireguard-machine-access owns package/application setup, non-secret desired routing, acceptance, and recovery.

Peer keys remain provider-native machine secrets. Never copy another machine's private key or invent a server. Installation and update preserve the reviewed network and verify provider status plus a fresh inbound SSH connection. Removing a peer or route is separate and must not disturb unrelated Kubernetes WireGuard access.
