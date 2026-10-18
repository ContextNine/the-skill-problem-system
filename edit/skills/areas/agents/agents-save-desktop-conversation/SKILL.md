---
name: agents-save-desktop-conversation
description: Save a complete visible AI conversation from the Codex, ChatGPT, Claude, or another desktop chat app into a user-named local directory. Use only when explicitly invoked to archive, export, back up, or save an entire/current/specific desktop conversation or chat.
---

# Agents · Save Desktop Conversation

## Output Contract

Save into the exact directory the user names. If they name a parent directory, create a collision-safe child folder named `YYYY-MM-DD_HHMM-<conversation-title>`; if they give an exact output folder, use it. Never overwrite existing files silently.

Prefer these artifacts:

- `conversation.md`: readable UTF-8 transcript in chronological order.
- `conversation.pdf` or the app's native export: visual/archive copy when available.
- `manifest.json`: source app, title, source identifier or URL when available, capture time and timezone, capture method, files created, first and last message fingerprints, message counts by role, and completeness status.
- `attachments/`: only attachments the app exposes and the user is authorized to save. Preserve filenames where possible and link them relatively from the transcript.

Include visible user and assistant messages, visible tool/result blocks, code fences, links, timestamps when exposed, and attachment references. Exclude hidden system/developer prompts, private reasoning, credentials, and non-conversation app chrome.

## Capture Workflow

1. Resolve the source app, conversation, and absolute destination. Treat the current conversation as the source when the request says "this" or "current." Ask only when source or destination cannot be determined safely.
2. Use the strongest complete source available, in this order:
   - A native task/thread transcript tool or app export that can page through the full selected conversation.
   - A local app-owned transcript for the exact conversation ID, reading only that selected record and its referenced transcript file.
   - The app's built-in single-conversation export, print, or save function through available GUI control.
   - DOM/accessibility extraction through available browser or computer-control tools, scrolling from the true beginning to the true end and expanding truncated content.
   - Clipboard/UI capture as a last resort.
   Continue down this list when a method is unavailable; do not stop merely because a native task ID or transcript tool cannot be resolved. Load the environment's GUI/computer-control skill when one is available. Stop only after every safe applicable route has been exhausted.
3. For Codex, prefer task/thread tools or the exact local thread transcript. Resolve the current task ID from app context, task URL, title plus message match, or UI. Do not scan or export unrelated tasks when an exact ID is available.
4. For ChatGPT, Claude, or another desktop app, use available GUI/computer control and any app-native export first. A local print-to-PDF archive is acceptable when structured text is unavailable. Do not create a public share link unless the user explicitly asks.
5. Convert structured messages to Markdown without summarizing or rewriting. Preserve role order and code formatting. Use explicit markers for non-text items that cannot be embedded.
6. Write the artifacts, then verify completeness before reporting success.

## Completeness Gate

Do not call an export complete merely because the current model context contains the conversation. Context may be compacted or truncated.

Verify all of the following:

- The captured first visible message matches the conversation's true first message.
- The captured last visible message matches the latest message at capture time.
- No lazy-loaded history, collapsed response, code block, or continuation remains unopened.
- Message ordering is monotonic and no extraction chunk was duplicated at scroll boundaries.
- Every created file opens and is non-empty; Markdown/PDF text or page count is plausible for the source length.

Set `completeness` in `manifest.json` to `complete`, `partial`, or `unverified`, with a concise reason. If only a partial export is possible, save it only when useful, label it clearly, and tell the user exactly what is missing. Never claim "entire conversation" without passing the gate.

## Safety

Keep the archive local unless the user requests upload or sharing. Avoid broad reads of app databases or profile directories; select the exact conversation first. Do not include hidden prompts, private chain-of-thought, unrelated chats, authentication data, or app secrets. Treat destination contents as user data and preserve unrelated files.

## Handoff

Return absolute clickable paths to the export folder and primary artifacts, name the source app and conversation, state the completeness result, and mention any unavailable attachments or formatting.
