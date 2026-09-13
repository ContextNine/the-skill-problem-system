## Global agent configuration

The editable global base is `_system/agents/edit/root-agents/AGENTS.md`. Its `fleet-templates/` directory owns platform, role, machine, preview, and public variants. `fleet-templates/render.json` selects the output and any approved skill fragments.

Rendering is deterministic: base, platform, role, machine, then approved fragments. The machine section resolves `~` against the selected registry home and writes the exact absolute Code root and Vault root or disabled state. When another enabled machine is registered, it also adds development-preview instructions using the primary's configured SSH alias, loopback addresses, and runtime port placeholders. A single-machine registry omits that section. Operating system does not imply Vault availability.

`fleet sync --dry-run` previews the source workflow; `fleet config` exposes the installed settings without a Vault. The renderer writes `~/.agents/instructions/AGENTS.md`. Codex and Claude use managed links to that one file. Installation refuses unmanaged collisions, keeps recoverable prior managed versions, and makes an identical second run a no-op.

Skill-source choices live separately at `edit/settings/skills/skill-sources.json`. They enroll skills from literal `~/` checkout paths but do not own repository registration, reconciliation, Git transport, or instruction fragments. `workspaces.json` owns registered checkout reconciliation.

Personal settings are excluded from both public products. Public agent exports use the explicit safe base at `fleet-templates/public/AGENTS.md`, generic templates, and starter settings.
