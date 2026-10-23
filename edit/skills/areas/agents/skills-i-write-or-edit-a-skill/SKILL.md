---
name: skills-i-write-or-edit-a-skill
description: Use when the user asks to create, edit, rename, reorganize, thin, or improve an agent skill or its supporting files.
---

# Skills · Write or edit a skill

Read `./references/skill-authoring.md` before changing a skill. If the skill or another owned file needs machine variants or inline Fleet values, also read `./references/fleet-templating.md`.

Project stable, non-secret instance settings into installed skills during sync wherever possible. Keep a single authoritative settings source; do not make agents resolve private configuration on every invocation. Credentials and genuinely live state must never be projected. Read the Fleet templating reference for the per-skill projection contract.

Always write file references as relative paths, using `./` or `../` from the referring document or an explicitly resolved project/config root. Mention other skills only by `$skill-name`, never by their filesystem location.
