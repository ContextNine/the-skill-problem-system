# Database health evidence

The `database_policy` object in this skill's configuration owns WAL thresholds,
metric freshness, the minimum expected number of replication slots and restore
proof freshness. Resolve configuration beneath `fleet config path`. Metrics use
the configured Prometheus endpoint and the current primary from each live CNPG
Cluster. The collector does not run SQL, change slots, force archival or restore
data.

The WAL checks read `cnpg_collector_pg_wal{value="size"}`,
`cnpg_pg_replication_slots_pg_wal_lsn_diff`,
`cnpg_pg_replication_slots_active` and
`cnpg_pg_stat_archiver_seconds_since_last_archival`. Only current-primary series
within `metric_max_age_seconds` qualify. Missing, non-finite, negative, duplicate
or mismatched series leave coverage incomplete. Replica slots normally appear
inactive, so standby observations must not trigger slot-retention findings.
Threshold breaches queue a `PostgresWAL` investigation. Passing metrics only prove
this bounded WAL check, not database upgrade safety.

## Restore receipts

The owning restore verifier writes a receipt after restoring an actual selected
backup into an authorized isolated target, verifying the recovered behavior/data,
and proving cleanup. Maintenance consumes receipts; it does not produce successful
restore claims. A backup creation timestamp, successful backup job or Ready pod is
not restore evidence.

Receipts live outside the Vault and agent run outputs at
`ctx9-automation/restore-evidence/<source-cluster-uid>.json` beneath the machine's
XDG state directory. Use private directories and atomic mode-0600 writes. The UID
must match the live CNPG resource, so evidence from a replaced cluster cannot pass.
The receipt has this shape, using only non-secret metadata:

```json
{
  "schema_version": 1,
  "source_cluster_uid": "uid-from-live-cnpg-resource",
  "backup_id": "actual-backup-identifier",
  "target": "isolated-target-identifier",
  "verifier": "independent-verifier-and-result-reference",
  "completed_at": "2026-01-01T00:00:00Z",
  "status": "passed",
  "cleanup_verified": true
}
```

This example is a format, not accepted evidence. Never copy it into operational
state. Receipts require an explicit timezone, a non-future timestamp within
`restore_max_age_hours`, a matching source UID, passed verification and completed
cleanup. Missing or invalid evidence stays incomplete and queues `RestoreTest`
with the actual prerequisite. Resolving an evidence gap means running its owning
procedure, not editing the receipt to change its status. These local receipts are
operator evidence, not cryptographic attestations or protection against a
compromised machine account.

The audit never provisions a restore target automatically. Keep test identities,
data, deployment authority and cleanup separate from production. Consult the
owning database runbook before a restore or upgrade; both have their own approval
and recovery boundaries.
