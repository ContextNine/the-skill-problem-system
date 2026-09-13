## Kubernetes operator kubeconfig

Secret ID: `kubernetes-operator-kubeconfig`. It is a guarded-copy credential available only to machines explicitly assigned an operator role. The logical `k3s-infrastructure` workspace is the issuing authority; its `hetzner-k3s/enroll-kubeconfig.py` flow is the only approved copy route.

The target custody contract is `~/.kube/config`, with `~/.kube` mode `0700` and the file mode `0600`. Enrollment must stage safely, compare source and target digests, preserve recoverable prior state, and never print content. A matching path alone is not acceptance.

Verify digest equality, permissions, current context, and one read-only namespace query. Do not change cluster resources during acceptance. Recovery repeats guarded enrollment from an authorized operator machine through the owning script. Never use ad hoc `scp`, make this a global fleet default, distribute it through agent sync, or place it in the Vault.
