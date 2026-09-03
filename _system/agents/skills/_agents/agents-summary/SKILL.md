---
name: agents-summary
description: Create explicit chat summaries for context in future chats. Use when the user wants a summary of what was found, changed, original problems, how solutions fix them, and exact files changed.
---

# Agents · Summary

Important: not to save a summary file, but to present the summary in the format requested here to the user that requests it.

Create an explicit summary of this chat that includes:

- What you found
- What you changed
- The original problems
- How the solutions fix them
- The exact files you changed

Format requirements:

- Start the summary with:

***
Previously, I had a chat with an agent that produced this summary:

# Summary

***

- End the summary with:

Now, I want you to consider this and,

***

This starting and ending framing helps paste the summary into a new chat for faster context handoff.
