# The Skill Problem System

The Skill Problem System is a Git-backed home for organizing, configuring, installing, and syncing agent skills across machines, part of the free and open-source developer system at [ctx9.com](https://ctx9.com).

## Install with your agent

```bash
gh skill install ContextNine/the-skill-problem-system skills/ctx9-install-skill-problem-system --scope user
```

Then tell your agent:

> Use $ctx9-install-skill-problem-system to create my skill repository. Ask me where it should live, run the setup wizard with me, install the public skills globally, and verify everything.

## Problems this solves

- Skills stop disappearing into agent-specific folders and machine-local setups.
- Shared instructions stay separate from credentials and personal configuration.
- Adding, reviewing, and syncing a large skill library becomes predictable.

## How I solved it

- I use one naming and folder standard for automatic, manual, and imported skills.
- I keep editable settings, skills, and instruction templates under `edit/`, with implementation under `internal/`.
- I project validated skills into each agent's discovery folder with `fleet sync`.
- I publish new skill areas and collections automatically while keeping user-selected exclusions private and marking partially hidden folders with `-REDACTED`.

The wizard installs the editable source in the folder you choose. `fleet source path` shows that folder later. The installed runtime and generated instructions live under `~/.agents/`; `fleet config path` shows its installed settings. A Context Vault is optional. If you install one later, its installer can connect it to this existing source without moving your skills.

## Browse and rate skills

```bash
fleet skills list --area code --sort rating --descending
fleet skills list --min-rating 4 --json
fleet skills rate code-better-ui 4
fleet skills list --collection emilkowalski-skills
```

Ratings are whole numbers from 0 to 5; unrated is separate from 0. Scores live in your editable source, survive upstream updates, and do not change invocation policy. Use `--clear` to remove a score. Read [Skill ratings](edit/settings/skills/README-skill-ratings.md) for filters, sorting, and worker behavior.

Grouping follows `edit/skills/areas/<area>/` or `collections/<collection>/`. GitHub repositories and enrolled local repositories form separate collections with no area. Default listings show areas first and locally maintained skills before GitHub imports; use `--group-by none --sort rating --descending` for a library-wide ranking.
