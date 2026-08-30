---
name: code-chrome-lost-window-recovery
description: Recover recently closed Chrome windows from copied Chrome session-restore files and reopen all tabs in a new Chrome window. Use when user lost a Chrome window, gives one or more remembered tabs/sites/titles/URLs, or asks to dig through Chrome session/cache/recently closed windows.
---

# Code · Chrome Lost Window Recovery

## Quick Start

1. Copy and scan Chrome session restore files only:

```bash
python3 _system/agents/skills/manual/_code/code-chrome-lost-window-recovery/scripts/recover_chrome_window.py \
  --query "calendar.google.com"
```

2. Inspect top match. Prefer `kind=window`, `tabs >= 5`, and seed tab present.

3. Open best match in new Chrome window:

```bash
python3 _system/agents/skills/manual/_code/code-chrome-lost-window-recovery/scripts/recover_chrome_window.py \
  --query "calendar.google.com" \
  --open
```

## Workflow

- Ask user for one or more remembered tabs if not provided: domain, page title fragment, or URL.
- Do not read Chrome cookies, login data, tokens, key stores, or secrets. This skill needs only `*/Sessions/Tabs_*` files.
- Script first copies session files into `~/Downloads/chrome-lost-window-recovery-*`, then parses copied files.
- Use multiple `--query` values when user remembers more than one tab.
- Use `--profile` only when user knows Chrome profile name, for example `Default` or `Profile 11`.
- Use `--open-rank N` if best match is not rank 1.

## Match Rules

- Prefer closed-window entries from Chrome's tab restore store over browsing history. History proves visits, but does not preserve window membership.
- If several matches share same tabs, choose newest timestamp or newest source file.
- If query appears in a tab's history but current URL differs, report both current URL and matched history URL.
- Before opening, avoid duplicate browser spam: open one best-matching window unless user asks for several.

## Script Output

- `rank`: candidate order.
- `score`: match confidence.
- `profile`: Chrome profile directory.
- `source`: copied `Tabs_*` file.
- `tabs`: number of tabs in candidate window.
- `timestamp`: Chrome close timestamp when available.
- `matched`: query hits.
- `urls`: exact URLs opened by `--open`.
