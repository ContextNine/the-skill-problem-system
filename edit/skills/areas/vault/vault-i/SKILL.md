---
name: vault-i
description: Use when the user asks to find, read, or change their Context Vault, including its notes, tasks, projects, or operating setup.
---

# Vault

Find the relevant Vault. Inside a Vault checkout, use that repository root. Otherwise use `vault root`, which resolves the installed Vault without a hard-coded path. If neither identifies one Vault, ask the user for its location. Verify the selected directory contains `AGENTS.md`, `_system/`, and `.obsidian/`.

On Linux, run `vault access status` and continue only when it succeeds with `"ok": true` before reading or editing the Vault. On macOS, no access check is needed.

Read the selected Vault's root `AGENTS.md`. Follow its routing, safety, and Git instructions for the task. It is the source of truth; this skill does not duplicate them.
