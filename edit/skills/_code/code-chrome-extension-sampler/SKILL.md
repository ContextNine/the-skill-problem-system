---
name: code-chrome-extension-sampler
description: Copy or extract an installed Chrome extension by extension ID into the local Chrome extension samples folder on macOS, resolving the extension name from manifest metadata and renaming the copied folder to that extension name. Use when the user wants to inspect, archive, compare, reverse-engineer, or sample a Chrome extension from Chrome profile data, or when they provide a Chrome extension ID and ask to copy, unzip, extract, or rename it for inspection.
---

# Code · Chrome Extension Sampler

## Purpose

Copy installed Chrome extension from Chrome profile data into configured sample folder. Read `_system/agents/edit/settings/skills/config/code-chrome-extension-sampler/README.md` first.

Use the bundled script so profile discovery, version selection, localized names, archive extraction, and folder naming are deterministic.

## Workflow

1. Accept a Chrome extension ID from the user.
2. Run `scripts/copy_chrome_extension.py <extension-id>`.
3. Script loads matching private config. If user names non-default destination, pass `--target <folder>`.
4. If Chrome has multiple matching profiles, either let the script choose the newest installed version or pass `--profile <Profile Name>` when the user cares which Chrome profile is used.
5. After copying, report the destination folder and the source profile/version.

## Script Usage

```bash
python3 /path/to/code-chrome-extension-sampler/scripts/copy_chrome_extension.py emdlbnkhjpfcooclfbodmhkhkohcjaoa
```

Useful options:

```bash
--config /path/to/config.json
--target /path/to/chrome-extension-samples
--chrome-user-data /path/to/Chrome
--profile Default
--version 1.2.3_0
--overwrite
--json
```

## Behavior

- Search configured Chrome user-data path for `*/Extensions/<extension-id>/`.
- Choose the newest version using the version folder name when `--version` is not provided.
- Read `manifest.json` and resolve names such as `__MSG_extName__` from `_locales/<default_locale>/messages.json`.
- Sanitize the extension name for a safe macOS folder name.
- Copy unpacked extension folders directly.
- Extract `.zip` or `.crx` archives if a matching archived source is encountered.
- Rename the destination folder to the resolved extension name, falling back to the extension ID when no name can be resolved.
- Avoid overwriting existing samples unless `--overwrite` is passed.

## Notes

- Installed Chrome extensions are usually already unpacked directories, not `.crx` files.
- Do not edit the copied extension unless the user explicitly asks; preserve it as an inspection sample.
