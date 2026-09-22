---
name: vault-i-custom-calendar
description: Manages Matt Derman's Google Calendar with direct GWS CLI commands and Vault-owned calendar routing. Use when the user asks to inspect a calendar, create or update events, add travel or appointments, time block work, set up the Time Blocks calendar, or fix GWS Calendar authentication.
---

# Vault · Custom Calendar

Use the `gws` CLI directly. The legacy `vault gcal` wrapper and automatic TaskNotes calendar mirror no longer exist.

## Instance config

Before a Calendar write, read `_system/agents/edit/settings/skills/config/vault-i-custom-calendar/README.md` and its `private/config.json` from `vault root`. Require schema version 1, non-empty calendar IDs, timezone, and positive durations. Use the configured IDs directly. Do not query `calendarList` during normal operation.

If config is missing or invalid, stop with setup guidance. If Google rejects a configured ID, list calendars once. When exactly one owned calendar matches the configured summary, use its ID and repair the private config. Otherwise stop rather than guessing or creating a duplicate.

## Authentication

Use `$fleet-i-onboard-machine` and read its Google Workspace CLI Authentication reference before any authentication, reauthorization, or token repair. Start with `gws auth status`, preserve the complete everyday grant, and prove Calendar access with a harmless agenda read after auth work.

## Defaults

- Use the configured timezone unless the event needs explicit source or destination offsets.
- Put appointments, travel, meetings, reservations, and other concrete events on `calendars.concrete_events.id`.
- Put explicit time blocking and broad planning blocks on `calendars.time_blocks.id`.
- If the user omits an end or duration, use the matching configured duration.
- TaskNotes `scheduled` and `due` fields are not mirrored. Do not create an event merely because a task has a date.
- Inspect the relevant window before writing when a duplicate is plausible, then verify the returned event.

## Common commands

Read the next seven days:

```bash
gws calendar +agenda --days 7 --timezone "<time_zone>" --format json
```

Create a concrete event:

```bash
gws calendar +insert --calendar "<calendars.concrete_events.id>" --summary "Event title" --start "2026-09-07T11:45:00+02:00" --end "2026-09-07T13:50:00+02:00" --location "Cape Town International" --description "Details"
```

Create a time block:

```bash
gws calendar +insert --calendar "<calendars.time_blocks.id>" --summary "Focused work" --start "2026-09-08T09:00:00+02:00" --end "2026-09-08T13:00:00+02:00"
```

## Legacy command mapping

| Removed wrapper | Direct replacement |
| --- | --- |
| `vault gcal list` | `gws calendar +agenda` |
| `vault gcal create-event` | Use configured `calendars.concrete_events.id` with `gws calendar +insert` |
| `vault gcal create-block` | Use configured `calendars.time_blocks.id` with `gws calendar +insert` |
| `vault gcal calendars ensure` | Removed; configured IDs replace name discovery |
| `vault gcal sync-tasks` | Removed with no replacement |

The imported `$gws-calendar`, `$gws-calendar-insert`, and `$gws-calendar-agenda` skills are manual-only raw references. Use them only when the user explicitly invokes one or needs an API operation not covered here.
