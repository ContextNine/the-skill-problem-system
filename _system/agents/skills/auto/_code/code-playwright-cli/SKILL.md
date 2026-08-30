---
name: code-playwright-cli
description: Automates browser interactions for app and Chrome extension testing, exploration, screenshots, tracing, and debugging from the terminal.
allowed-tools: Bash(playwright-cli:*)
---

# Code · Playwright CLI

## Dependencies

- Required dependency ID: `playwright-cli`.
- Optional Linux service ID: `playwright-cli-watchdog`; it is never required for normal CLI use.
- If the CLI is missing or incompatible, read `~/.agents/package/deps/references/playwright-cli.md` (Vault source: [[playwright-cli|Playwright CLI lifecycle]]), report the missing approved dependency, and stop for confirmation. Do not improvise an installer or enable the watchdog from this skill.

## Session safety

- Treat every Playwright CLI browser session as task-scoped. Use a unique descriptive `-s=` name and close that exact session before ending the task, including after failures when cleanup remains safe.
- Never use `playwright-cli close-all` or `playwright-cli kill-all` as routine cleanup on a shared machine because another agent may own a concurrent session. Use `playwright-cli -s=<name> close`; reserve global cleanup for explicitly reviewed recovery.

## Quick start

```bash
# open a browser
playwright-cli open https://example.com

# inspect the page and interact using snapshot refs
playwright-cli snapshot
playwright-cli click e15
playwright-cli type "page.click"
playwright-cli press Enter
playwright-cli screenshot
playwright-cli close
```

## Choose the browser surface

- Use this CLI for terminal-driven, repeatable browser automation, snapshots, tracing, and isolated sessions.
- Use `$code-chrome-devtools-cli` for lower-level Chrome DevTools Protocol work.
- Use `$chrome:control-chrome` when an existing signed-in Chrome session, its open tabs, or installed extensions matter.
- For Impression-specific wrappers, authentication, extension surfaces, and local URLs, use `$impression-debugging-and-testing`.

## Core commands

```bash
playwright-cli open
playwright-cli open https://example.com/
playwright-cli goto https://playwright.dev
playwright-cli type "search query"
playwright-cli click e3
playwright-cli dblclick e7
playwright-cli fill e5 "user@example.com"
playwright-cli drag e2 e8
playwright-cli hover e4
playwright-cli select e9 "option-value"
playwright-cli upload ./document.pdf
playwright-cli check e12
playwright-cli uncheck e12
playwright-cli snapshot
playwright-cli snapshot --filename=after-click.yaml
playwright-cli eval "document.title"
playwright-cli eval "el => el.textContent" e5
playwright-cli dialog-accept
playwright-cli dialog-dismiss
playwright-cli resize 1920 1080
playwright-cli close
```

## Navigation

```bash
playwright-cli go-back
playwright-cli go-forward
playwright-cli reload
```

## Tabs

```bash
playwright-cli tab-list
playwright-cli tab-new
playwright-cli tab-new https://example.com/page
playwright-cli tab-close
playwright-cli tab-close 2
playwright-cli tab-select 0
```

## Storage

```bash
playwright-cli state-save
playwright-cli state-save auth.json
playwright-cli state-load auth.json

playwright-cli cookie-list
playwright-cli cookie-get session_id
playwright-cli cookie-set session_id abc123 --domain=example.com --httpOnly --secure
playwright-cli cookie-delete session_id
playwright-cli cookie-clear

playwright-cli localstorage-list
playwright-cli localstorage-get theme
playwright-cli localstorage-set theme dark
playwright-cli localstorage-delete theme
playwright-cli localstorage-clear
```

## DevTools and artifacts

```bash
playwright-cli console
playwright-cli console warning
playwright-cli network
playwright-cli tracing-start
playwright-cli tracing-stop
playwright-cli video-start
playwright-cli video-stop demo.webm
playwright-cli run-code "async page => await page.context().grantPermissions(['clipboard-read'])"
```

## Browser sessions

```bash
playwright-cli -s=mysession open example.com --persistent
playwright-cli -s=mysession click e6
playwright-cli -s=mysession close
playwright-cli -s=mysession delete-data

playwright-cli list
playwright-cli close-all
playwright-cli kill-all
```

## Open parameters

```bash
playwright-cli open --browser=chrome
playwright-cli open --browser=firefox
playwright-cli open --browser=webkit
playwright-cli open --browser=msedge

playwright-cli open --persistent
playwright-cli open --profile=/path/to/profile
playwright-cli open --config=my-config.json
```

## Notes

- Follow the owning repository's documented wrapper and authentication flow when it provides one.
- Use snapshots first when exploring unfamiliar UI.
- Prefer unique `-s=` session names for agent work.
- Save traces, screenshots, videos, and state only in an appropriate repo artifact or temporary directory.
