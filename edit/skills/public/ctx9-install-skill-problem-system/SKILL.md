---
name: ctx9-install-skill-problem-system
description: Create a user-owned Skill Problem System repository, run its setup wizard, install fleet, and make every public skill discoverable. Use when someone asks to install or set up the CTX9 skill system.
license: MIT
---

# CTX9 · Install The Skill Problem System

Create a clean, user-owned skill repository from the public release.

Read [Install](references/install.md) before changing installation behavior, [Configuration](references/configuration.md) before changing editable or installed paths, and [Distribution](references/distribution.md) before changing packaging or public release behavior.

## Workflow

1. Check `fleet source path`. If it identifies an existing source, verify that installation and reuse it. If no source is installed, ask whether its editable source should be standalone or inside an existing Context Vault.
2. For a standalone source, ask for an empty destination folder. Reject a non-empty or Git-managed destination. Clone `https://github.com/MDerman/the-skill-problem-system.git` there.
3. Record the installed release tag and commit. For standalone placement, use the bundled guard to detach only the verified public clone and initialize a fresh repository on `master`:

```bash
python3 /path/to/skill/scripts/prepare_repository.py '/absolute/destination'
```

4. For Vault-owned placement, clone the public release into a temporary folder outside the Vault. Keep the released clone only as an installation input. Run `./install.sh --vault-source '/absolute/Vault/path'` from that clone. It copies the editable source into `<vault>/_system/agents/` without nested Git metadata.
5. For standalone placement, run `./install.sh` from a real TTY. Let the setup wizard collect the machine name, code root, optional Vault root, and agent integrations.
6. Run `fleet config validate` and `fleet verify`.
7. Confirm every public skill in `edit/skills/` is installed into the user's global discovery directory.
8. Tell the user the editable source path. A new standalone repository has no remote; offer to add one only after they provide it. A Vault-owned source belongs to the Vault's existing Git repository.

Never overwrite an existing destination or reuse its Git history.
