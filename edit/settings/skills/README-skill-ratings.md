Skill grouping comes from folders and optional GitHub pack areas. Ratings live in `skill-metadata.json` beside this note, independently of skill files.

```bash
fleet skills list
fleet skills list --area uiux
fleet skills list --collection anthropics-skills
fleet skills list --area uiux --sort rating --descending
fleet skills list --group-by none --sort rating --descending
fleet skills list --group-by source
fleet skills list --unrated
fleet skills list --min-rating 4 --json
fleet skills rate code-better-ui 4
fleet skills rate code-better-ui --clear
```

Locally maintained sources live beneath `edit/skills/areas/<area>/` or `edit/skills/collections/<collection>/`, relative to `fleet source path`. Adding a valid skill folder requires no registration. Locally maintained collections preserve their internal structure and have no area. Names and prefixes are independent of group folders. GitHub installs retain `edit/skills/github/<source-id>/skills/`; each source ID is a collection. A GitHub pack can also have an optional `area` in its `gh_skills` policy in `skill-sources.json`, such as `"motion-graphics-skills": {"area": "creative"}`. Both area and collection filters then find the pack. Enrolled local repositories also form collections using their existing source IDs.

The default listing groups skills with an area first, including area-assigned GitHub packs, then collections without an area, alphabetically within each kind. Within each group, the `preferred` sort places Vault-maintained sources first, repository sources second, and GitHub-managed imports third, then sorts by highest rating and name. Source describes maintenance location, not authorship; invocation mode is separate.

Use `--group-by group|source|none`. Explicit sorting supports `--sort name|rating|source`; `--descending` reverses that sort within each group. `preferred` has a fixed direction and rejects `--descending`. Rating sorts always put unrated skills last. `--group-by none --sort rating --descending` ranks the entire library together. JSON contains the same ordered rows without terminal headings, with nullable `area` and `collection`; at least one is populated. GitHub packs with an assigned area populate both.

Scores are whole numbers from 0 to 5. Unrated means no score and differs from 0. Numeric filters exclude unrated skills. Repeat `--area` or `--collection` to select a union of groups, then narrow it with an exact rating or a minimum/maximum range. `--unrated` cannot be combined with numeric filters.

`fleet skills rate` and `--clear` update the editable source immediately. Installation creates no rating entry. Moving or updating a skill preserves its rating through the unchanged effective name. Keep its metadata key aligned if intentionally renaming it. `fleet config validate` reports stale entries without deleting them.

Listing is offline and read-only. Source owners see live folders and ratings; workers browse their verified installed catalog. Change ratings on the registered primary source owner. Run `fleet sync --skills --dry-run`, then `fleet sync --skills`, to distribute changes. Missing repository skills retain their previously installed catalog record; new missing skills receive no record.

Ratings do not change invocation policy or export eligibility. Public export retains ratings only for included skills. Excluded, redacted, dormant, and repository-only records are omitted. Standalone runtime upgrades preserve source-owned ratings.
