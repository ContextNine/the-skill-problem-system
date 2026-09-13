---
name: code-chrome-agent
description: Drives Chrome through full Chrome DevTools Protocol access with chrome-agent. Use only when the user explicitly requests this skill or chrome-agent for raw CDP browser automation, including CAPTCHA-involved flows.
allowed-tools: Bash(chrome-agent:*)
---

# Code · Chrome Agent

## Dependency

The `chrome-agent` command and Google Chrome or Chromium are required. If either is missing, report it and stop; do not install dependencies without confirmation.

## Workflow

1. Read the installed guide before use:

```bash
chrome-agent guide --path
```

2. Launch a task-scoped browser, retain its instance name, and use `chrome-agent help <instance> [Domain[.method]]` for the live protocol reference.
3. Drive or observe the browser with one-shot CDP commands and `attach` event streams.
4. Stop only the instance created for the task. Do not use global cleanup when another agent may own a browser.

```bash
chrome-agent launch
chrome-agent status
chrome-agent <instance> Runtime.evaluate '{"expression":"document.title","returnByValue":true}'
chrome-agent stop <instance>
```

Treat the installed guide as authoritative for command syntax, sensing and acting, event streams, targeting tabs, and CDP safety details.
