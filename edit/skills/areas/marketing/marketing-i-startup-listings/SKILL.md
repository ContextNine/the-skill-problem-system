---
name: marketing-i-startup-listings
description: Use when the user asks to get startup backlinks, sign up for product directories, list a startup, submit a product, improve personal or consultancy profiles, or resume a saved backlink campaign through computer use. Tracks each campaign separately and verifies published links.
---

# Startup listings

Use computer use to create or claim suitable product, person or service-business listings and save progress after each meaningful action. A request to create this skill or research opportunities alone does not authorize external submissions.

## Working state

{% if fleet.skill.config %}
Resolve the Vault with `vault root` and follow its AGENTS.md. The canonical campaign root is `./{{ fleet.skill.config.state_path }}` relative to that Vault. Read the owning config README at `../../README.md` relative to the campaign root for the state schema.

Default campaign for an execution request naming no site: `{{ fleet.skill.config.default_campaign }}`. An explicitly named site always wins; never submit for another campaign silently.

Configured campaigns:
{% for startup in fleet.skill.config.startups %}
- {{ startup.name }} ({{ startup.campaign_type }}; canonical origin: {{ startup.canonical_origin }}): `./{{ startup.id }}/profile.md` and `./{{ startup.id }}/listings.csv` relative to the campaign root.
{% endfor %}
{% else %}
Setup is required. Resolve `fleet config path`, then read `./skills/config/marketing-i-startup-listings/README.md` relative to that settings root. Use $skills-i-write-or-edit-a-skill to configure non-secret routing and resync before starting a campaign.
{% endif %}

Read the selected startup's profile and tracker before opening submission forms. Use the projected default when no campaign is named. Select platforms that fit the campaign type; people and service businesses do not belong in SaaS directories unless they also own a qualifying product. Missing product facts should come from current company/repository docs and the live website before asking the user. Confirm the canonical website, account identity, product description, pricing and available assets before submitting. Never invent product claims or revenue.

Keep state in the canonical Vault files. Installed skill copies and browser session history are not campaign state. Live submission status must never be projected into installed Markdown. One operator works on a startup at a time; reread its tracker before writing and preserve concurrent changes.

## Execution contract

- Use `./references/platforms.md` as the initial candidate catalog. Recheck current submission routes, eligibility, costs and requirements on the platform itself. Add relevant candidates to the startup tracker as opportunities emerge.
- Prioritize product/audience fit, referral potential, link quality and effort. DR is Ahrefs' domain-wide backlink metric, not a Google score or proof of a valuable listing. Do not copy estimated DR or follow attributes into verified fields.
- Use the available computer-use browser tooling and its documented APIs for account signup, forms, asset uploads and submission. For extensive computer use, follow $fleet-i-code-folder-and-computer-topology to select the configured shared-computer-work machine and access route.
- Prefer existing authenticated accounts and the user's normal credential manager. Store only a non-secret account identity or credential-manager item reference. Authentication secrets, recovery codes and verification links must not enter profiles, trackers or tool output.
- Search for an existing listing by product name and canonical domain before creating one. Claim or update an appropriate existing listing instead of duplicating it. After interruption or an uncertain submit result, inspect the dashboard and public listing before retrying.
- A user request to submit listings authorizes ordinary free signup, saving drafts, uploading approved assets and submitting suitable listings. Follow the user's approved launch timing. Paid placements require an approved budget; revenue integrations require explicit authorization. Record the needed decision and continue other eligible platforms.
- Honor actual platform requirements without importing blanket prerequisites from another skill. A suitable listing does not require several comparison pages, a template gallery or a review campaign unless the platform actually requires them.
- Tailor truthful copy to the audience and field limits. Use approved profile copy where available and save useful variants in the profile. Prepare a preview before publishing when practical; do not schedule a public launch beyond the authorized timing.
- Record the draft/edit URL and next action as soon as a draft exists. Save state after account creation, draft save, submission, rejection or publication. Persist a concrete next action when a step is interrupted, blocked or waiting on moderation.
- `submitted` means the platform accepted the submission. `live` requires a publicly accessible listing. A live listing can still have an unverified backlink. Keep those facts separate.
- Verify the actual link element on the public rendered page: destination URL, anchor text, redirect target and `rel` values such as `nofollow`, `ugc` and `sponsored`. Inspect robots metadata separately when available. HTTP headers alone cannot prove an anchor's attributes. An ordinary follow link is an observed absence of those qualifiers, not a guarantee of ranking benefit or indexing.
- If MFA, CAPTCHA, payment, missing assets or a product decision needs human input, save the exact blocker and smallest next action. Continue other independent listings within the user's scope and time budget.
- End with submitted/live counts, verified links, unresolved blockers and the next action. Preserve enough state for a new chat to resume without reading this chat's history.

## Related skills

Load these by name when their capability is useful:

- $corey-directory-submissions: directory discovery, audience-specific positioning, listing copy and a submission catalog/tracker. Verify its dated SEO claims and platform facts; use only prerequisites actually needed for the selected submission.
- $claude-seo-backlinks: backlink profile analysis, referring domains, competitor link gaps and verification of existing backlinks. Use it for analysis and measurement alongside the listing tracker.
- $corey-launch: broader launch planning, Product Hunt preparation and launch timing. Use it when a submission is a public launch event.
- $corey-public-relations: press angles, journalist research, pitches and earned coverage. Use it for editorial opportunities such as Forbes. Sending outreach requires the user's explicit authorization.

## Example requests

- "Continue listings for [startup] for 30 minutes."
- "Submit the next three suitable free directories for [startup]."
- "Check whether our submitted listings are live and verify their backlinks."
- "Find additional directories that fit [startup] and add them to the queue."
