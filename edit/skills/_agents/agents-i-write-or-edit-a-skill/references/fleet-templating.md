# Fleet templating

Put `fleet-templates/` inside the bundle that owns the rendered file. A skill bundle may render `SKILL.md` or a supporting file. The global instruction bundle uses the same contract. Templates do not inherit from parent folders.

Use `fleet-templates/render.json` only when rendering is needed:

```json
{
  "schema_version": 1,
  "outputs": [
    {
      "target": "SKILL.md",
      "base": "SKILL.md",
      "format": "markdown",
      "fragments": [
        {
          "id": "platform:macos",
          "path": "fleet-templates/platform/macos.md",
          "when": {"platform": "macos"}
        }
      ]
    }
  ]
}
```

`target`, `base`, `template`, and fragment paths are relative to the owning bundle. Use exactly one of `base` or `template`. A base is copied verbatim and receives selected fragments separated by `***`. A whole-file `template` is formatted directly. Supported output formats are `markdown`, `json`, and `text`.

Selectors may use `platform`, `role`, or `machine_id`, with one string or a string list. Explicit template variables use `{name}`. Unknown variables, unknown selectors, duplicate targets or fragment IDs, missing real files, path escapes, invalid rendered JSON, and malformed rendered skill frontmatter fail before installation.

Ordinary source files are not formatted. Put placeholders only in explicit templates or fragments. Do not use executable template code or automatic JSON merging.

The global instruction renderer composes base, platform, role, machine, then `append_fragments` sorted by `order` and `id`. An appended skill fragment path is relative to `edit/` and must stay inside a Vault-authored skill group. Put private variants under `fleet-templates/private/`; public export always removes that subtree.

Run the renderer tests, then `fleet sync --dry-run` and `fleet sync`. A repeated dry run must report no changes.
