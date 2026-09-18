# Agent instructions

Edit `AGENT-INSTRUCTIONS.md` for instructions shared by every machine. Edit one of the files directly under `templates/` for a machine type or local development. `machine.md` controls the short machine description. The `machine-worker-mac-vault.md` addition applies only to a worker Mac enrolled in the Vault.

The renderer combines the shared file, one machine type, the machine description, an optional worker-Mac Vault addition, local development, then any configured skill fragments. Its configuration and the public starter text live under `internal/instructions/`; they are not normal editing files. The machine registry supplies identity, Code root, connection facts, and optional Vault guidance. A machine without Vault participation gets no Vault section.

`fleet sync --dry-run` previews generated destinations. Review it, then run `fleet sync`. The resulting global file is `~/.agents/instructions/AGENTS.md`; Codex and, when enabled, Claude link to it. The Vault root `AGENTS.md` is a separate project instruction file.

The standalone skill-system repository can be placed anywhere you choose. Installing it with a Vault can instead keep its editable source under that Vault's `_system/agents/`. In either case, `fleet source path` reports the editable source and `fleet config path` reports the installed settings copy.
