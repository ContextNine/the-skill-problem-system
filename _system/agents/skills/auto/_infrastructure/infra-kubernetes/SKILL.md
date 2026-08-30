---
name: infra-kubernetes
description: Diagnoses Kubernetes and k3s workloads, CNPG, ingress, scheduling, and persistent storage with read-only inspection by default. Use for pod failures, rollout trouble, cluster events, CNPG health, PVC or Longhorn/CSI faults, and production Kubernetes investigation.
---

# Infra · Kubernetes

Use `$infra-code-folder-and-computer-topology` to resolve the current machine and the `k3s-infrastructure` checkout. Read its `AGENTS.md`, `README-infrastructure.md`, and the closest component README before acting.

## Default investigation

Stay read-only unless the user explicitly asks for remediation. Establish the target cluster, namespace, workload, and incident window without assuming old node placement or manifest values remain current.

```bash
kubectl config current-context
kubectl get nodes -o wide
kubectl get pods -A
kubectl get events -A --sort-by=.lastTimestamp
kubectl -n <namespace> describe pod <pod>
kubectl -n <namespace> logs <pod> --all-containers --since=30m
kubectl -n <namespace> get deploy,statefulset,job,cronjob,pvc
```

- Prefer `get`, `describe`, `logs`, events, and manifest inspection.
- Correlate pod status with owner controllers, recent events, readiness probes, scheduling constraints, PVCs, and node health.
- Inspect desired state in the k3s repository before proposing a live change. Current manifests and live state override historical notes.
- Do not use broad delete, rollout restart, scale, patch, drain, or apply operations as diagnostic shortcuts.

## Handoffs

- For database queries, locks, slots, WAL, or schema evidence, use `$infra-run-postgresql`.
- For CNPG trouble, inspect cluster and instance status first; then follow the PostgreSQL runbook in the resolved k3s checkout.
- For connection-pool symptoms, separate PgBouncer health from PostgreSQL health before changing either.
- For pending pods or attachment errors, investigate nodes, Longhorn/CSI, volumes, and PVC events before restarting CNPG or applications.
- For application alerts and remediation orchestration, use the relevant projected repo skill, such as `$incident-controller-remediate-production`.

## Mutation guardrail

Before any mutation, state the exact resource and namespace, evidence, expected effect, rollback, and verification. Re-read live state immediately beforehand. Apply only the smallest authorized change, then verify workload health, events, logs, and dependent services.
