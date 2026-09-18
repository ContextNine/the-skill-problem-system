## Optional developer tools

Dependency IDs routed here include `bun`, `docker`, `kubectl`, `helm`, `sops`, `rclone`, and `coding-provider-launchers`. They are approved capabilities but are installed only when a machine capability or owning repository explicitly selects them.

Onboarding or the owning repository supplies the exact official installer/package and acceptance contract. Verify command ownership and a real non-destructive use case before recording readiness. Authentication remains separate and follows machine-local-secrets-and-enrollment. Do not turn an observed command into a fleet default, substitute an editable checkout, alter Kubernetes resources, log into a registry, or remove data during routine sync.
