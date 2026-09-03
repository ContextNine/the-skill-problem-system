---
type: agent-reference
status: enabled
---

## Skill authoring method

### Description as discovery

The frontmatter description is primarily how an agent discovers that a skill matches the user's request.

- Open with the capability in plain language.
- Follow with `Use when the user...` and concrete request forms, verbs, objects, or inputs.
- Describe what the user is trying to accomplish, not the skill's internal architecture or implementation steps.
- Include meaningful synonyms when users naturally phrase the request in several ways.
- Be specific enough to avoid accidental invocation, concise enough to scan, in third person, and under 1024 characters.

Prefer:

```yaml
description: Onboards, rebuilds, or accepts a Mac or Linux machine as a fleet member. Use when the user asks to add a worker Mac, set up a Linux worker, rebuild a machine, or complete machine acceptance.
```

Avoid vague or implementation-led descriptions such as “provides a multi-platform orchestration framework.”

### Thin `SKILL.md`

Treat `SKILL.md` as the capability's entrypoint: prerequisites, durable safety rules, routing decisions, and the shortest complete working procedure.

- Aim for roughly 30 lines when the capability can reasonably be routed that compactly.
- When it starts documenting multiple platforms, approaches, or substantial procedures, split those into focused reference documents linked directly from `SKILL.md`.
- More than roughly 30 lines is a prompt to consider progressive disclosure, not a mechanical failure.
- Keep detail inline when splitting would add indirection without making the skill easier to understand or execute.
- Follow an explicit user request to split or retain material even when a different layout might also work.
- Never exceed the Vault's 100-line limit for `SKILL.md`; move optional or detailed material out before then.
- Keep references one level deep and give each one a single clear responsibility.

### File responsibilities

- `SKILL.md`: discovery, routing, invariants, and quick execution contract.
- `references/`: platform procedures, alternative workflows, schemas, examples, and detailed acceptance criteria.
- `scripts/`: repeatable validation, transformation, or operations with useful failure handling.
- `assets/`: reusable inputs or templates consumed by the skill.
- `_system/agents/_package/instance/skills/config/<skill-name>/`: changing personal paths, domains, IDs, machine facts, and private instance configuration.

Do not restate canonical naming, source-root, invocation-policy, or projection rules. Link to `_system/agents/_package/docs/skills.md`, which owns them.

### Authoring sequence

1. Identify the capability, user request phrases, outputs, safety boundaries, and owning source.
2. Decide whether one compact workflow is sufficient or whether platform/approach references are clearer.
3. Create or update the smallest useful `SKILL.md`, then add only the supporting files it routes to.
4. Keep time-sensitive instance facts out of the portable skill.
5. Review trigger precision, links, examples, scripts, and failure behavior.
6. Run applicable tests and the required skill sync dry-run/apply cycle.

### Interactive remote scripts

- Put nontrivial interactive logic in a reviewed source file, transfer that file without credentials, then invoke it through a separate standalone `ssh -t` command. Do not embed it as base64 or a large `python -c` payload.
- Never attach a password prompt to an SSH command whose stdin is a pipe, heredoc, or here-string. Those inputs displace the user's terminal, may echo typed text locally, and can leave it queued for the parent shell.
- Read passwords with a TTY-aware API such as Python `getpass`. Do not pipe `printf '%s\n'` into a credential API: some tools consume the newline as part of the password.
- Add bounded timeouts, verify the exact service or interface being mutated, and perform a harmless store/read/clear proof before reporting success.

Minimal shape:

```md
---
name: category-capability
description: Does the user-facing capability. Use when the user asks to perform concrete task forms.
---

# Category · Capability

Read [[focused-reference|Focused Reference]] when that branch applies.

1. Perform the minimal safe workflow.
2. Verify the result.
```
