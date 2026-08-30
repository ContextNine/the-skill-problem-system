---
name: ctx9-install-skill-problem-system
description: Create a user-owned Skill Problem System repository, run its setup wizard, install ctx9-agents, and make every public skill discoverable. Use when someone asks to install or set up the CTX9 skill system.
license: MIT
---

# CTX9 · Install The Skill Problem System

Create a clean, user-owned skill repository from the public release.

## Workflow

1. Ask for an empty destination folder and resolve it to an absolute path.
2. Reject the destination if it is non-empty, already managed by Git, or contains user files.
3. Clone `https://github.com/MDerman/the-skill-problem-system.git` into the destination.
4. Record the installed release tag and commit, then use the bundled guard to detach only the verified public clone and initialize a fresh repository on `master`:

```bash
python3 /path/to/skill/scripts/prepare_repository.py '/absolute/destination'
```

5. Run `./install.sh` from a real TTY. Let the setup wizard collect the machine name, code root, optional Vault root, and agent integrations.
6. Run `ctx9-agents config validate` and `ctx9-agents verify`.
7. Confirm every public skill in `_system/agents/skills/` is installed into the user's global discovery directory.
8. Tell the user the final path and that the fresh repository has no remote. Offer to add a remote only after they provide one.

Never overwrite an existing destination or reuse its Git history.
