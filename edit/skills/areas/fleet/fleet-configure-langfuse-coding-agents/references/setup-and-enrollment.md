---
type: agent-reference
status: enabled
---

## Official Langfuse coding-agent integrations

Read the current upstream instructions before installation or upgrades:

- https://langfuse.com/integrations/developer-tools/codex
- https://langfuse.com/integrations/developer-tools/claude-code

Resolve the HTTPS endpoint from `integrations/langfuse.json` and credential ownership from `fleet/machine-secrets.json` below `fleet config path`. Select the coding-agent project recorded in instance metadata. Issue a distinct project-scoped API key pair for each selected machine, so it can be revoked independently. Do not reuse an application key or copy another machine's credentials.

### Codex configuration

Requires Codex 0.143+ and Node.js 22+ on the normal shell and desktop hook PATH. Install with the official CLI:

```bash
codex plugin marketplace add langfuse/codex-observability-plugin
codex plugin add tracing@codex-observability-plugin
codex features enable hooks
```

Enable `tracing@codex-observability-plugin` in the target's Codex plugin settings. Create local `~/.codex/langfuse.json` atomically with mode 0600 and these official fields, using the actual endpoint and target-issued keys:

```json
{
  "enabled": true,
  "base_url": "https://your-langfuse-host.example",
  "public_key": "<target-project-public-key>",
  "secret_key": "<target-project-secret-key>",
  "environment": "coding-agent",
  "tags": ["coding-agent", "machine:<registered-machine-id>"],
  "user_id": "<local-user>",
  "debug": false,
  "fail_on_error": false
}
```

Keys are plaintext in this explicitly approved, user-only local file. Deliver them from the administrator/provider process to the writer through stdin; never print them, put them in shell arguments, temporary credential files, profiles, synchronized configuration or Git. Verify the pair through the public projects API before installation. Environment variables override JSON, and project-local configuration can override global fields; inspect presence without printing values when diagnosing precedence.

The official exporter reads the JSON itself. There is no custom launcher or Keychain adapter. Review its Stop command in Codex `/hooks` and trust only that exact reviewed hook. After updates, review again when Codex requires it. Fully restart the desktop app and start a new chat to load the plugin. Existing running chats may not pick up installation changes.

The exporter captures full prompts, responses, tool input/output, available reasoning summaries and images. Metadata defaults do not limit its capture. It can export previously unuploaded turns when an old session is resumed; it has no fleet creation-date cutoff. Use fresh harmless sessions for acceptance, and do not resume historical confidential conversations for testing.

### Temporarily pause or enable tracing across the fleet

Resolve the selected machines from the fleet registry using `$fleet-i-code-folder-and-computer-topology`. Apply the change directly on every machine with Codex tracing configured, using local execution or SSH. These are machine-local edits, not configuration sync.

| Request | Change in each machine's `~/.codex/langfuse.json` |
| --- | --- |
| Pause tracing | Set only `enabled` to `false` |
| Enable tracing | Set only `enabled` to `true` |

Use a target-local read/modify/write in memory, an atomic replacement and mode 0600. Preserve all other fields, including that target's keys; do not create credential backups or print the JSON. Keep the plugin, hook trust and API keys intact for a temporary pause. Confirm the boolean and protected permissions without exposing credentials, and report success or failure per machine. An unreachable machine remains unchanged and must not be reported paused or enabled.

The official Stop exporter rereads JSON for each invocation, so the toggle affects subsequent hooks; an upload already running may finish. Project-local `langfuse.json` and `TRACE_TO_LANGFUSE` can override the global boolean. Check applicable overrides without printing credential values, and reconcile them within the requested tracing scope before claiming the effective state. Restart Codex if changing process environment or plugin settings.

After enabling, use a fresh harmless two-turn chat to confirm ingestion. Pausing stops uploads but does not remove the local Codex transcript. Resuming a chat used while paused can export its unuploaded turns later; start a fresh chat after enabling and keep chats intended to stay untraced out of subsequent traced sessions.

### Acceptance and viewing a conversation

Use an empty temporary working directory. Run one harmless text-only turn followed by a second harmless turn that performs a fixed `printf` command. Record the fresh session UUID and final cumulative provider input, cached-input and output totals. Do not use `resume --last`.

Run `../scripts/verify_codex_session.py` on that target with `--session-id`, `--key-id`, `--expected-input`, `--expected-cached-input` and `--expected-output`. It consumes the official JSON in memory, verifies project identity, two server-side traces, machine/user labels, a tool observation, exact provider totals and every generation's matched price. It prints sanitized evidence only. Optional `--state-output` merges that evidence into the owning generated machine-secret lock; do not hand-edit successful acceptance. Desktop acceptance requires a separate fresh desktop chat after restart.

Sign into the configured Langfuse website with a user account. Project API keys are for the exporter and are not website login credentials. Select the coding-agent project, then Sessions and the exact session UUID. Each turn has its own trace; Sessions groups the entire conversation. Open a trace to inspect prompts, responses, tool spans, usage and cost. Machine tags distinguish fleet targets.

Verify model prices against the provider's current official pricing. Langfuse computes API-equivalent estimates from provider usage and model prices. ChatGPT subscription-authenticated Codex does not have a corresponding per-call API invoice. Costs on a separate ingestion server are outside the Codex trace.

### Rotation and complete removal

Issue a replacement target-specific key, replace the protected local JSON, verify a harmless fresh session, then revoke the previous key. Removing a local file alone does not revoke server credentials.

When changing away from an integration, retire its owned code and state after replacement acceptance. For the retired native Codex helper, remove `~/.local/bin/codex-langfuse` and its installer-created copies, its global Stop hook, `~/.agents/state/codex-langfuse.json`, and `~/.cache/codex-langfuse/`. Delete only the macOS generic-password item with service `ctx9-langfuse-codex` and account `<local-user>`, or Linux Secret Service item with `ctx9-provider=langfuse` and `ctx9-purpose=codex`. Confirm absence, preserve unrelated credentials and hooks, revoke replaced keys, update the registry and sync the skill. Temporary native cleanup jobs must exit and be removed; do not retain a credential adapter.

### Claude and authenticated API access

Configure Claude only when selected by the user. The official Claude plugin's `/plugin configure langfuse-observability@langfuse-observability` supports native OS custody. Keep it disabled until its own target credential and harmless acceptance pass; do not use plaintext inline Claude settings.

Authenticated Langfuse MCP and CLI access are distinct from observability. Do not place Basic-auth headers in synchronized settings or treat the public docs MCP as private project access. Configure these separately when requested.
