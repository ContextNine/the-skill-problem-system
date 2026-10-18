---
name: code-implement-proposed-plan-in-new-branch-and-draft-pr
description: Use when the user explicitly asks to implement a proposed plan on a new branch and publish a draft pull request. Or "Implement new branch and pr"
---

# Code · Implement proposed plan in new branch and draft PR

Deliver the agreed plan as implemented, checked, committed changes on a new branch with a published draft PR. Invoking this skill authorises implementation, commits, pushing the new branch and opening the draft. Continue through those actions without asking for routine confirmation.

## Scope and branch

Use the latest proposed plan in the conversation or the plan file the user identifies, including subsequent corrections. Read the repository instructions and relevant source before implementing. Ask only when the intended plan or repository cannot be determined, or a material ambiguity blocks safe progress.

Inspect the current branch, working tree, staged changes and worktrees. Preserve unrelated work. If changing branches would carry unrelated changes or disturb active work, use an isolated worktree based on the same fetched main branch. Never reset, clean, stash or overwrite someone else's work to prepare the branch.

Fetch the latest main with `git fetch origin --prune` and confirm `origin/main` exists. Create and check out a new branch from that exact ref with `git switch -c <type>/<short-kebab-case-description> origin/main`, or create the equivalent new branch in the isolated worktree. Choose the conventional type and description for the proposed change, following repository naming instructions. Do not base the branch on a stale local main or the previously checked-out feature branch. If fetching fails or main is absent, report the blocker instead of silently choosing another base.

## Implementation and validation

Implement the complete agreed scope, following repository conventions. Keep the change small and update documentation when the resulting behaviour conflicts with it. Use the repository's appropriate checks and focused integration or end-to-end coverage where warranted. Resolve failures introduced by the change before publishing; report any unrelated failures or checks that could not run.

Review the complete diff against `origin/main` for scope, correctness and accidental files. Stage only this task's changes, preserving unrelated staged work, and create a Conventional Commit that describes the result. Verify the commit contains the intended files. Push the branch and set its upstream with `git push -u origin <branch>`. Never force-push or merge into main as part of this workflow.

## Draft pull request

After the commit is pushed, invoke $code-i-file-pr for the PR title, description, existing-PR check and publication. This workflow explicitly requires a **draft**, overriding that skill's default preference for a ready-for-review PR. Target `main` and use `gh pr create --draft` when creating it through the CLI. If the branch already has a PR, verify its base, contents and draft status, then update it as needed instead of creating a duplicate.

Describe the original problem, final behaviour and relevant validation. Follow the filing skill's guidance and any repository PR template. Keep the PR in draft; do not mark it ready, merge it or start monitoring unless separately requested. Attach the PR to the current task when the app provides that capability.

Return the branch, commit and draft PR link, along with the checks run and any material limitations. If a stage fails, preserve completed work and state exactly what remains, without claiming the PR or push succeeded.
