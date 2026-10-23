# Planning and granular mode

Use this after the source reads in `../SKILL.md`. Work from the full Time Game note, including its current constraints and Commitments, and the personal goal notes. Never copy its current table into this skill or hard-code note headings.

## Establish capacity and progress

- Read active Todoist tasks with `td task list --all --json`, including undated tasks; use `td task view` or a narrower query if detail is needed. Read relevant completions with `td completed list --since <week-Monday> --until <next-Monday> --all --json`. For a next-week plan, include all next-week dated tasks in the active set. Check CLI help if flags change.
- Use `$integrations-i-google-calendar` to exclude the calendar named exactly `Todoist` and read each remaining relevant calendar for today through Sunday. For next-week planning, read next Monday through Sunday as well. Expand recurring instances, honor all-day dates, and merge overlapping busy intervals. Ignore cancelled, declined, or free events as appropriate. Count a timed Todoist task only once if it mirrors another commitment; date-only tasks still require effort but do not reserve 24 hours.
- Compare each recurring Commitment's target with evidenced work already completed, work scheduled but unfinished, and the unscheduled remainder. A checked task may prove an action occurred, but not its duration unless the note or review supplies that duration. Calendar events prove only that time was reserved. A recurring item completed yesterday can still be due today.
- Apply Time Game's protected work and timing preferences even when they are absent from Calendar. A target that cannot fit after protected work, obligations, and reasonable slack is deferred. Never squeeze a long-block-only task into fragments or pretend an undated Todoist task has no time cost.

## Update today's and this week's notes

Start with today's note. Its unchecked tasks may have been carried forward automatically; treat them as current, not as new tasks to append. Earlier daily notes establish progress and completed instances, but do not create a permanent duplicate ban. For an unchanged intention with stale suggested timing, adjust only the clearly stale timing while preserving the action and user wording.

Choose zero to three useful, realistic new daily checkbox tasks. Add a task only when an equivalent action is absent from Calendar, Todoist, today's note, and the current weekly note. In granular mode, also deduplicate against TaskNotes already linked in either target note. Put each new checkbox under the semantically relevant existing heading, with plain-English timing inside the task when it matters, ideally naming the day or date so later carryover is recognizable. Do not use TaskNotes `scheduled` or `due` fields as a substitute for a note recommendation.

Reconcile the current weekly note after the daily note. Check a broad weekly goal only when completed work or Matt's review answers establish the whole goal. Partial progress stays unchecked. If a meaningful opening remains, add at most one new broad weekly goal under a suitable existing heading, and only if that goal is not already represented by equivalent Calendar, Todoist, or note work. Zero changes is valid. Do not turn every Commitment into a new checkbox.

When the request is to plan next week after Sunday review, use the actual next-week Calendar, Todoist, quarterly goals, current week's evidence, and review answers. Put a small set of realistic broad goals directly in next week's personal weekly source note. Deduplicate there too. If absent, create the source note with `vault periodic --date <next-Monday> --teamspace-folders personal` and then inspect the created source before editing it.

## Granular mode

Only on explicit request, read `_system/docs/commands/Tasks And Projects.md` relative to the Vault root and inspect TaskNotes under active teamspace task folders. Prefer `in-progress`, `to-be-resumed`, and `up-next`; inspect backlog only when asked or when no active task supports the chosen goal. Rank by alignment with overall and quarterly goals, weekly goals, and Commitments. A prioritized teamspace raises relevant work there, not every item in the folder.

Link a selected actionable TaskNote as `Task name` in a new daily or weekly checkbox only if it is unscheduled and passes the same capacity and duplicate checks. Verify that the name resolves to one note; skip ambiguous duplicate filenames rather than writing a misleading link. Leave every source TaskNote, including its frontmatter, untouched. If no task qualifies, add no granular checkbox.
