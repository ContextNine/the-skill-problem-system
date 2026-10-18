---
name: k3s-ai-triage
description: Use when the user manually asks to audit Langfuse AI failures, output quality, latency, cost, tools, or instrumentation for a configured repository. Do not schedule it.
---

# Triage AI quality

Resolve bundled file paths relative to this document; run its command examples from this directory and resolve project inputs against the target project.

This skill is manual-only. Use $fleet-i-code-folder-and-computer-topology to resolve the existing target checkout. Never clone or create a worktree. Run the shared adapter launcher directly:

```bash
python3 "./scripts/run.py" --repository <workspace-id> --environment <local|prod>
```

The default interval is the previous 7 days. Use `--since 30d` for the comparison window or another bounded duration supported by the adapter. The launcher writes a short-lived value-free request and invokes the repository's managed Notenv profile. The profile's thin adapter invokes Fleet's shared TypeScript collector, not a `pnpm` package script. Fleet declares its `tsx` and `zod` dependencies. Evidence stays in `.agents/evaluations/<evaluation-id>/` relative to the target repository. Reuse a supplied evidence directory instead of fetching it again.

Read `manifest.json`, `evidence.json`, `triage.md`, and selected trace dossiers. Separate population metrics from bounded examples, observed facts from inference, and unknown values from zero. One agent may perform the review. Before code changes, independently verify the proposed root cause and proof method.

Write `recommendations/` and `final.md` using [the evidence contract](references/evaluation-file-contract.md). Review and recommendation are the default. An explicit request to improve the application authorizes focused implementation and verification in this invocation. It does not by itself authorize deployment or recurring work. Preserve unrelated checkout changes. Keep unresolved recommendations in that evaluation directory and report actionable decisions in the current conversation. Never export maintenance handoffs to the Vault.
