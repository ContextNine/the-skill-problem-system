---
name: creative-install-font
description: Finds, archives, installs, and selects a font on macOS. Use when the user explicitly invokes this skill with a font or typeface name and wants a free, demo, or personal-use copy installed and ready in Font Book.
---

# Creative · Install Font

Install a named font for the current macOS user and finish with its family selected in Font Book.

## Requirements

- Read `_system/agents/_package/instance/skills/config/creative-install-font/README.md` and validate `config.toml` before downloading or copying files.
- Use `$browser:control-in-app-browser` to search the web, inspect the source, and download the font.
- Use `$computer-use:computer-use` for all Font Book interaction.

## Source safely

1. Search for the exact font name in the browser even when a likely URL is known. Prefer, in order: the designer or foundry, an official project repository, Google Fonts, Font Squirrel, or another established distributor authorized by the rights holder.
2. Verify the family name, designer or foundry, included styles, and license on the source page. Prefer open-source or broadly licensed releases; an official demo or personal-use-only release is acceptable for this personal workflow.
3. Never use an unauthorized mirror for a commercial font. If no legitimate free, demo, or personal-use release exists, stop and report the best legal option without buying it.
4. Download through the browser. Keep the source URL and license name for the final report.

## Archive and install

1. Extract downloads in a temporary directory and accept only `.otf`, `.ttf`, or `.ttc` font files. Ignore webfont-only formats unless the user explicitly asks for them.
2. Inspect each font's embedded family/style metadata. Reject unrelated bundled fonts. Preserve the source filename.
3. Copy every intended desktop style into `archive_directory`. If a same-named archive file already exists, compare hashes: reuse an identical file, but never overwrite a different file without explicit approval.
4. In Font Book, switch to `My Fonts` before opening the archived file so installation cannot implicitly add it to whichever custom collection was selected. Install it for the current user. Handle duplicate warnings conservatively; keep an identical installed copy and do not replace a different version without approval.
5. Add the family to a Font Book collection only when the user names one. Do not infer that every installed font is a favorite.
6. Search Font Book for the family, select the family or its only face, and leave Font Book frontmost with that row selected.

## Verify and report

- Confirm the archived font path exists, Font Book shows the family as installed/active, and the requested family remains selected.
- Report the source URL, designer/foundry, license, archived file paths, installed scope, and collection change if any.
- Do not delete the browser download or temporary extraction as part of this workflow unless the user asks.
