# Fleet Markdown templates

Use the same syntax in a skill's `SKILL.md`, its `references/*.md`, and `edit/agent-instructions/AGENT-INSTRUCTIONS.md`. Put reusable paragraphs in a flat `templates/` directory directly under the owning skill or instruction bundle. The source Markdown determines where the text appears. No render manifest is needed.

```md
---
name: example-skill
description: Example.
---

# Example

Working on \{{ fleet.machine.display_name }}.
\{% include "templates/platform-runtime.md" %}
```

`\{{ fleet.machine.display_name }}` inserts one machine fact. `\{% include "templates/platform-runtime.md" %}` inserts a Markdown file at that position. `\{% if fleet.machine.vault.enabled %}` / `\{% else %}` / `\{% endif %}` conditionally include text. `\{% for peer in fleet.peers %}` / `\{% endfor %}` repeats a block; use `\{{ peer.display_name }}` inside it. Conditions can compare a field with a quoted string, for example `\{% if fleet.machine.platform == "linux" %}`. Undefined values and missing includes fail rendering. Missing optional condition fields are false.

The include name is always the unsuffixed file. The machine's ordered `template_variants` list in `edit/settings/fleet/machines.json` determines which file is read: the last matching suffix wins, then the unsuffixed file is the fallback. For `["macos", "workermac", "workermaclowmemory"]`, an include of `templates/platform-runtime.md` chooses `platform-runtime.workermaclowmemory.md` if present, then `platform-runtime.workermac.md`, then `platform-runtime.macos.md`, then `platform-runtime.md`. Keep all of these files directly in `templates/`. A low-memory worker uses an explicit `workermaclowmemory` variant in its machine record.

Global instruction renders also expose `fleet.agent` as `codex` or `claude`. Use `\{% if fleet.agent == "claude" %}` around an include to add text only to generated `CLAUDE.md`. Skills render independently and do not receive `fleet.agent`.

The renderer exposes `fleet.machine`, `fleet.primary`, `fleet.peers`, `fleet.vault_source`, and `fleet.runtime.novnc_url`. Machine objects carry registry facts such as `id`, `display_name`, `platform`, `role`, `roots.code`, `roots.vault`, `vault.enabled`, `vault.checkout_mode`, `ssh_alias`, `vnc`, the optional `computer_use_project`, and selected `access.provider` / `access.host`. Put changing facts in the machine registry, and instruction wording in Markdown. Do not put policy prose or default wording into Python.

To show delimiters literally in authored Markdown, prefix their opening brace with a backslash: `\{{ fleet.machine.id }}` or `\{% include "templates/example.md" %}`. Plain Markdown and ordinary third-party braces are left alone. Includes cannot leave their owner's `templates/` directory; include cycles and malformed blocks fail before installation. The renderer processes authored Markdown in a staged copy and preserves the original source files.

## Non-secret skill settings

Prefer sync-time projection over telling agents to read private configuration on every invocation. Resolve the editable package with `fleet source path`. Each skill may own `./edit/settings/skills/config/<skill-name>/private/projection.json` under that root:

```json
{
  "schema_version": 1,
  "values": {
    "time_zone": "Europe/London",
    "calendar_id": "example-calendar"
  }
}
```

These values are explicitly approved for agent-visible Markdown on every selected sync target. They may contain personal non-secret IDs, paths, defaults, and preferences, but never credentials, passwords, private keys, tokens, or live service data. Keep this file as the single source for these values. Never scrape environment variables, credential files, or arbitrary config files to populate templates.

In the skill source:

```md
\{% if fleet.skill.config %}
Use calendar `\{{ fleet.skill.config.calendar_id }}` in `\{{ fleet.skill.config.time_zone }}`.
\{% else %}
Calendar setup is required. Follow this skill's config README and resync.
\{% endif %}
```

Fleet supplies `fleet.skill.name` and `fleet.skill.config` separately for each skill. Missing projection files yield an empty config for setup branches. Malformed files, symlinked projection paths, or missing referenced fields fail rendering before installation. Values are inserted literally, not recursively evaluated as templates. Validate service-specific types and values before saving config; generic projection validates its JSON envelope, not each integration's schema.

Normal sync renders from editable source settings. Public installation renders from the recipient's installed settings. Public exports retain authored template expressions and exclude every `private/` folder; never export rendered snapshots. A configured installed skill should contain actual values, not variable names or instructions to reread private config. Keep maintenance/setup guidance in the config README or the unconfigured branch. Live queries and credential custody remain runtime concerns.

Check the result with `fleet sync --skills --instructions --dry-run`, then apply with `fleet sync --skills --instructions`. Use `--local-only` when intentionally checking just the current machine. A new task may be needed to reload the refreshed skill catalog.
