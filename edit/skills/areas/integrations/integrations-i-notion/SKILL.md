---
name: integrations-i-notion
description: >-
  Use the Notion CLI (`ntn`) to interact with the Notion API, manage workers,
  and upload files. Use when the user asks to "call the Notion API", "deploy a
  worker", "upload a file to Notion", "create a page", "query a database", or
  any task involving the `ntn` command.
---

# Integrations · Notion

Choose the route below using the tools actually available in this task.

- Use `$notion-cli` for explicit CLI/API requests, page trashing, precise block or property operations, bulk changes, cursor pagination, file-upload API flows, and Notion Workers deployment, execution, syncs, and logs. Read that skill before running `ntn`; inspect live command help and endpoint docs for exact syntax.
- When Notion MCP is connected, prefer it for interactive search, reading and editing pages, ordinary page/database/view management, and comments. Use its advertised AI search, connected-source search, cross-database queries, Notion Skills, and Custom Agent session tools when available for the connected account.
- When MCP is unavailable, use `$notion-cli` for operations supported by the public API, including ordinary page reads and edits. Do not install or connect MCP unless the user requests it. If a requested MCP capability has no public API equivalent, explain the missing capability rather than approximating it silently.

For bulk work, process and filter results locally and return only relevant content to context. Respect pagination, rate limits, and the user's requested scope. A search filter is not an access restriction.

Confirm current support through `ntn <command> --help`, `ntn api <path> --docs`, or the connected MCP tool schema. See the official [CLI reference](https://developers.notion.com/cli/reference/commands) and [MCP tool list](https://developers.notion.com/guides/mcp/mcp-supported-tools) when comparing routes.
