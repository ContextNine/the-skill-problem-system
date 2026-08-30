---
name: infra-run-postgresql
description: Runs safe PostgreSQL investigations and diagnoses queries, locks, replication slots, WAL, connections, and CNPG/PgBouncer boundaries with read-only SQL by default. Use for SQL debugging, PostgreSQL incidents, database performance, connection failures, or replication health.
---

# Infra · Run PostgreSQL

Use `$infra-code-folder-and-computer-topology` to resolve the owning application and `k3s-infrastructure` checkouts. Read their `AGENTS.md`, database docs, current manifests, and the k3s PostgreSQL troubleshooting runbook before production work.

## Safe session

Use the repository's documented connection helper or existing authenticated environment. Confirm environment, database, role, and route before querying. Never infer production from a familiar hostname or historical note.

Start read-only and make accidental writes fail:

```sql
BEGIN READ ONLY;
SHOW transaction_read_only;
SELECT current_database(), current_user, version();
-- bounded diagnostic queries
ROLLBACK;
```

- Add limits and narrow predicates to application-data queries.
- Use `EXPLAIN` first. Do not run `EXPLAIN ANALYZE` on costly or mutating statements without explicit approval.
- Prefer PostgreSQL statistics/catalog views for locks, sessions, slots, WAL, and query health. Avoid copying sensitive row contents into logs or chat.
- Treat exact historical WAL sizes, slot names, and node placement as context only; inspect current manifests and live state.

## Investigation order

1. Classify the symptom: connectivity, pool exhaustion, lock/contention, query plan, storage/WAL, replication, or application data.
2. Separate application, PgBouncer, PostgreSQL service, CNPG instance, and storage boundaries.
3. Correlate bounded SQL evidence with Kubernetes events/logs when the database runs in-cluster.
4. For WAL exhaustion, inventory physical and logical slots, active consumers, retained WAL, and configured bounded retention before proposing slot removal.
5. For recovery incidents, restore storage/nodes first, then CNPG, replication slots, Sequin, and finally MinIO/Airbyte dependencies.

## Handoffs

- Use `$infra-kubernetes` for CNPG pods, scheduling, services, PVCs, Longhorn/CSI, or node health.
- Return to the owning repo's debugging skill for ORM, schema, application-query, or test-fixture issues.
- Use the projected Incident Controller remediation skill when alert evidence, remediation, and post-fix verification are part of one incident.

## Mutation guardrail

DDL, DML, terminating sessions, changing settings, dropping slots, failover, restore, or pool changes require explicit authorization. Before acting, show the target, evidence, blast radius, backup/rollback or recovery path, and verification query. Prefer a transaction or reversible bounded operation when possible.
