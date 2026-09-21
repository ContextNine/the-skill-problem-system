# Agent instructions

Edit `AGENT-INSTRUCTIONS.md` for instructions shared by every machine and for the order of the generated sections. Its `\{{ fleet.machine.display_name }}` value comes from `../settings/fleet/machines.json`; its `\{% include "templates/name.md" %}` directives insert Markdown at the point written.

Edit files directly under `templates/` for specific text:

- `machine_type.primarymac.md`, `machine_type.workermac.md`, `machine_type.workermaclowmemory.md`, or `machine_type.workerlinux.md`: machine-type guidance. The low-memory version is selected only when `workermaclowmemory` appears last in that machine's ordered `template_variants`.
- `local_development.md`: the shared no-local-Docker and development K3s policy for PostgreSQL, Redis, and other backing services.
- `vault.md`: optional Vault checkout and access rules.
- `connections.md`: registered access, peers, and GUI connection guidance.
- `development-previews.md`: worker preview forwarding.

The machine registry owns identity, the default Code root, access routes, Vault participation, and variant choice. The workspace registry owns each repository's optional non-secret `development` target and service names. Never put credentials or connection URLs there. Markdown owns all instruction wording. For syntax and precedence, see the Fleet templating reference in `../skills/_agents/agents-i-write-or-edit-a-skill/references/fleet-templating.md`.

`fleet sync --skills --instructions --dry-run` previews generated destinations; `fleet sync --skills --instructions` applies them. The generated global file is `~/.agents/instructions/AGENTS.md`, with Codex and optional Claude links. The Vault root `AGENTS.md` is a separate, direct-edit project instruction file.

The public skill-system package and public Vault can be installed independently. Run `fleet source path` to find the authoritative editable agent package and `fleet config path` to find its installed settings. A later Vault install does not silently move or replace an existing standalone skill-system source.
