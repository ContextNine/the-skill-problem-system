# Skill SOP

## Source And Catalog Contract

- Implicit source: `_system/agents/skills/auto/<_group>/<skill>/SKILL.md`
- Explicit-only source: `_system/agents/skills/manual/<_group>/<skill>/SKILL.md`
- GitHub-managed source: `_system/agents/skills/github/<skill>/SKILL.md`
- Selected repo projection: `_system/agents/skills/projected/<repo-id>/<projected-name>/SKILL.md`
- Generated catalog: `_system/agents/skills/catalog/<skill>`
- Dormant storage: `_system/agents/skills/dormant/<skill>/`
- Repo-local skills: `.agents/skills/`

`skills/catalog/` contains symlinks only. Put new or moved skills under auto, manual, or GitHub source, then sync. Never install content into the generated catalog. Skill sync implementation lives in `_package/src/sync_skills.py`.

Use `$agents-write-a-skill` when creating or restructuring a skill; it owns the authoring method and routes back here for canonical naming, source, invocation, and projection rules.

Every new Vault-owned skill must use `skills/auto` for implicit invocation or `skills/manual` for explicit-only invocation, followed by the matching `_lower-kebab` category group. Never create a Vault-owned skill in the Vault root's `.agents/skills`. Repo-local `.agents/skills` is only for a separate owning code repository when the user explicitly requests repository-local ownership there.

Organizer folders must use `_lower-kebab`, may nest recursively, and never contain `SKILL.md`. Skill folder must contain `SKILL.md`; folder basename must equal frontmatter `name`. Names must be globally unique.

## Big-Endian Naming

- Auto/manual skill: `<category>-<capability>`.
- Large third-party packs may use an approved root pack group and distinctive pack token, such as `_claude-seo/claude-seo-<capability>` or `_corey-marketing-skills/corey-<capability>`.
- Repository-local skill: `l-<capability>`.
- Never encode auto/manual invocation in the name.
- Use lowercase kebab-case and preserve the established descriptive capability slug. Do not shorten, reword, or reorder it merely to make names more compact. Keep the complete name under 64 characters.
- Keep `SKILL.md` as the filename. For shared skills, make the first H1 mirror the hierarchy, such as `# Infra · Update Fleet Coding Tools`. For repository-local skills, use the exact lowercase slug, such as `# l-hotfix-build-push`.
- Omit `interface.display_name` from `agents/openai.yaml`; Codex derives the user-facing label from the canonical frontmatter `name`, avoiding a second name to maintain.
- Prefix the existing descriptive capability slug with literal lowercase `l-`; do not add repository or category tokens.

| Folder | Token |
|---|---|
| `_agents` | `agents` |
| `_blogs` | `blog` |
| `_claude-seo` | `claude-seo` |
| `_code` | `code` |
| `_corey-marketing-skills` | `corey` |
| `_creative` | `creative` |
| `_documents` | `documents` |
| `_finance` | `finance` |
| `_gws` | `gws` |
| `_infrastructure` | `infra` |
| `_marketing` | `marketing` |
| `_matt-p-skills` | `mp` |
| `_spreadsheets` | `spreadsheets` |
| `_swan-gtm-skills` | `swan-gtm` |
| `_vibe-marketer-skills-pack` | `vibe-marketer` |
| `_vault` | `vault` |
| `_video` | `video` |

Shared skill sync validates the category prefix and big-endian H1 for auto/manual sources. GitHub-managed skills retain publisher names and titles.

Use a dedicated pack token when a large installed collection would otherwise flood autocomplete under a broad functional token. Choose a short, distinctive publisher or repository phrase; prefix every projected skill consistently; and preserve the upstream capability slug after that prefix. Register the pack group and title in `scripts/sync_skills.py` rather than weakening category validation.

A pack may expose one orchestrating root skill whose name exactly equals its pack token, such as `_claude-seo/claude-seo`. Register that exception explicitly; ordinary category skills still require `<token>-<capability>`. The canonical `_vault/vault` router is the only ordinary category root exception and uses the exact H1 `# Vault`.

## Skill And Config Separation

- Read [[_system/agents/README|Agents]], this file, and [[_system/local/README|Local Vault Data]] before adding or restructuring skill.
- Generic instructions, validation, scripts, code snippets, and reusable assets stay in skill folder.
- Changing domains, personal paths, machine facts, account/project IDs, repository locations, and deployment access details go in `_system/agents/_package/instance/skills/config/<skill-name>/`.
- Use same basename as skill. Add config-folder `README.md`; use `private/` for private instance data.
- Config format may be Markdown, JSON, TOML, YAML, or another consumer-appropriate format.
- Skill must name required config, validate it before mutation, and explain setup when missing. Public-exported skill must remain understandable without private config.
- Before adding secrets or variables, read [[_system/local/env/README|Env Tooling]]. Add names to the owning `.env.base` contract first; values move only through the repository's protected Secret Bindings workflow. External-repository variables remain in the owning repository contract.

## Invocation Policy

Sync preserves other `agents/openai.yaml` fields and enforces:

```yaml
policy:
  allow_implicit_invocation: true
```

for auto skills, and:

```yaml
policy:
  allow_implicit_invocation: false
```

for manual skills. Missing metadata gets created. GH metadata stays publisher-controlled.

GitHub-managed skills may opt into an explicit snapshot policy without changing publisher files. Add the installed skill name and `auto` or `manual` mode under `github_skills` in `_system/agents/_package/instance/skills/sources.json`. Sync writes the policy only into distributed point-in-time copies. Skills omitted from that map retain publisher policy.

## Sync

```bash
ctx9-agents sync --dry-run
ctx9-agents sync
```

Sync performs full preflight before writes. Malformed sources, duplicate names, real content under generated catalog, or unmanaged global name collisions fail with repair instructions.

The default apply:

- validates configured repository skill projections and rebuilds changed tracked copies before discovery links;
- repairs dependency target/type metadata after manually moving a managed skill wrapper;
- removes stale catalog links and rebuilds changed links;
- installs real point-in-time copies under `~/.agents/skills` on every enabled fleet machine;
- maintains per-skill discovery aliases under `~/.claude/skills`, `~/.kilo/skills`, and `~/.kilocode/skills` when Kilocode exists;
- preserves unrelated global skills;
- removes vault-owned legacy `~/.codex/skills` whole-directory link;
- never copies discovery-target content into vault.

Existing tasks cache skill catalog. Start new task or restart Codex after sync.

## Dependency Skills

External skill-source repos derive as `<resolved Code root>/open_source/<repo-name>` and are configured in `_system/agents/_package/instance/skills/sources.json`. Consumers obtain the Code root through `ctx9-agents config`, never a hard-coded home path.

Set a repo's `enabled` field to `false` to retain its configuration and currently materialized skill projections as a discoverable snapshot while excluding that repo from dependency and auto-skill projection sync. Re-enable it to resume refreshes. See [[_system/docs/commands/Dependency Repos|Dependency Repos]].

Each compact skill choice stores `source`, `group`, `name`, and optional `mode`, `kind`, `title`, or pack fields. `mode` defaults to `manual`; use `auto` for implicit invocation. Sync derives the checkout URL/path, projection target/type, managed marker, and catalog destination. The wrapper materializes upstream content for portable distribution, uses the configured local name, and optionally replaces its first H1 with `title`.

```bash
ctx9-agents update --skills --dry-run
ctx9-agents update --skills
ctx9-agents sync --dry-run
```

Routine source refresh belongs to `ctx9-agents update --skills`, which safely fast-forwards cloned sources, asks `gh skill` to update GitHub-managed sources, materializes repository-relative symlinks for portable snapshots, rebuilds projections, distributes snapshots, verifies targets, and records factual state. Use `--skill-source <repo-id>` or `--skill-source gh:<skill-name>` to restrict one operation. A detached, dirty, ahead, divergent, wrong-branch, wrong-upstream, or remote-mismatched checkout is preserved and blocks only when selected.

Public Vault bootstrap and release do not consume agent skill sources. To move a managed wrapper, edit its `group`, `name`, or `mode` choice in `instance/skills/sources.json`, then run agent sync. Generated targets and markers are outputs and never rewrite desired configuration.

## GitHub-Managed Skills

```bash
GH_SKILLS_DIR="$(vault root)/_system/agents/skills/github"
gh skill install owner/repo packages/agent-skills/code-review --dir "$GH_SKILLS_DIR"
ctx9-agents update --skills --skill-source gh:<skill-name>
```

Direct `gh skill install` remains the enrollment operation. Once enrolled, use the central agent update command so projection, fleet distribution, verification, and factual locking remain one transaction. GH publisher files remain untouched. Name conflict fails preflight.

To make an enrolled skill explicit-only while preserving GitHub update ownership:

```json
"github_skills": {
  "resume-builder": "manual"
}
```

Run skill sync after changing the mode. The generated snapshot receives `policy.allow_implicit_invocation: false`; the tracked GitHub-managed source remains byte-for-byte publisher-owned.

## Repo-Local Skills

Repository-owned skills always begin in `.agents/skills/l-<capability>`. They stay local by default; registering a repository never projects all its skills. Repo `.claude/skills` may link to `../.agents/skills`.

Selected user-owned repo skills are listed explicitly under that repo ID in `_system/agents/_package/instance/skills/sources.json`. Each entry contains a repo-relative `source` and `auto` or `manual` mode. Sync derives `<repo-id>-<capability>`, rejects global collisions and names over 64 characters, rewrites the copied frontmatter/H1 and `$l-sibling` references, copies supporting resources, enforces invocation policy, and records a managed digest marker under `_system/agents/skills/projected/<repo-id>/`. Invocation mode is metadata, not a projection subfolder.

If a whole configured checkout or selected source is unavailable, ordinary sync preserves a valid tracked copy and warns. `ctx9-agents sync --dry-run --require-repo-sources` fails unless every configured checkout and selected source exists; use it for machine acceptance after Code workspace reconciliation. Missing or invalid tracked projections still fail. Only obsolete marked projections are removed; unmanaged content is never replaced. Linux targets receive the portable snapshot over SSH independently of optional Vault access and never resolve discovery through a remote mount.

Reference skills portably as `$skill-name`. Relative cross-skill paths are allowed only between Vault-owned sources. Use `vault root` only when a real Vault filesystem path is necessary. Manual dependencies require explicit user invocation; capabilities that must compose automatically belong in auto skills.
