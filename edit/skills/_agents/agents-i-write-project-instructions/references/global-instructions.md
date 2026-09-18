## Global agent configuration

Edit `edit/agent-instructions/AGENT-INSTRUCTIONS.md` for shared instructions and the flat `templates/` folder for machine and development variants. Read `edit/agent-instructions/README.md` for the editing map. Inline values, conditions, loops, and includes in that Markdown determine composition. The public starter base lives under `internal/defaults/`.

`fleet sync --dry-run` previews the generated `~/.agents/instructions/AGENTS.md`. `fleet sync` applies it. Managed Codex and Claude links point to this one file. The machine registry supplies identity, exact Code root, and optional Vault guidance. A Vault-free machine has no Vault section. `fleet source path` identifies the editable repository; `fleet config path` identifies installed settings.

The public Vault and skill-system packages are independent. The public skill-system export uses the safe starter base, generic templates, and starter settings. Skills installed before a Vault retain their original editable source when the Vault is connected.
