---
name: mp-wayfinder
description: Plan a huge chunk of work through a live charting interview, storing a shared filesystem map of decision tickets and later resolving them until the way to the destination is clear.
disable-model-invocation: true
---

# Matt P Skills · Engineering · Wayfinder

A loose idea has arrived — too big for one agent session, and wrapped in fog: the way from here to the **destination** isn't visible yet. Wayfinding is about finding that way, not charging at the destination. This skill charts the way as a **shared filesystem map**, then works its **decision tickets** — questions whose resolution is a decision, not slices of a build to execute — one at a time until the route is clear.

The destination varies per effort, and naming it is the first act of charting — it shapes every ticket. It might be a spec to hand off and iterate on, a decision to lock before planning starts, or a change made in place like a data-structure migration. The map is domain-agnostic — engineering work, course content, whatever fits the shape.

## Plan, don't do

Wayfinder is **planning** by default: each ticket resolves a decision, and the map is done when the way is clear — nothing left to decide before someone goes and does the thing. The pull to just do the work is usually the signal you've reached the edge of the map and it's time to hand off. An effort can override this in its **Notes** — carrying execution into the map itself — but absent that, produce decisions, not deliverables.

## Refer by name

Every map and ticket has a **name** — its title. In everything the human reads — narration, the map's Decisions-so-far — refer to it by that name, never by a bare number or slug. Names read at a glance. A filename, tracker id, or URL may carry identity, but the linked name remains what the human sees.

## The Map

The map is one canonical Markdown file. Its tickets are child Markdown files in the map's `tickets/` directory. An external issue tracker may mirror these artifacts when an effort explicitly asks for it, but it is not the only store.

The map is an **index**, not a store. It lists the decisions made and points at the tickets that hold their detail; a decision lives in exactly one place — its ticket — so the map never restates it, only gists it and links.

### Filesystem standard

Unless the user explicitly chooses another canonical tracker, store every Wayfinder effort in:

```text
.agents/plans/<wayfinder-name>/
  <wayfinder-name>.md
  tickets/
    01-<ticket-name>.md
    02-<ticket-name>.md
```

- The directory name is the stable Wayfinder name.
- `<wayfinder-name>.md` is the root map and dependency chart.
- `tickets/` contains one numbered file per child ticket; never combine tickets in one file.
- In an Obsidian vault, use filename-only `[[Obsidian links]]` between the map and tickets.
- Git history supplies durable conversation history. Append a ticket's answer in that ticket when it resolves.
- Claims, status, type, and blocking live in YAML frontmatter so another session can compute the frontier without loading every answer.
- Maps move from `charting` to `active` only after the human confirms the draft map has the right destination, ticket coverage, and visible fog. Tickets remain `draft` until that confirmation.

If the repo provides tracker-specific Wayfinding operations, consult them for any additional fields or mirroring. The filesystem copy remains canonical unless the effort's Notes explicitly override it.

### The map body

The whole map at low resolution, loaded once per session. Its ticket graph may show every named ticket and blocking edge, but detailed questions and answers live only in the ticket files. The current frontier is computed from ticket frontmatter.

```markdown
## Destination

<what reaching the end of this map looks like — the spec, decision, or change this effort is finding its way to. One or two lines; every session orients to it before choosing a ticket.>

## Notes

<domain; skills every session should consult; standing preferences for this effort>

## Ticket graph

<low-resolution dependency chart using ticket names; no duplicated questions or answers>

## Decisions so far

<!-- the index — one line per closed ticket: enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [<closed ticket title>](link) — <one-line gist of the answer>

## Not yet specified

<!-- see "Fog of war": in-scope fog you can't ticket yet; graduates as the frontier advances -->

## Out of scope

<!-- see "Out of scope": work ruled beyond the destination; closed, never graduates -->
```

### Tickets

Each ticket is a child file of the map, sized to one 100K token agent session. Use this shape:

```markdown
---
type: wayfinder-ticket
title: <ticket title>
map: "[[<wayfinder-name>]]"
status: draft
ticket_type: grilling
mode: HITL
blocked_by: []
claimed_by:
---

## Question

<the decision or investigation this ticket resolves>
```

Each ticket's `ticket_type` is one of `research`, `prototype`, `grilling`, or `task` (see [Ticket Types](#ticket-types)). An external tracker mirror may express the same value as a `wayfinder:<type>` label.

A session **claims** an active ticket by setting `status: claimed` and `claimed_by` to the driver, **first**, before any work, so concurrent sessions skip it. Save the claim before investigating. An `open` ticket with an empty `claimed_by` is unclaimed. A `draft` ticket belongs to a map still being charted and cannot be claimed or resolved yet.

Blocking uses the `blocked_by` frontmatter list and is rendered in the map's ticket graph. A ticket is **unblocked** when every linked ticket blocking it has `status: resolved`; the **frontier** is the open, unblocked, unclaimed children, ordered by filename number — the edge of the known.

The answer is absent while a ticket is open. On resolution, append it under `## Answer`, set `status: resolved`, and clear `claimed_by`. Assets created while resolving a ticket are linked from the ticket, not pasted in.

## Ticket Types

Every ticket is either **HITL** — human in the loop, worked *with* a human who speaks for themselves — or **AFK**, driven by the agent alone. A HITL ticket only resolves through that live exchange; the agent never stands in for the human's side of it (a grilling agent that answers its own questions has broken this).

- **Research** (AFK): Reading documentation, third-party APIs, or local resources like knowledge bases to surface a fact a decision waits on. Resolved by a `/mp-research` **subagent**. Use when knowledge outside the current working directory is required.
- **Prototype** (HITL): Raise the fidelity of the discussion by making a cheap, rough, concrete artifact to react to — an outline, a rough take, a stub, or UI/logic code via the /mp-prototype skill. Links the prototype as an asset. Use when "how should it look" or "how should it behave" is the key question.
- **Grilling** (HITL): Conversation via the /mp-grilling and /mp-domain-modeling skills. The default case.
- **Task** (HITL or AFK): Manual work that must happen before a *decision* can be made — nothing to decide, prototype, or research, but the discussion is blocked until it's done. Signing up for a service so its API can be judged, provisioning access, moving data so its shape can be seen. This is the one type that *does* rather than decides — and it earns its place by unblocking a decision, not by delivering the destination. The agent drives it alone where it can (AFK); otherwise it hands the human a precise checklist (HITL). Resolved when the work is done; the answer records what was done and any resulting facts (credentials location, new URLs, row counts) later tickets depend on.

## Fog of war

The map is _deliberately_ incomplete: don't chart what you can't yet see. Beyond the live tickets lies the **fog of war** — the dim view of decisions and investigations you can tell are coming but can't yet pin down, because they hang on questions still open. Resolving a ticket clears the fog ahead of it, graduating whatever's now specifiable into fresh tickets — one at a time, until the way to the destination is clear and no tickets remain.

The map's **Not yet specified** section is where that dim view is written down: the suspected question, the area to revisit later. It's the undiscovered frontier _toward_ the destination — everything here is in scope, just not sharp enough to ticket. Write as loosely or as fully as the view allows; it doubles as a signpost for collaborators reading where the effort is headed.

**Fog or ticket?** The test is whether you can state the question precisely now — _not_ whether you can answer it now.

- **Ticket when** the question is already sharp — even if it's blocked and you can't act on it yet.
- **Not yet specified when** you can't yet phrase it that sharply. Don't pre-slice the fog into ticket-sized pieces: it's coarser than a ticket, and one patch may graduate into several tickets, or none, once the frontier reaches it.

**Not yet specified** excludes what's already decided (Decisions so far), what's already a live ticket, and what's out of scope (the next section).

## Out of scope

Fog only ever gathers _toward_ the destination. The destination fixes the scope, so work beyond it is **out of scope** — it isn't fog, and it doesn't belong in **Not yet specified**. It gets its own **Out of scope** section on the map: work you've consciously ruled out of _this_ effort. Scope, not sharpness, lands it here.

Out-of-scope work never graduates — the frontier stops at the destination — so it returns only if the destination is redrawn, and then as a fresh effort, not a resumption.

Ruling something out of scope is a scoping act, not a step on the route. When a ticket that already exists turns out to sit past the destination — mis-scoped in while charting, or exposed by a resolution — **close it** (a closed ticket is unambiguously off the frontier) and leave one line in the **Out of scope** section: the gist plus why it's out of scope, linking the closed ticket. It stays out of **Decisions so far**, which records the route actually walked — a scope boundary isn't a step on it.

## Invocation

Two modes. Either way, **never resolve more than one ticket per session** — with the exception of research tickets.

### Interview cadence

Charting defaults to one question at a time, but the human may request **ordered batch mode** for the whole effort or one part of it. Record the selected cadence in the map's Notes.

In ordered batch mode:

- Ask a bounded batch of related questions, normally five to eight.
- Order questions by dependency. Later questions may say how to answer under each earlier choice, so the human can work through the batch sequentially in one reply.
- Give a recommended answer and its main trade-off for every question.
- Number questions and ask the human to reply with matching numbers; accept prose when they prefer it.
- Do not silently treat unanswered questions as agreement. Carry them into the next batch or ask a focused follow-up.
- After each reply, update the draft map and tickets before asking the next dependent batch.

The human may switch cadence at any time. The goal is shared understanding, not ritual adherence to one-question turns.

### Chart the map

User invokes with a loose idea.

Charting is a live, multi-turn grilling session in the current conversation. A request to start Wayfinder is not satisfied by writing a guessed ticket set and stopping.

1. **Open the charting session.** Create the filesystem map at `.agents/plans/<wayfinder-name>/<wayfinder-name>.md` with `status: charting`. Any early ticket files use `status: draft`.
2. **Name the destination.** Run `/mp-grilling` and `/mp-domain-modeling` using the selected interview cadence until the destination and scope boundary are explicit.
3. **Map breadth-first.** Continue interviewing across the whole space rather than resolving one branch deeply. After each answer or batch, revise, add, merge, split, or remove draft tickets and update fog. Draft tickets are hypotheses, not a declaration that charting is complete.
4. **Ask for map confirmation.** Summarize the proposed destination, ticket names, dependency shape, fog, and out-of-scope boundary. Continue grilling until the human explicitly confirms the map is ready. If this surfaces no fog and the whole journey fits one session, explain that no Wayfinder is needed and ask how to proceed.
5. **Activate the map.** Change the map to `status: active`, change surviving draft tickets to `status: open`, then wire `blocked_by` links and the dependency chart in a second pass. Only now does the frontier exist.
6. **Fire the research subagents.** For each active `research` ticket, spin up a `/mp-research` subagent to resolve it in parallel, capturing findings in a research note linked from the ticket. Use a throwaway `research/<name>` branch only where the repository workflow calls for one.
7. Stop after activation — charting resolves no non-research ticket.

### Work through the map

User invokes with a map (URL or number). A ticket is **optional** — without one, you pick the next decision, not the user.

1. Load the **map** — the low-res view, not every ticket body.
2. Confirm the map has `status: active`; if it is still `charting`, resume charting with the cadence recorded in Notes instead of claiming a draft ticket.
3. Choose the ticket. If the user named one, use it. Otherwise take the first frontier ticket in numeric order. **Claim it** in frontmatter before any work.
4. Resolve it — **zoom as needed**: fetch the full body of any related or closed ticket on demand; invoke the skills the `## Notes` block names. If in doubt, use `/mp-grilling` and `/mp-domain-modeling`.
5. Record the resolution: append the answer under `## Answer`, set `status: resolved`, clear the claim, and **append a context pointer** to the map's Decisions-so-far.
6. Add newly-surfaced ticket files, then wire their `blocked_by` fields and the map graph; graduate any fog the answer has made specifiable, clearing each graduated patch from **Not yet specified** so it lives only as its new ticket. If the answer reveals a ticket — this one or another — sits beyond the destination, set it `status: out-of-scope` and **rule it out of scope** rather than resolving it on the route. If the decision invalidates other parts of the map, update or delete those tickets.

The user may run unblocked tickets in parallel, so expect other sessions to be editing the tracker concurrently.
