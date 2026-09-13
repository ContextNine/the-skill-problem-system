# AGENTS.md

plans are made in .agents/plans/
todos are in .agents/todos
docs are in .docs/

Read `.agents/DEVELOPMENT.md` before setting up a machine, cloning another development checkout, changing env workflow, or running Impression on Linux. It is one repo-wide guide shared by every clone.

Related local repos: K3s infrastructure lives at `~/Code/ctx9/k3s-infrastructure`; shared env tooling lives at `~/Code/ctx9/secret-bindings`.

## Git Coordination

Before making task-related file changes:

1. Run `git fetch origin --prune`.
2. Confirm the current branch is the repository's expected working branch, then compare `HEAD` with its configured upstream.
3. If the checkout is clean and behind, fast-forward to the upstream branch.
4. Unrelated dirty or newly appearing files are expected in a shared checkout. Continue when they do not overlap the task's files, and never stage, overwrite, or revert them.
5. If the current branch is ahead, divergent, or cannot be updated safely, identify and reconcile the Git state without discarding other work before editing.

## Docs

Reference .docs/\* files when wanting to understand parts of the codebase quickly. These are for internal understanding only and are not user facing.

### Directory

- `.docs/DMs-and-outreach.md` | LinkedIn DMs, conversations, outreach storage, message architecture
- `.docs/LinkedinAPI.md` | LinkedIn API integration, share API, community management
- `.docs/PNPM-SCRIPTS.md` | pnpm scripts, dev servers, tests, Playwright, job runner
- `.docs/T3-Turbo.md`
- `.docs/Tooling.md` | local tooling, command mapping
- `.docs/Turbo.md` | Turbo config, env vars, build tasks, dotenv behavior
- `.docs/actor-lists.md` | actor lists, categories, outreach priority, list behavior
- `.docs/agents.md` | Hudson supervisor, agent roster, launch surfaces
- `.docs/ai-and-agent-workflows.md` | AI workflows, routes, chat, generation, agents
- `.docs/ai-quality-and-outcomes.md` | Langfuse-first 30-day quality triage, direct feedback scores, and independent recommendation workflow
- `.docs/ai-transcription.md` | audio transcription, modes, architecture, implementation
- `.docs/airbyte-integrations.md` | Airbyte OAuth, integration setup, database schema
- `.docs/airbyte-typesense-sequin.md` | Airbyte, Typesense, Sequin, document ingestion, sync infra
- `.docs/analytics-engagement-and-comment.md` | LinkedIn analytics, comments, reactions, engagement extraction
- `.docs/analytics-platform-posts.md` | LinkedIn platform posts, post analytics, browser fetch path
- `.docs/analytics-profile.md` | LinkedIn profile analytics, profile metrics, browser collector
- `.docs/auth.md` | auth, admin cookies, sessions, cookie domain, BullMQ emails
- `.docs/auto-dm-auto-reply-auto-plug.md` | Auto DM, Auto Reply, Auto Plug, automation queues
- `.docs/auto-hooks-and-auto-ctas.md` | hook suggestions, CTA suggestions, editor overlays
- `.docs/blogs-and-changelog.md` | blog posts, changelog, markdown content, public UI
- `.docs/brand-context-search.md` | brand context search
- `.docs/brand-options.md` | brand settings, cross-posting, repurposing, idea preferences
- `.docs/brand-workspaces-and-website-research.md` | brand workspaces, website research
- `.docs/campaigns-and-sequences.md` | LinkedIn campaigns, sequence builder, graph execution, scoring, manual review
- `.docs/chrome-extension-use-cases-and-throttling.md` | extension use cases, throttling, limits, Browsergate
- `.docs/chrome-extension.md` | public Chrome extension, runtime model, publishing, automation
- `.docs/chrome-persona-extension.md` | internal persona extension, runtime, worker tokens, task queue
- `.docs/persona-extension-build-and-load.md` | persona extension build, Mac mini sync, RoxyBrowser local upload
- `.docs/chrome-web-store-first-time-setup.md`
- `.docs/cloudflare-cache.md` | Cloudflare Cache Rules, hostname purge, public edge-cache verification
- `.docs/creator-post-prod-recovery.md` | CreatorPost recovery, backfill, indexes, maintenance
- `.docs/creator-post-search.md` | creator post retrieval, search, source of truth, prerequisites
- `.docs/drizzle.md` | Drizzle ORM, query API, CRUD, migrations
- `.docs/emails.md` | email templates, email assets, add/edit email flow
- `.docs/error-and-toast-handling.md` | errors, toasts, UI error handling
- `.docs/expo-components-and-styles.md` | Expo components, mobile styles, app icon, splash
- `.docs/expo-ios-release.md` | Expo iOS EAS release, Apple setup, public env handoff
- `.docs/exported-feature-descriptions.md` | created from script
- `.docs/extension-indistinguishability-and-browsergate.md` | extension indistinguishability, Browsergate research, evidence
- `.docs/external-data-fetcher-agent.md` | external data fetcher agent, evidence workflow, tool surface
- `.docs/file-uploads-and-polling.md` | file uploads, attachments, SSE, polling, document pipeline
- `.docs/frontend-selector-directory.md` | frontend selectors, chat selectors, Find Ideas selectors
- `.docs/analytics-and-seo.md` | public-site GA4/GTM, app PostHog, consent, attribution, SEO surfaces, and canonical evidence
- `.docs/homebrew.md`
- `.docs/idea-finder-agent.md` | Idea Finder agent, workflow, suspend/resume, handoff
- `.docs/idea-generation.md` | idea generation, persistence, lanes, document ideas
- `.docs/impression-cli.md` | Impression CLI, auth, config, local usage
- `.docs/jobs-and-bullmq.md` | background jobs, BullMQ, job runner
- `.docs/kubernetes-network-and-firewall-flow.md`
- `.docs/langfuse-and-tracing.md` | Langfuse, OpenTelemetry, traces, local span files
- `.docs/lead-magnets-freebies-and-utm-links.md` | lead magnets, freebies, UTM links, delivery, tracking
- `.docs/linkedin-api-application-final.md`
- `.docs/linkedin-scraping.md` | LinkedIn persona scraping, discovery, RoxyBrowser, recurring jobs
- `.docs/linkedin-terms-of-service-notes.md` | LinkedIn ToS, automation rules, compliance notes
- `.docs/mastra-evals-and-studio.md`
- `.docs/monitoring-k3s-stack.md` | Prometheus, Grafana, Loki, incident-controller incident flow
- `.docs/naming-and-types.md` | naming conventions, type definitions, shared schema rules
- `.docs/notifications-and-accountability.md` | notification registry, delivery attempts, keep-on-track reminders, email/push/in-app defaults
- `.docs/oauth.md` | OAuth setup, frontend callbacks, high-level flow
- `.docs/onboarding-tour-and-sidebar-cards.md` | onboarding tour, starter posts, sidebar cards
- `.docs/page-editor-experiment.md` | page editor experiment, modes, platform blocks, playground
- `.docs/persona-service.md` | LinkedIn persona service, queues, browser tasks, worker model
- `.docs/pg-bouncer.md`
- `.docs/post-generation.md` | post generation, routes, UI entry points, workflows
- `.docs/public-marketing-style-guide.md` | public marketing pages, visual style, layouts for non subdomain pages.
- `.docs/service-organization.md` | LinkedIn services, router mapping, adapter boundaries
- `.docs/sql-runtime-tool.md` | SQL runtime tool, contract, inputs, execution flow
- `.docs/sse-ai-streaming-and-events.md` | SSE, AI streaming, events, request contract
- `.docs/style-guide.md` | frontend internal app style guide, app internals, buttons, dropdowns
- `.docs/testing-e2e.md` | local e2e lanes, auth, onboarding, shared Chrome
- `.docs/testing-evals.md` | Hudson evals, fixtures, browser state, commands
- `.docs/testing-unit-and-integ.md` | unit tests, integration tests, commands, database expectations
- `.docs/tool-rendering-prompt-helper-etc.md` | tool rendering, prompt placement, assistant UI helpers

After making code changes, you may need to reference .docs/\*\*.md to update docs for functionality that changed (relatively high-level).
Update this map here if new docs are added, removed, or their contents changed completely in meaning. Not all docs need descriptions if the name of the file is enough info.

# Debugging

You can always assume that i have have pnpm run dev1ep (i.e. all apps are already on localhost). however if not you can start dev server.
when using pnpm run playwright-cli - you can assume that I already have that browser open

Use `$impression-debugging-and-testing` for repository-specific routing. Shared specialists are `$code-playwright-cli`, `$code-chrome-devtools-cli`, `$chrome:control-chrome`, `$infra-kubernetes`, `$infra-run-postgresql`, `$k3s-infrastructure-incident-controller-fix-prod-errors`, and `$k3s-infrastructure-incident-controller-fix-github-issues`.

Use `$impression-ai-quality-improve` for the fixed previous-30-day Langfuse quality triage and three-agent recommendation review. Use `$impression-ai-trace-review` for lower-level evidence-only trace inspection.

## UI

Never add unneccesary labels, when possible, dont place a component inside a card (cleaner = better), i hate "eyebrow" labels and uppercase text, and using tailwind sizes that aren't standard (e.g never use text-[11px] use text-xs or text-sm or rounded-md over rounded-[22px]). See style-guide.md for app-internals. see public-marketing-style-guide.md for how to style public pages.
