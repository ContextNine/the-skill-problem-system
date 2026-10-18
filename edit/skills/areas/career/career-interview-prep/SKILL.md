---
name: career-interview-prep
description: Use when the user explicitly invokes this skill to create or develop a minimal Markdown interview story workbook in a specified directory, with a separate guide explaining how best to answer every question.
---

# Career interview prep

Create two complementary files: a minimal workbook for the user to type answers and stories, and a companion guide with specific advice for answering each question. Build toward 8–12 real stories covering customer / user focus, success, failure, conflict, problem-solving, learning & growth, leadership, and time management. These are preparation themes, not every employer's interview rubric.

## Inputs and destination

- `target_dir`: required destination supplied at invocation. Report a missing destination; never assume the current workspace.
- `workbook`: optional Markdown path, relative to the destination or an absolute path inside it. Continue that exact file, or create it if missing.
- `mode`: optional `self-serve`, `review`, or `mock`; default to `self-serve`. All modes put questions in files.
- Existing notes, resume, job descriptions, and interview dates are optional context. Confirm stale career details before treating them as current facts.

Resolve shell-escaped paths as filesystem paths. Follow destination instructions and nearest README before editing. Keep outputs inside the destination and follow its Git and note-format rules.

For a new workbook, use `./assets/workbook.md` and `./assets/guide.md`, resolved relative to this skill. Default outputs are `./behavioral-prep/Interview workbook.md` and `./behavioral-prep/README-interview-prep.md`, resolved relative to `target_dir`. A specified workbook replaces the default workbook path; keep the guide alongside it. Substitute the actual filenames in links and continuation examples. Use basename-only Obsidian links in a Vault and relative Markdown links elsewhere.

Read existing files before editing. Reuse the default workbook if present, or a sole workbook candidate in the prep folder, excluding READMEs. If several candidates exist, report the filenames and ambiguity without editing them. Never reset an existing workbook from the asset or discard user answers. Explicit requests to simplify or redesign an unanswered template authorize replacing that template.

## Two-file contract

The workbook contains only a short opening, plain section headings, questions, and empty space for answers. Leave blanks genuinely blank. Do not add tables, status labels, story IDs, repeated answer placeholders, rubrics, coverage tracking, administrative logs, schedules, or nested STAR forms. The user should be able to type a story directly beneath its question. Keep further stories under simple headings chosen by the user.

The guide names `$career-interview-prep` as the skill that created it and explains how to invoke it again. Give each workbook question a matching heading in the guide. Explain what kind of incident to choose, which details make the answer useful, how to structure it, and common mistakes specific to that question. Planning questions need only practical answering advice. Keep general STAR and delivery advice in the guide, not the workbook.

All interview questions and follow-ups stay in the files. Never ask them in chat or through a question tool. Chat is for brief progress reports and links. Do not add tasks, calendar events, reminders, applications, or outbound messages without a separate request.

## Developing answers

Read the current workbook on every invocation. Accept rough bullets and incomplete memories. Keep the user's raw answers and voice; do not replace their answer with a polished version unless they ask for that. Save question-specific review feedback and follow-up questions in the companion guide beneath the matching heading. Do not clutter the workbook with coaching notes.

Use STAR and reflection to identify the situation and stakes, personal responsibility, decisions and actions, result and evidence, and learning. When something is vague, put a focused follow-up in the guide explaining what detail is missing and how to supply it. One incident can support several themes; do not split one incident into several stories just to reach a count.

Never invent metrics, dates, titles, responsibilities, or impact. Distinguish personal actions from team results, estimates from measurements, and observed outcomes from assumptions. Preserve uncertainty. Explain anonymization of confidential details in the guide. For failure and conflict, explore ownership and the other person's reasonable perspective. Do not turn an unresolved failure into a success.

If the user requests a spoken draft, write natural first-person prose that can be delivered in about two minutes, grounded in confirmed details. Help adapt emphasis to different questions without changing facts. Build an introduction from confirmed experience and the target role. Resume edits require the user to choose the source resume. Company-specific hiring advice needs supplied interview materials or verified official sources; cite researched claims. Creating this workbook from supplied themes requires no research.

## Review and practice

In `self-serve` mode create or continue the two written materials and stop without a chat questionnaire. In `review` mode read the user's answers and add useful feedback and focused follow-ups to the guide. Do not recreate the workbook's blank template.

In `mock` mode append a plain practice-question heading and question to the workbook. On the next invocation, read the user's attempt and add a follow-up there. After the follow-up is answered, put feedback in the guide on clarity, personal contribution, judgment, evidence, and reflection. Do not reveal a model answer before the attempt or claim to measure speaking confidence from text alone.

Before closing, check that every workbook question has matching answering guidance and that the workbook remains minimal. Save the files, follow the destination's completion rules, and link both outputs. If writes fail, report the exact blocker; do not start asking the interview questions in chat.
