---
name: k3s-cluster-wizard
description: Use when the user asks to audit, maintain, repair, or patch-upgrade the K3s cluster, or to run the daily midnight cluster health workflow.
---

# Maintain the K3s cluster

Resolve bundled file paths relative to this document; run its command examples from this directory and resolve project inputs against the target project.

Run the deterministic audit first:

```bash
python3 "./scripts/audit.py" run
```

The audit checks readiness, certificate expiry, backup freshness, PVC/node/Longhorn capacity and seven-day growth, and release candidates for K3s, PostgreSQL, CNPG and Langfuse. Missing telemetry is recorded as incomplete coverage, never healthy capacity. Each new finding or configured collector failure can dispatch on its first occurrence. Release candidates receive compatibility review under the upgrade policy below. Each execution receives at most ten incident groups from the existing infrastructure checkout. Shared configuration selects Codex, an external coding command or disabled execution. The healthy path with no pending investigations exits without an agent. `--audit-only` retains findings without invoking an agent.

PVC history must use stable namespace/claim identity rather than pod, node or scrape
labels. Byte capacity still includes EFI filesystems; inode checks exclude FAT
filesystems because they do not expose Unix inodes. A `ReadonlyFilesystem=True`
node condition is an investigation finding, not proof that the filesystem is still
read-only. Release discovery paginates with a bounded budget and prefers patch,
then same-major candidates. Exhausting that budget remains incomplete coverage.

Keep evidence, execution logs and outcomes in machine-local XDG state, defaulting to `~/.local/state/ctx9-automation/cluster-wizard/`. The deterministic runner publishes sanitized unresolved, blocked and approval-required outcomes to the configured GitHub or GitLab repository. Agents return outcomes and do not create chats or issues themselves. Use `fleet maintenance status` for current problems, issue links and collector freshness, `fleet maintenance show <id>` for local detail, `fleet maintenance deliver-issues` to retry delivery, and `fleet maintenance retry <id>` after resolving a prerequisite or approving its action. Shared settings live at `skills/config/k3s-maintenance/config.json` beneath `fleet config path`. Keep 30 days of detailed runs, at most 1,000 per job and 10 GiB across both jobs; keep 180 days of closed summaries, at most 50,000 per job. Preserve active summaries and failed issue deliveries until resolved.

When the audit invokes this skill with a finding bundle:

1. Compose `$fleet-i-code-folder-and-computer-topology`, `$k3s-infrastructure-kubernetes` and the closest component README before diagnosis. The agent runs in the existing registered infrastructure checkout. Never clone or create worktrees.
2. Capture initial branch, SHA, staged paths and working changes. Use current `master` and preserve unrelated edits. Stop on overlapping work or unsafe upstream integration, not on unrelated dirty files. Never stash, reset or clean.
3. Capture exact affected resources, current state, and rollback steps before mutation.
4. Prefer a targeted, reversible repair. Never start with a broad redeploy or restart.
5. Keep infrastructure changes in `k3s-infrastructure`; run its focused checks, commit, push, apply only the owning operation, and verify cluster health.
6. Patch-version upgrades and reversible repairs are autonomous only with fresh backups, compatibility checks, capacity, focused verification and a credible recovery procedure. Review upstream release notes. Langfuse minor upgrades need a reviewed migration path. Kubernetes minor upgrades, PostgreSQL/CNPG major upgrades, storage migrations, destructive cleanup, and reduced redundancy require explicit approval. Expand volumes only when the storage class and capacity policy permit it. Never shrink or delete data to resolve pressure.
7. Return one structured outcome per incident ID, including investigated repository SHAs, commits, applied operations and health verification. Detailed evidence remains in the private local queue; bounded outcome summaries are published by the runner. Never include protected values or raw user data.

The audit reads fresh WAL size, replication-slot retention/activity and archival
age from the discovered current primary, never standby slot inactivity. It checks
independent restore receipts and queues missing, invalid or stale proof. Read
`./references/database-health.md` for policy and receipt ownership. Do not infer a
safe database upgrade from Ready pods or a recent backup alone. A maintenance
agent must not manufacture a passing restore receipt. Use the owning isolated
restore procedure and establish its independent verification before changing a
database version.

The runner shares a mutation lock with triage. The child agent inherits it so an interrupted parent cannot permit overlapping repairs.

Unchanged blocked or unresolved findings do not retry on a cooldown. State the actual prerequisite in `next_action`. A complete live check that no longer finds a failure closes it; incomplete coverage cannot close that source's problems. The schema cutover requires idle timers and `fleet maintenance migrate`; it archives old groups with a private SQLite backup, preserves all source cursors and rebuilds current problems from fresh checks. Never reset cursors to replay historical logs.
