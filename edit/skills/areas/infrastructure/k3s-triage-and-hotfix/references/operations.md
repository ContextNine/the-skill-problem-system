# Operations

Resolve bundled file paths relative to this document; run its command examples from this directory and resolve project inputs against the target project.

The scheduled job stores private rebuildable state in `${XDG_STATE_HOME:-$HOME/.local/state}/ctx9-automation/triage`. `state.sqlite3` contains cursors, fingerprints, and outcomes. `runs/` contains redacted JSON evidence and Codex JSONL output. Neither location is synced by Fleet.

Commands:

```bash
python3 ../scripts/triage.py run --collect-only
python3 ../scripts/install-systemd.py install
python3 ../scripts/install-systemd.py status
python3 ../scripts/install-systemd.py run-once
python3 ../scripts/install-systemd.py disable
python3 ../scripts/install-systemd.py uninstall
```

The service uses a non-blocking lock. The timer runs 25 minutes after the previous activation and catches up after a reboot. An empty completed interval does not invoke Codex.

Shared settings are `skills/config/k3s-maintenance/config.json` beneath `fleet config path`. Edit the corresponding source beneath `fleet source path`, then sync configuration. `agent.provider` selects `codex`, `external` or `off`. External commands are an argv array with `{prompt}`, `{cwd}`, `{evidence}`, `{schema}` and `{output}` placeholders. They receive the same evidence and must write the schema-conforming result to `{output}`. Commands run directly, without a shell, with a bounded timeout and inherited mutation lock. Disabled agents leave incidents pending and publish them to the configured issue destination for manual investigation.

`issues.provider` selects `github`, `gitlab` or `off`; `hostname` and `repository` identify the explicit destination. GitHub uses `gh api` and its native OAuth session. GitLab uses the optional declared `glab` package and its host session. Use a private repository and an identity with permission to create and update issues. Credentials remain machine-local and are never placed in this configuration. Delivery retries on every scheduled collection after its saved backoff, even when there are no new errors. `fleet maintenance deliver-issues` retries immediately without running an agent. A lost creation response is reconciled by the embedded incident marker before another create. Verification closes existing issues; recurrence reuses them. Raw telemetry and transcripts remain local.

For native Langfuse authentication failures, inspect `notenv readiness` and `notenv broker status` on the worker. Use $fleet-i-onboard-machine for native-store unlock or repair, then `notenv broker unlock`. A `process-exec-reconcile-required` failure requires `notenv reconcile .` from the existing target checkout with its accepted Git contract. Verify recovery through a bounded native read and a successful `--collect-only` run; complete source coverage closes its telemetry incident and updates the existing issue. Native stores can need another manual unlock after reboot or sleep under their owning policy. Do not weaken native protection or add a plaintext fallback for unattended jobs.

## Consolidating fragmented history

With both timers stopped and both services idle, preview one queue:

```bash
fleet maintenance regroup triage --json
fleet maintenance regroup triage --apply --expected-plan <preview-plan-sha256> --json
```

The second command must match the fresh preview. It takes a restricted SQLite
backup, merges matching fingerprints and occurrence counts, retains original rows,
outcomes and issue links, and records the surviving incident ID. Existing approvals
remain approvals. Duplicate issues close as consolidated, not as repaired. Future
observations reuse the surviving incident and issue. Cursors and source deduplication
stay unchanged. Repeating the operation is idempotent. `cluster-wizard` is also a
supported explicit job argument.

Regrouping does not publish issues by itself. Inspect the result, run collection-only
and audit-only checks, then use `fleet maintenance deliver-issues` and restore the
timers. Never replace a live queue from its backup without separately checking
newer collection and issue-delivery state.

