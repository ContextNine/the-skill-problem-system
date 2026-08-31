---
name: infra-manipulate-threads
description: Manipulate Codex and T3 Code chats or threads across machines and repositories, including moving, copying, pinning, unpinning, archiving, changing or preserving IDs, bridging history, and making remote chats visible in the Codex sidebar. Use for any request involving chats or threads between computers, worker Macs, Codex, T3 Code, remote projects, sidebar visibility, handoff, fork, import, thread IDs, or thread URLs.
---

# Infra · Manipulate Threads

## Glossary And Routing Contract

- **Move a thread**: port the selected thread state over the approved SSH route with the bundled exact-state workflow. Preserve the thread identity by default, do not invoke native Codex handoff, and do not create a Git worktree. Remove the source only after destination verification.
- **Copy a thread**: use the same direct state-port workflow but retain the source. When both copies must remain visible, use a destination-native identity or ask before creating duplicate visible UUIDs.
- **Handoff**: use Codex's native handoff feature. Handoff creates or reuses a Git worktree on the destination host and transfers the chat plus Git state.
- **Codex-visible**: the destination thread renders under the intended host/project in the requesting Codex desktop app and opens with the expected history.
- **T3-visible**: the destination task renders in the intended T3 project, opens with the expected visible history, and retains a working Codex resume cursor.

Treat these words as explicit method selection. If the user's wording, source harness, destination harness, identity, or visibility target conflicts or remains unclear, summarize the possible operation and ask before mutation.

## Main Workflows

- Move or copy a Codex thread between machines through a selected export/import bundle over the approved SSH route, without creating a worktree.
- Handoff a Codex thread between matching saved projects with native Codex handoff and its worktree semantics.
- Pin, unpin, archive, restore, rename, or verify a Codex thread on the intended host.
- Move Codex history into T3 Code on this or another machine.
- Return continued T3-backed work to Codex or another machine.
- Export/import exact-ID threads, archives, workspace sets, or recovery state when native tooling is insufficient.
- Re-key selected Codex projects and thread assignments when a stable SSH alias replaces a transport-specific alias for the same physical machine.

## Confirm Intent Before Mutation

Resolve these fields before changing state:

1. Source app, machine, thread, and repository/workspace.
2. Destination app, machine, and saved project/workspace.
3. Move or copy: should the source remain?
4. Identity: preserve the UUID or create a new native UUID?
5. Destination state: pinned, unpinned, archived, or active?
6. Visibility: must it appear in the current Codex sidebar, the destination app, T3 Code, or more than one place?
7. Method: direct SSH move/copy or native Codex handoff with a worktree?

If the request leaves any field ambiguous or contradictory, inspect what can be discovered, summarize the resolved operation in one short sentence, and ask for confirmation before mutation. Do not ask again when the user already specified a complete, consistent operation. Never infer permission to delete a source from the word “copy.”

Defaults when the verb is explicit: a move removes the source only after verification; a copy retains it. If the verb is absent, retain the source. Use a new destination-native ID when both copies must coexist, leave the destination unpinned, and require destination-app visibility.

If the request originates in Codex and targets Codex, acceptance requires Codex-visible verification in the requesting desktop app. If it originates in T3 or targets T3, acceptance requires T3-visible verification. Do not assume either app refreshes imported state correctly; restart or refresh the exact state writers that were stopped and verify the rendered task.

## Choose the Workflow

- Read [[references/codex-between-machines|Codex Between Machines]] for direct moves/copies, native handoff, pin state, and sidebar acceptance.
- Read [[references/t3-code-bridge|T3 Code Bridge]] for Codex ↔ T3 Code workflows.
- Read [[references/exact-state-and-recovery|Exact State And Recovery]] for bundle imports, bulk sets, archives, exact IDs, selectors, and rollback.

Use the bundled exact-state scripts for “move” and “copy.” Use native task tools for “handoff,” titles, pins, archives, and project placement that does not relocate thread state. Never substitute native handoff for a move merely because matching saved projects exist.

When old and new SSH aliases reach the same physical Codex home, do not copy the transcript. Use the alias re-key workflow in [[references/codex-between-machines|Codex Between Machines]] to clone saved-project metadata and re-associate only the selected desktop thread assignments. A local-to-remote copy still needs a destination-native remote thread and exact-state history transplant.

## Completion Report

After every mutation, explicitly tell the user which method was used, source and destination hosts/apps/workspaces, source and destination IDs, whether the source remains, whether a worktree was created or reused, and how destination visibility was verified. Include the backup and temporary-bundle disposition for direct state ports. If verification is incomplete, say exactly what remains unverified.

## Safety Contract

- Treat Codex and T3 state formats as internal and version-sensitive.
- Never copy authentication, credentials, config, logs, or an entire state directory.
- Back up destination databases and transcripts before direct state mutation; preview before apply.
- Stop processes that write destination state, then restore the same services afterward.
- Do not pin a destination unless explicitly requested.
- Do not claim sidebar success from a SQLite row alone. Verify host, workspace, history, pin/archive state, and actual app visibility; if direct UI inspection is unavailable, ask the user for a screenshot.
- Same UUIDs on two visible hosts can collide in Codex’s cross-host index. Prefer a destination-native new-ID copy when both must coexist.
- Never synthesize an ID casually or rewrite transcript metadata without a destination-native task, a backup, and post-restart verification.
- Transfer temporary bundles only over the approved machine route and remove them after verification.
