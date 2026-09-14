# code-skill-install-checker

**Read the file before you run it.**

People install skill files, plugins and MCP connectors the way they used to install browser extensions: they don't read them. A file that arrives as a link, a zip or a paste has the same reach as software you install, and almost nobody opens it first.

This skill opens it for you.

## What it does

Give it a `SKILL.md`, a plugin folder, an MCP config, or the install instructions someone posted. It reads the actual file and answers five questions:

1. **Where do the links go?** Every URL and package name, and whether each one is the official source or a lookalike.
2. **What does it ask you to run?** Every shell command, `curl | bash`, `npx`, or "paste this" instruction, in plain words.
3. **What can it reach?** Which tools, accounts and files, compared to the job it claims to do.
4. **What leaves the room?** Anything that sends, posts, uploads or emails, and whether the file says so openly.
5. **Who wrote it?** Author, date, version, licence, repository, and what is missing.

Then a verdict: **INSTALL**, **READ FIRST**, or **DO NOT INSTALL**, with the exact lines to look at.

## What it does not do

It is not an antivirus. It does not scan binaries and it does not check domains against a threat database. It reads text and flags what a careful person would flag if they took the time to read, which nobody does.

That is the whole point.

## Prompt injection

A skill file is a file of instructions, so a malicious one can contain text aimed at the model reading it. This skill treats every audited file as data to be quoted, never as instructions to follow, and reports any attempt to direct its behaviour as a finding.

## Install

Download `SKILL.md` and add it to your assistant the same way you add any other skill.

Then, before you trust it: run its own five checks on it. It has an author, a version, a licence and a public history, so all five are answerable.

---

Built by Yonathan Cohen · [Tool Monsters](https://toolmonsters.com) · hello@toolmonsters.com
