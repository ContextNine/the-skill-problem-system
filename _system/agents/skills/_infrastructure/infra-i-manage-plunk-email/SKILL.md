---
name: infra-i-manage-plunk-email
description: Manages Plunk email, automation workflows, sequences, campaigns, and broadcasts for self-hosted marketing and transactional delivery. Use when the user asks an agent to inspect or change Plunk contacts, segments, templates, domains, lead-magnet automations, newsletter sequences, campaigns, broadcasts, or deployment health.
---

# Infra · Manage Plunk Email

Use this capability to operate an existing Plunk instance and its project-scoped email configuration. It does not replace application-owned consent, one-time confirmation tokens, or offer-specific post-confirmation redirects.

1. Use `$infra-i-code-folder-and-computer-topology` to locate the `k3s-infrastructure` repository, then read `plunk/README.md` there.
2. Resolve the exact Plunk project, segment, template, workflow, campaign, or contact before mutation. Keep new workflows disabled and campaigns as drafts unless the user explicitly approves enabling or sending them.
3. Prefer the configured `plunk` MCP server for supported contact, segment, template, workflow, domain, campaign, event, and analytics actions. It runs the pinned community package through Secret Bindings, so never copy API keys into MCP configuration or command arguments.
4. Use the REST fallback for actions missing from MCP. From the infrastructure repository:

```bash
PLUNK_REST_METHOD=GET PLUNK_REST_PATH=/segments secret-bindings run plunk-rest
PLUNK_REST_METHOD=POST PLUNK_REST_PATH=/workflows PLUNK_REST_BODY='{"name":"Draft","enabled":false}' secret-bindings run plunk-rest
```

`PLUNK_REST_PATH` must be relative to the configured Plunk API. DELETE additionally requires `PLUNK_REST_ALLOW_DESTRUCTIVE=1`; obtain explicit approval first. Inspect the installed Plunk version or upstream REST route schema before inventing payloads.

5. Use `secret-bindings run plunk-status` for read-only service checks. Use `plunk-bootstrap-content` only when the user wants the repository-defined draft segment, templates, and workflows reconciled.
6. Use `$infra-i-kubernetes` for K3s workload diagnosis and `$infra-i-run-postgresql` for database diagnosis. Do not query or export contact bodies when aggregate evidence is sufficient.

For lead magnets, the application remains the consent authority: it creates the pending signup and one-time token, sends a Plunk transactional confirmation containing the application callback, confirms locally, returns the offer-specific 302, then tracks the confirmed event that starts a Plunk sequence.
