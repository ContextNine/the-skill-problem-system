## Optional developer tools

Dependency IDs routed here include `bun`, `docker`, `kubectl`, `helm`, `sops`, `rclone`, and `coding-provider-launchers`. They are approved capabilities but are installed only when a machine capability or owning repository explicitly selects them.

Onboarding or the owning repository supplies the exact official installer/package and acceptance contract. Verify command ownership and a real non-destructive use case before recording readiness. Authentication remains separate and follows `$fleet-i-onboard-machine` (machine-local-secrets-and-enrollment). Do not turn an observed command into a fleet default, substitute an editable checkout, alter Kubernetes resources, log into a registry, or remove data during routine sync.


`maintenance-eval-bubblewrap` is an optional Linux-only dependency for explicitly
authorized local maintenance evals. Its apt package is `bubblewrap`; verify with
`bwrap --version` and the runner's no-model sandbox preflight. It is not required
for normal cluster maintenance and does not authorize running fault injection,
using a remote Docker daemon or changing host namespace policy. Docker remains
an explicitly selected local capability. Impression owns the eval's Node 22 and
esbuild prerequisites in its existing checkout. Missing model custody is a
separate blocker, never an installer or credential-relay fallback.
