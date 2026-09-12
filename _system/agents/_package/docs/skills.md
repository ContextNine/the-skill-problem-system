# Skill SOP

## Source and discovery contract

- Vault-owned source: `_system/agents/skills/<_group>/<skill>/SKILL.md`
- GH-managed source: `_system/agents/skills/github/<repo-name>/skills/<skill>/SKILL.md`
- Local-checkout source: `<checkout>/.agents/skills/<repo-name>-<capability>/SKILL.md`
- Generated policy overlay: `_system/agents/skills/overlays/<source-id>/<skill>/`
- Generated prefixed snapshot: `_system/agents/skills/snapshots/<source-id>/<skill>/`
- Generated catalog link: `_system/agents/skills/catalog/<skill>`
- Dormant storage: `_system/agents/skills/dormant/`

`catalog` contains symlinks only. `overlays` and `snapshots` contain generated outputs only. Never author or install a skill in those locations.

## Skill authoring method

### Structure and progressive disclosure

Treat `SKILL.md` as the entry point for prerequisites, durable safety rules, routing decisions, and the shortest complete workflow.

- If you discover that the skill file will be long (> 300 lines), create additional docs under references/ grouped logically.
- Keep references one level deep and give each one a clear responsibility.
- Keep detail inline when splitting it would only add indirection.
- Follow the user's requested structure when they specify one.
- If you discover that a skill contains explicit variables, file paths or other user-specific information, ALWAYS ensure that this information is not 
  duplicated elsewhere. This is because information like this will inevitably change, and never ever do we want to have conflicting or duplicate information. When it makes sense, store specific "config" such as file paths under the _package folder explained below.
- Always suggest changes to existing skills when you notice they conflict with these rules.

Use each file for one job:

- `SKILL.md`: discovery, routing, invariants, and the quick execution contract.
- `references/`: additional docs
- `scripts/`: repeatable validation, transformation, or operations with useful failure handling.
- `assets/`: reusable inputs or templates consumed by the skill.
- `_system/agents/_package/instance/skills/config/<skill-name>/`: changing personal paths, domains, IDs, machine facts, and private instance configuration.

Do not restate naming, source-root, invocation-policy, projection, or dependency rules inside individual skills.


### Description as discovery

The frontmatter description is how an agent discovers that a skill matches a request.

- Open with the capability in plain language. not vague.
- Follow with `Use when the user...` and concrete request forms, verbs, objects, or inputs.
- Describe what the user wants to accomplish, not the skill's internal implementation.
- Include meaningful synonyms when users naturally phrase the request in several ways.
- Keep it specific, concise, third person.

e.g.

```yaml
description: Onboards, rebuilds, or accepts a Mac or Linux machine as a fleet member. Use when the user asks to add a worker Mac, set up a Linux worker, rebuild a machine, or complete machine acceptance.
```


### Authoring workflow

1. Identify the capability, realistic request phrases, outputs, safety boundaries, owning source, and runtime dependencies.
2. Choose a compact `SKILL.md` or split distinct procedures into focused references.
3. Create or update the smallest useful skill and only the supporting files it routes to.
4. Keep changing instance facts out of portable skills.
5. Review trigger precision, links, examples, scripts, dependency declarations, and failure behavior.
6. Test applicable scripts, validate the skill, then run the required skill sync dry-run and apply cycle.

For interactive remote scripts, stage a reviewed source file and invoke it with a separate standalone `ssh -t` command. Never connect a password prompt to a pipe, heredoc, here-string, or encoded inline script. Read passwords through a TTY-aware API such as Python `getpass`. Add bounded timeouts and perform a harmless store, read, and clear proof before reporting success.

## Vault-owned naming

Use a root `_lower-kebab` category folder. The skill folder basename must equal frontmatter `name`, use lowercase kebab-case, remain globally unique, and stay within 64 characters.

- Implicit: `<category>-i-<capability>` with `allow_implicit_invocation: true`.
- Manual: `<category>-<capability>` with `allow_implicit_invocation: false`.
- An implicit category router may use `<category>-i`, such as `vault-i`.

The `-i-` marker is only for Vault-owned sources. Repository and GH names retain their ownership conventions. Shared H1s mirror the hierarchy, for example `# Infra · Sync Code Workspaces`; `vault-i` uses `# Vault`.

| Folder | Token |
|---|---|
| `_agents` | `agents` |
| `_blogs` | `blog` |
| `_code` | `code` |
| `_creative` | `creative` |
| `_documents` | `documents` |
| `_finance` | `finance` |
| `_gws` | `gws` |
| `_infrastructure` | `infra` |
| `_marketing` | `marketing` |
| `_spreadsheets` | `spreadsheets` |
| `_vault` | `vault` |
| `_vibe-marketer-skills-pack` | `vibe-marketer` |
| `_video` | `video` |

## Three enrollment methods

### 1. Vault-authored

Create the canonical skill in its root category. Put repeatable utilities in `scripts/`, reusable inputs in `assets/`, focused detail in `references/`, and changing personal facts in `_system/agents/_package/instance/skills/config/<skill-name>/`.

Invocation changes require the folder, frontmatter name, config folder, references, `-i-` marker, and `agents/openai.yaml` policy to agree.

### 2. GH-managed

Install a public repository into its own owner directory:

```bash
SKILLS_ROOT="$(vault root)/_system/agents/skills"
gh skill install owner/repo --all --dir "$SKILLS_ROOT/github/<repo-name>/skills"
```

The GitHub CLI copies selected skills and injects `github-repo`, `github-path`, `github-ref`, and `github-tree-sha` metadata. Those installed directories are the local installation record. There is no separate install manifest.

`skill-sources.json` may add only effective policy:

```json
"gh_skills": {
  "repo-name": {
    "prefix": "publisher",
    "invocation": {"skill-name": true}
  }
}
```

Omitting a repository from `gh_skills` leaves every installed skill globally manual and unprefixed. A prefix creates snapshots. An invocation-only difference creates linked overlays. Do not edit publisher-owned files to apply either policy.

Use `fleet update --skills --skill-source gh:<repo-name>` to update one installed repository. It runs `gh skill update --all --dir` against that repository's `skills` directory. `gh skill list --dir` discovers installs from injected metadata.

### 3. Existing local checkout

Name repository-owned skills `<repo-name>-<capability>` and keep them in the owning checkout. Enroll the checkout independently of workspace registration:

```json
{
  "path": "~/Code/example-repo",
  "github": "https://github.com/owner/example-repo",
  "all_skills": true
}
```

The path must begin with literal `~/`. Use exactly one of `all_skills: true` or a source-only selection:

```json
"skills": [
  {"source": ".agents/skills/example-repo-do-a-thing"}
]
```

Optional `invocation` keys use repo-relative sources and boolean values. Optional `prefix` rewrites effective names through generated snapshots. Registration in `workspaces.json` neither enrolls nor locates skills; it only controls repository registration and reconciliation.

Refer to another capability as `$skill-name`, never by absolute skill directory. Relative paths between skills are appropriate only when both files share one canonical source tree and move together.

## Materialization rules

| Change needed | Result |
|---|---|
| None | Direct link to the local checkout |
| Invocation policy only | Linked overlay with generated `agents/openai.yaml` |
| Prefix, name, H1, or `$skill` reference rewrite | Generated snapshot |
| GH install without effective changes | Publisher copy remains canonical |

Local-checkout direct links and overlays are recreated against each target machine's own `~/` path. Missing enrolled checkouts fail strict sync rather than linking across machines. Fleet-distributed Vault, GH, and prefixed skills are portable copies.

All external skills default to manual globally. A literal `$skill-name` reference in an invoked skill is explicit composition and may load that dependency even when the dependency is manual-only. Manual-only prevents unsolicited top-level selection, not named dependency use.

## Runtime dependencies

Audit every executable, package, runtime, and library used by a skill or its scripts before delivery.

### Globally available skills

A skill is global when it is an active Vault-owned skill, a GH-managed installation, or an enrolled local-checkout skill projected through `skill-sources.json`.

Every non-standard runtime dependency for a global skill must be declared in `_system/agents/_package/defaults/dependencies.json` before projection. Add a typed entry with:

- a stable dependency ID;
- eligible platforms and package-manager recipes;
- the effective skill name in `required_by`;
- a lifecycle document;
- a deterministic verification command.

Command-line dependencies belong in `dependencies.json`, not `agents/openai.yaml`. The latter only declares supported MCP tool dependencies. `fleet sync --dependencies` installs missing required packages and verifies them on enabled agent machines. Read [[_system/agents/_package/docs/dependencies|Agent and fleet dependencies]] for the registry schema and lifecycle rules.

### Local-only skills

A first-party repository skill that is not globally enrolled may assume its dependencies are installed. If one is missing, install it automatically through the repository's documented package manager or the registered platform package manager, then verify it. Do not add it to the global dependency registry unless the skill becomes globally available. A third-party skill does not authorize installing missing dependencies unless its installation workflow is explicitly requested.

## Configuration and validation

`_system/agents/_package/instance/skills/skill-sources.json` is the only enrollment policy registry. It uses schema version 4 with `gh_skills` and `repos`. Unknown fields, unsafe paths, duplicate names, bad metadata, missing selected sources, and names over 64 characters fail before writes.

```bash
fleet sync --dry-run
fleet sync
```

Sync validates sources, materializes overlays and snapshots, rebuilds the symlink-only catalog, and reconciles fleet discovery. Existing tasks cache their skill catalog, so start a new task after changing skills.

Public Vault export includes canonical Vault and GH sources when licensing permits. It excludes local-checkout links and generated overlays/snapshots.
