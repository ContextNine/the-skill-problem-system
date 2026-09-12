# The Skill Problem System

The Skill Problem System is a Git-backed home for organizing, configuring, installing, and syncing agent skills across machines, part of the free and open-source developer system at [ctx9.com](https://ctx9.com).

## Install with your agent

```bash
gh skill install MDerman/the-skill-problem-system skills/ctx9-install-skill-problem-system --scope user
```

Then tell your agent:

> Use $ctx9-install-skill-problem-system to create my skill repository. Ask me where it should live, run the setup wizard with me, install the public skills globally, and verify everything.

## Problems this solves

- Skills stop disappearing into agent-specific folders and machine-local setups.
- Shared instructions stay separate from credentials and personal configuration.
- Adding, reviewing, and syncing a large skill library becomes predictable.

## How I solved it

- I use one naming and folder standard for automatic, manual, and imported skills.
- I keep public defaults and schemas in Git while private instance data stays outside the public export.
- I project validated skills into each agent's discovery folder with `fleet sync`.
- I publish every active non-repository skill while keeping repository-owned projections private.
