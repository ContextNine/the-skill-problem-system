# Issue tracker: Local Markdown

Issues and specs (you may know a spec as a PRD) for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/mp-wayfinder`. The **map** is a file with one **child** file per ticket.

- **Effort root**: `.agents/plans/<wayfinder-name>/` — the canonical filesystem record, even when an external tracker is mirrored.
- **Map**: `.agents/plans/<wayfinder-name>/<wayfinder-name>.md` — Destination, Notes, ticket graph, Decisions-so-far, Fog, and Out-of-scope.
- **Child ticket**: `.agents/plans/<wayfinder-name>/tickets/NN-<slug>.md`, numbered from `01`, with the question in the body and tracker state in YAML frontmatter.
- **Map lifecycle**: a map is `charting` during the live one-question-at-a-time Wayfinder interview and becomes `active` only after explicit human confirmation.
- **Ticket state**: `ticket_type` records `research`/`prototype`/`grilling`/`task`; `status` records `draft`/`open`/`claimed`/`resolved`/`out-of-scope`; `claimed_by` records the active driver. Draft tickets cannot be claimed.
- **Blocking**: `blocked_by` is a YAML list of filename-only Obsidian links. A ticket is unblocked when every linked ticket is `resolved`.
- **Frontier**: scan `tickets/` for files that are open, unblocked, and unclaimed; first by filename number wins.
- **Claim**: set `status: claimed` and `claimed_by` and save before any work.
- **Resolve**: append the answer under `## Answer`, set `status: resolved`, clear `claimed_by`, then append a one-line gist plus filename-only Obsidian link to the map's Decisions-so-far.
