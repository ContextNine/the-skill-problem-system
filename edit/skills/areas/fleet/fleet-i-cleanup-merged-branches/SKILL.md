---
name: fleet-i-cleanup-merged-branches
description: Use when the user asks to clean up merged Git branches across all repositories and fleet machines, remove finished local branches, return clean checkouts to main or master, or tidy one repository.
---

# Fleet · Clean up merged branches

Use `$fleet-i-code-folder-and-computer-topology` for the registered machines, Code roots and SSH routes. Run from the registered primary for fleet-wide work. One-repository cleanup can run on its owning machine.

A cleanup request authorises applying the reviewed scope. A preview request authorises inspection only. Do not ask again merely because the helper separates preview and apply.

## Scope and safeguards

- Default fleet scope is every enabled machine's Code root, including nested repositories and linked worktrees. A named repository limits the scan to its matching clones; a named machine limits the targets. Resolve workspace identities through the registry and verify each clone's origin. Do not create missing clones. For an unregistered repository, use its existing path and confirm matching origin identities before including clones elsewhere.
- Remove only local feature branches proven merged into freshly fetched `origin/main` or `origin/master`. There is no age cutoff unless the user supplies one. If an age range is requested, narrow the saved plan using verified merge dates; do not infer merge dates from branch commit dates.
- Preserve main, master, prod, production, develop, development, staging, demo, gh-pages, release and maintenance branches. Pass additional repository-specific long-lived names with `--keep`.
- A deleted remote branch or closed PR is insufficient proof. The helper accepts Git ancestry or a merged GitHub PR with the matching branch name and base, a verified PR head containing the local tip, and a merge commit reachable from the fetched target. Missing PR head objects are fetched from that exact pull-request ref and checked against the API SHA. It checks up to 200 recent merged PRs per GitHub repository. Report branches without proof as retained; investigate older PRs explicitly if needed.
- Never discard, stash, reset, rebase or commit user work, delete remote branches, remove worktree folders, rewrite history, or change authentication. Keep dirty or locked worktrees, active Git operations and local default branches with unpushed commits. Non-checked-out merged branches may be deleted while unrelated files are dirty.
- Switch a clean primary checkout off a branch being deleted onto main/master and fast-forward only. A clean linked checkout becomes detached at the fetched default commit so the default branch remains available in the primary checkout. Preserve detached worktrees that have no feature branch.
- Keep the Vault outside Code discovery. Only its registered Git owner may operate on Vault Git, through its own workflow.

## Execute

Resolve this skill directory once; the helper is `./scripts/cleanup-branches.py`. Use the installed helper on each selected machine, or stage this reviewed helper into that machine's temporary directory. Use direct SSH with bounded connection timeouts and noninteractive Git. Do not open terminal windows or create alternate sessions after an authentication failure.

The helper uses Python's standard library, Git and optional `gh` PR verification. Fleet SSH uses the registered routes. No project dependencies or services are needed.

Store each machine's plans and results under its resolved Code root's `./.workspace-sync/branch-cleanup/` directory, with owner-only permissions and a timestamped filename. Those are local operational records, not synced configuration. Output contains branch IDs and merge evidence, never source-file bodies or credential values.

For a complete Code root:

```sh
python3 ./scripts/cleanup-branches.py --root CODE_ROOT --plan PLAN_JSON
```

For one existing repository:

```sh
python3 ./scripts/cleanup-branches.py --repo REPOSITORY_ROOT --plan PLAN_JSON
```

Inspect `eligible`, `unproven` and errors in the saved plan. Read each affected repository's AGENTS.md and README.md before applying, including any additional long-lived branch policy. Do not broaden a one-repository request to other workspaces.

If a worker lacks GitHub API access, query merged PRs from the primary's authenticated `gh` session and supply an owner/repo-keyed JSON cache with `--github-cache CACHE_JSON` when rebuilding its preview. Use `gh pr list --repo OWNER/REPO --state merged --limit 200 --json number,baseRefName,headRefName,headRefOid,mergeCommit,mergedAt`. Transfer only that non-secret evidence, never credentials. For private provider repositories where PR evidence is unavailable, ancestry remains sufficient. Fetch failure blocks cleanup for that clone.

```sh
python3 ./scripts/cleanup-branches.py --apply PLAN_JSON
```

Apply rechecks origin identity, branch tips, target tips, merge evidence and every affected worktree. It atomically verifies the target and deletes only the expected local tip. Changed state is retained for a new preview. Results are written beside the plan as `*-results.json`.

After application, inspect local heads and worktree checkouts again. Confirm deleted branches are absent, unfinished branches and dirty state remain, and switched primary checkouts are on the fetched main/master. Return counts by machine and concise retained/blocker reasons. Do not claim complete cleanup when fetch failures or dirty merged checkouts remain.

The helper's integration check is `python3 ./scripts/test-cleanup-branches.py`.
