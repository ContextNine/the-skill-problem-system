# Skill SOP

## Source and discovery contract

The following package paths are relative to `fleet source path`. Local-checkout paths are relative to that checkout.

- Locally maintained area source: `./edit/skills/areas/<area>/<skill>/SKILL.md`
- Locally maintained collection source: `./edit/skills/collections/<collection>/<skill>/SKILL.md`
- GH-managed source: `./edit/skills/github/<repo-name>/skills/<skill>/SKILL.md`
- Local-checkout source: `<checkout>/.agents/skills/<repo-name>-<capability>/SKILL.md`
- Generated policy overlay: `./internal/generated/overlays/<source-id>/<skill>/`
- Generated prefixed snapshot: `./internal/generated/snapshots/<source-id>/<skill>/`
- Generated catalog link: `./internal/generated/catalog/<skill>`
- Dormant storage: `./edit/skills/dormant/`

`catalog` contains symlinks only. `overlays` and `snapshots` contain generated outputs only. Never author or install a skill in those locations.

## Skill authoring method

### Paths and skill references

Always use relative file paths. Resolve bundled references from the referring document: `./README.md` for a sibling, `./references/topic.md` from SKILL.md, or `../scripts/tool.py` from a reference. For project files and external configuration, name the base explicitly and resolve it at runtime with the owning tool, such as `vault root`, `fleet source path`, or `fleet config path`. Never hard-code a checkout or installed skill directory. Check that paths still resolve after skill installation, where folder depth can differ. Runtime system locations required by an operating system or external tool belong in configuration; do not turn them into misleading document-relative paths.

Mention other skills only by `$skill-name`, never by a file path or link to their location.

### Structure and progressive disclosure

Treat `SKILL.md` as the entry point for prerequisites, durable safety rules, routing decisions, and the shortest complete workflow.

Keep public defaults and schemas under `internal/defaults/` and `internal/schemas/`. Never store credential values in the repository. Preserve provenance and license notices when importing a skill.

- If you discover that the skill file will be long (> 500 lines), create additional docs under references/ grouped logically.
- Skills should often be composable, with logical groupings of responsibility under references or into separate skills. You can do this automatically when you notice this can be done, but if it's a big change to an existing skill, notify me.
- Rewrite both the "what" (capability) and the "when" (trigger context) in the description.
- Provide constraints not procedures ("e g. Always run tests before x", not "step 1, step 2"). Step by step should be in scripts.
- Keep references one level deep and give each one a clear responsibility.
- Keep detail inline when splitting it would only add indirection.
- Follow the user's requested structure when they specify one.
- If you discover that a skill contains explicit variables, file paths or other user-specific information, ALWAYS ensure that this information is not 
  duplicated elsewhere. This is because information like this will inevitably change, and never ever do we want to have conflicting or duplicate information. When it makes sense, store user-editable configuration such as file paths under `edit/settings/` as explained below.
- Always suggest changes to existing skills when you notice they conflict with these rules.

Design first-party skills to be shareable by default. A primary Mac with optional additional Mac or Linux machines is a safe assumption for fleet skills. A particular username, machine ID or count, path, domain, account, repository, or provider ID is not. Project stable, non-secret facts from the registry or per-skill settings into installed Markdown during sync, using `./fleet-templating.md`. Do not add routine runtime configuration lookups when a projected literal suffices. Read changing live state through its owning service; keep credentials in their custody system. Keep examples and test fixtures neutral. Deliberately private sources and explicit public-export exclusions are the exceptions.

Use each file for one job:

- `SKILL.md`: discovery, routing, invariants, and the quick execution contract.
- `references/`: additional docs
- `templates/`: flat Markdown fragments selected by inline includes and machine suffixes; see `./fleet-templating.md`.
- `scripts/`: repeatable validation, transformation, or operations with useful failure handling.
- `assets/`: reusable inputs or templates consumed by the skill.
- `./edit/settings/skills/config/<skill-name>/`: changing personal paths, domains, IDs, machine facts, and private instance configuration.

Use `./private/projection.json` within that config directory for non-secret values approved for inclusion in agent instructions. It is the authoritative value source, not a duplicate of another config file. Installed skills contain rendered values; portable source skills contain expressions and an unconfigured setup branch. After settings changes, resync skills. Do not bulk-convert unrelated skills or project credentials, access tokens, or live task/calendar data.

Do not restate naming, source-root, invocation-policy, projection, or dependency rules inside individual skills.


### Description as discovery

The frontmatter description is how an agent discovers that a skill matches a request.

- Start with `Use when the user...` and concrete request forms, verbs, objects, or inputs.
- Describe what the user wants to accomplish, not the skill's internal implementation.
- Include meaningful synonyms when users naturally phrase the request in several ways.
- Keep it specific, concise, third person.

e.g.

```yaml
description: Use when the user asks to add a worker Mac, set up a Linux worker, rebuild a machine, or complete machine acceptance.
```
another good example:
```yaml
description: 
When user asks to upload a file, or one is needed for PR descriptions, and public/private resources.
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

Use `areas/<area>/` or `collections/<collection>/` beneath `edit/skills/`. Group IDs use lowercase words separated by hyphens or underscores, without a leading underscore. Folder placement supplies grouping without registration. Collections have no area and preserve their internal layout; adding or moving a group does not rename skills or add prefixes. The skill folder basename must equal frontmatter `name`, use lowercase kebab-case, remain globally unique, and stay within 64 characters.

- An implicit skill contains the `-i-` marker, or ends in `-i`, and sets `allow_implicit_invocation: true`.
- A manual skill omits that marker and sets `allow_implicit_invocation: false`.

The `-i-` marker is only for Vault-owned sources. Repository and GH names retain their ownership conventions. A skill needs a non-empty H1, but its name and H1 do not need to mirror its area or collection.

New areas and locally maintained collections are included in the public Skill Problem System export by default. Add its path to `edit/settings/public-skill-repo-export-exclusions.json` only when it must stay private or appear as a redacted placeholder.

## Three enrollment methods

### 1. Vault-authored

Create the canonical skill in its area or collection. Put repeatable utilities in `scripts/`, reusable inputs in `assets/`, focused detail in `references/`, and changing personal facts in `./edit/settings/skills/config/<skill-name>/`.

Invocation changes require the folder, frontmatter name, config folder, references, `-i-` marker, and `agents/openai.yaml` policy to agree.

### 2. GH-managed

Install a public repository into its own owner directory:

```bash
SKILLS_ROOT="$(fleet source path)/edit/skills"
gh skill install owner/repo --all --dir "$SKILLS_ROOT/github/<repo-name>/skills"
```

The GitHub CLI copies selected skills and injects `github-repo`, `github-path`, `github-ref`, and `github-tree-sha` metadata. Each repository directory is a collection. Set an optional `area` in its `gh_skills` policy to group the pack by purpose while preserving its collection and upstream ownership. Those installed directories are the local installation record. There is no separate install manifest.

`skill-sources.json` may add only effective policy:

```json
"gh_skills": {
  "repo-name": {
    "area": "creative",
    "prefix": "publisher",
    "invocation": {"skill-name": true}
  }
}
```

Omitting a repository from `gh_skills` leaves every installed skill globally manual and unprefixed. A prefix creates snapshots. An invocation-only difference creates linked overlays. Do not edit publisher-owned files to apply either policy.

Use `fleet update --skills --skill-source gh:<repo-name>` to update one installed repository. It runs `gh skill update --all --dir` against that repository's `skills` directory. `gh skill list --dir` discovers installs from injected metadata.

### 3. Existing local checkout

Name repository-owned skills `<repo-name>-<capability>` and keep them in the owning checkout. Enrolled repositories form collections with no area, using their existing source IDs. Enroll the checkout independently of workspace registration:

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

Always reference another skill only by `$skill-name`. Do not link to its directory, SKILL.md, scripts, or references, even when the skills share a source tree; load the named skill and follow its own routing.

## Materialization rules

| Change needed | Result |
|---|---|
| None | Direct link to the local checkout |
| Invocation policy only | Linked overlay with generated `agents/openai.yaml` |
| Prefix, name, H1, or `$skill` reference rewrite | Generated snapshot |
| GH install without effective changes | Publisher copy remains canonical |

Local-checkout direct links and overlays are recreated against each target machine's own `~/` path. Missing target skills are deferred without blocking other skills or failing verification; any existing installation and ownership remain unchanged until the source becomes available. Do not fast-forward a checkout just to finish skill sync. Strict source-catalog validation still requires the primary's enrolled checkouts. Fleet-distributed Vault, GH, and prefixed skills are portable copies.

A skill with Fleet expressions is rendered into a target-specific snapshot even if it would otherwise be a direct link or invocation overlay. The authored `SKILL.md` and supporting Markdown remain the editable source; the snapshot is generated output. Use `./fleet-templating.md` for the one shared syntax and variant precedence contract.

All external skills default to manual globally. A literal `$skill-name` reference in an invoked skill is explicit composition and may load that dependency even when the dependency is manual-only. Manual-only prevents unsolicited top-level selection, not named dependency use.

## Runtime dependencies

Audit every executable, package, runtime, and library used by a skill or its scripts before delivery.

### Globally available skills

A skill is global when it is an active Vault-owned skill, a GH-managed installation, or an enrolled local-checkout skill projected through `skill-sources.json`.

Every non-standard runtime dependency for a global skill must be declared in `./internal/defaults/dependencies.json` before projection. Add a typed entry with:

- a stable dependency ID;
- eligible platforms and package-manager recipes;
- the effective skill name in `required_by`;
- a lifecycle document;
- a deterministic verification command.

Command-line dependencies belong in `dependencies.json`, not `agents/openai.yaml`. The latter only declares supported MCP tool dependencies. `fleet sync --dependencies` installs missing required packages and verifies them on enabled agent machines. Read `$fleet-i-update-dependencies` for the registry schema and lifecycle rules.

### Local-only skills

A first-party repository skill that is not globally enrolled may assume its dependencies are installed. If one is missing, install it automatically through the repository's documented package manager or the registered platform package manager, then verify it. Do not add it to the global dependency registry unless the skill becomes globally available. A third-party skill does not authorize installing missing dependencies unless its installation workflow is explicitly requested.

## Configuration and validation

Use `fleet skills list --area <area>` or `--collection <collection>` to browse folder-derived groups, and `fleet skills rate <name> <0-5>` to record a whole-number rating. Locally maintained collections have no area. GitHub collections may also have an area through `gh_skills.<source-id>.area`; use a lowercase group ID with hyphens or underscores. Default browsing puts area-assigned skills first, collections without an area second, with locally maintained sources and highest ratings first within each group. Use `--group-by none --sort rating --descending` for a ranking across groups. Metadata lives in `./edit/settings/skills/skill-metadata.json` below `fleet source path`, independently of upstream skill files. The source-owner SOP is `./edit/settings/skills/README-skill-ratings.md` below that same resolved source root. Workers without an editable source can use `fleet skills list --help`. Keep the metadata key aligned when renaming an effective skill. Listing never syncs or writes generated materializations.

`./edit/settings/skills/skill-sources.json` is the only enrollment policy registry. It uses schema version 4 with `gh_skills` and `repos`. Unknown fields, unsafe paths, duplicate names, bad metadata, missing selected sources, and names over 64 characters fail before writes.

```bash
fleet sync --dry-run
fleet sync
```

Sync validates sources, materializes overlays and snapshots, rebuilds the symlink-only catalog, and reconciles fleet discovery. Existing tasks cache their skill catalog, so start a new task after changing skills.

The Skill Problem System export includes canonical Vault and licensed GH sources. It excludes local-checkout links and generated overlays/snapshots. `exclude` keeps selected paths private. `partial_hiding` replaces an exact skill or folder with an otherwise empty `<name>-REDACTED` folder containing only Git's `.gitkeep`. The separate public Vault includes only its repo-local `vault-i` skill.
