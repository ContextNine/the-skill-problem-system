---
name: code-i-gh-open-source-pr
description: Prepare and publish a contribution to an external open source GitHub repository from a local checkout. Use when the user asks to contribute a patch upstream, create a fork PR, publish an open source fix, or automate branch/commit/push/PR flow with GitHub CLI.
---

# Code · GH Open Source PR

Use this skill for open source contribution work, including one-off patches in repos outside Impression.

## Workflow

1. Inspect the repo state with `git status --short` and identify the intended files only.
2. Check remotes with `git remote -v` and determine whether the user has write access or should use a fork.
3. Choose a focused branch name, commit subject, PR title, and PR body.
4. Run the relevant build/test command for the touched repo when it is cheap and obvious.
5. Stage only the intended files. Never stage unrelated dirty files.
6. Commit the change.
7. Push to a fork remote by default, then open a PR against upstream.

## Usual Commands

Read `_system/agents/_package/instance/skills/config/code-i-gh-open-source-pr/README.md`. Resolve optional helper repository through topology config, then use configured command when available:

```bash
<configured-helper-command> \
  --repo owner/name \
  --branch fix-example \
  --title "Fix example" \
  --body-file /tmp/pr-body.md
```

For repos where the helper is not suitable, use GitHub CLI directly:

```bash
gh repo fork owner/name --remote --remote-name fork
git switch -c fix-example
git add <intended-files>
git commit -m "Fix example"
git push -u fork fix-example
gh pr create --repo owner/name --base main --head "$(gh api user -q .login):fix-example" --title "Fix example" --body-file /tmp/pr-body.md
```

## Defaults

- Use fork + PR for repositories where the user is not clearly a maintainer.
- Use a direct branch only when the user has write access or explicitly asks for it.
- Prefer branch names like `fix-section-embed-viewport-decorations`, `docs-clarify-api-timeout`, or `test-cover-token-refresh`.
- Keep PRs narrow: one bug, one behavior, or one docs improvement.
- Include a short testing section in the PR body.

## Guardrails

Do not put secrets in commit messages, PR bodies, shell history, or files.

Do not use `git reset --hard`, `git checkout --`, or other destructive cleanup commands unless the user explicitly asks.

If there are unrelated dirty files, leave them alone and stage paths explicitly.

If the upstream default branch is not obvious, ask `gh repo view owner/name --json defaultBranchRef -q .defaultBranchRef.name` instead of guessing.
