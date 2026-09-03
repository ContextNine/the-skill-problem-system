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

Use `$agents-i-write-a-skill` for skill creation or restructuring.

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

Use `ctx9-agents update --skills --skill-source gh:<repo-name>` to update one installed repository. It runs `gh skill update --all --dir` against that repository's `skills` directory. `gh skill list --dir` discovers installs from injected metadata.

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

## Materialization rules

| Change needed | Result |
|---|---|
| None | Direct link to the local checkout |
| Invocation policy only | Linked overlay with generated `agents/openai.yaml` |
| Prefix, name, H1, or `$skill` reference rewrite | Generated snapshot |
| GH install without effective changes | Publisher copy remains canonical |

Local-checkout direct links and overlays are recreated against each target machine's own `~/` path. Missing enrolled checkouts fail strict sync rather than linking across machines. Fleet-distributed Vault, GH, and prefixed skills are portable copies.

All external skills default to manual globally. A literal `$skill-name` reference in an invoked skill is explicit composition and may load that dependency even when the dependency is manual-only. Manual-only prevents unsolicited top-level selection, not named dependency use.

## Configuration and validation

`_system/agents/_package/instance/skills/skill-sources.json` is the only enrollment policy registry. It uses schema version 4 with `gh_skills` and `repos`. Unknown fields, unsafe paths, duplicate names, bad metadata, missing selected sources, and names over 64 characters fail before writes.

```bash
ctx9-agents sync --dry-run
ctx9-agents sync
```

Sync validates sources, materializes overlays and snapshots, rebuilds the symlink-only catalog, and reconciles fleet discovery. Existing tasks cache their skill catalog, so start a new task after changing skills.

Public Vault export includes canonical Vault and GH sources when licensing permits. It excludes local-checkout links and generated overlays/snapshots.
