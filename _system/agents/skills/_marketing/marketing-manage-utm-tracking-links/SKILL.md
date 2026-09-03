---
name: marketing-manage-utm-tracking-links
description: Manages configured self-hosted Shlink UTM tracking links, including creation, inspection, updates, deletion, redirect checks, and visit reporting. Use only when explicitly invoked to add, change, remove, list, test, or audit managed tracking links.
---

# Marketing · Manage UTM Tracking Links

Read `_system/agents/_package/instance/skills/config/marketing-manage-utm-tracking-links/README.md` and its private config,
then use bundled `scripts/shlink-links.sh`. It resolves repository through topology
config and loads owning repository env; never open plaintext env or Kubernetes Secret content.

## Required inputs

Get or infer only when unambiguous:

- short domain from `scripts/shlink-links.sh domains`
- stable lower-kebab slug
- destination URL
- `utm_source`, `utm_medium`, `utm_campaign`
- optional `utm_content`, `utm_term`, `utm_id`, `utm_source_platform`

Use source for referrer/platform, medium for channel type, campaign for durable
initiative name, content for creative/placement, and term for paid-search term.
Use `utm_id` for a stable campaign identifier and source platform for the sending
platform when useful. Slugs use lower-kebab-case. Component-built UTM values use
lowercase snake_case.

## Commands

Run from this skill directory:

```bash
scripts/shlink-links.sh domains
scripts/shlink-links.sh create --domain short.example.com --slug launch \
  --target https://www.example.com/ --source linkedin --medium organic_social \
  --campaign product_launch --content founder_post \
  --id launch_2026 --source-platform linkedin

scripts/shlink-links.sh get --domain short.example.com --slug launch
scripts/shlink-links.sh list --domain short.example.com --search launch
scripts/shlink-links.sh check --domain short.example.com --slug launch
scripts/shlink-links.sh visits --domain short.example.com --slug launch

scripts/shlink-links.sh update --domain short.example.com --slug launch \
  --target https://www.example.com/new --source linkedin --medium social \
  --campaign product_launch

scripts/shlink-links.sh delete --domain short.example.com --slug launch --yes
```

Use `--url` instead of `--target` plus UTM flags only when user supplies exact
tracked destination. Exact URL must contain exactly one non-empty source, medium,
and campaign in the query before any fragment. Preserve exact URL values verbatim.

## Safety

- Inspect existing mapping before mutation. Create refuses conflicting slug.
- Keep `forwardQuery=false`; callers must not override attribution parameters.
- Treat same slug on each domain as separate link.
- Update or delete a configured protected slug only when user explicitly names it;
  pass both `--yes` and `--allow-permanent` for deletion.
- Never invent campaign attribution when source or campaign is unclear.
- After mutation, run `get` and `check`. `check` must confirm HTTP 302, the exact
  stored destination, and blocked incoming query forwarding. Report the public
  short URL plus exact target.
- Delete temporary verification links before finishing.

## Failure handling

Internal API requires WireGuard and cluster DNS. If unreachable, report failure.
Do not silently switch to public API. `UTM_LINKS_CONFIG`, `SHLINK_REPOSITORY_DIR`,
and `SHLINK_API_BASE` may be set explicitly for another known topology.
