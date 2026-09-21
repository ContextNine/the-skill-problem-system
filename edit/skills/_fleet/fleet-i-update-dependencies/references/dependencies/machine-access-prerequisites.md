## Machine access prerequisites

Dependency ID: `openssh`. Regular OpenSSH with registry-owned aliases, dedicated fleet identities, exact host-key pinning, and the selected WireGuard or Tailscale route is the fleet transport contract.

fleet-shell-mesh owns key enrollment and acceptance. Verify a new connection in each required direction without printing private material. SSH service changes, host-key replacement, or authorization removal require the onboarding recovery flow and explicit review.
