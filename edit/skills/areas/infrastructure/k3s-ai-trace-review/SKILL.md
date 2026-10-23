---
name: k3s-ai-trace-review
description: Use when the user asks to export or inspect a Langfuse trace, review a bounded filtered trace set, or investigate trace evidence without changing code or deployment state.
---

# Review AI traces

Resolve bundled file paths relative to this document; run its command examples from this directory and resolve project inputs against the target project.

This skill is evidence-only. It never edits code, prompts, infrastructure, or deployments.

Use an existing triage directory when supplied. Otherwise use $fleet-i-code-folder-and-computer-topology to resolve the existing checkout and run the configured repository adapter directly. Do not clone or create a worktree:

```bash
python3 "./scripts/run.py" --repository <workspace-id> --environment <local|prod> --since 24h
```

Optional selectors are trace ID, workflow, action, agent, release, status, and limit. Treat production as read-only. Read the generated summary, manifest, and relevant trace Markdown. Report failed or cancelled traces, the failing observation, model/provider, prompt revision, retries, latency, tokens, cost, tool behavior, and instrumentation gaps. Missing values are unknown, not zero.

The launcher writes a short-lived value-free request and invokes the repository's matching managed Notenv profile. Its thin adapter runs Fleet's shared collector using Fleet-managed `tsx` and `zod`. No package-manager wrapper or persistent plaintext environment projection is involved. Output stays in `.logs/ai-traces/<export-id>/` in the target repository.

Never reproduce credentials, cookies, authorization headers, signed URLs, or binary/data URLs.
