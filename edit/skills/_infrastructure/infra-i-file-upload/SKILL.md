---
name: infra-i-file-upload
description: Use when the user asks to upload or share a file, or when a file is needed for a PR description, public resource, or private delivery.
---

# Infra · File Upload

Upload files with `publish upload` and return the stable URL from the response.

## Upload

Inspect the file for credentials, private data, hidden metadata, or material the user did not intend to publish. Stop on meaningful risk instead of silently redacting it.

Run `publish doctor --json` before the first upload in a task, then use the matching preset:

```bash
# PR evidence
publish upload <path-to-file> --namespace git --visibility unlisted \
  --owner-domain github --owner-type pull-request --owner-reference <owner/repo#number>

# Public resource
publish upload <path-to-file> --namespace public --visibility public \
  --owner-domain website --owner-type resource --owner-reference <stable-name>

# Private delivery
publish upload <path-to-file> --namespace private --visibility tenant \
  --owner-domain support --owner-type delivery --owner-reference <stable-name>
```

- Add `--expires-in` or `--expires-at` only when delivery should end automatically.
- Use the returned stable URL directly. Include the publication ID when it will be needed for updates or deletion.
- Never upload env files, credentials, private keys, authentication exports, cookies, database dumps, or unreviewed archives.
- If doctor or authentication fails, report the missing configuration without printing values. Do not retry with another service.

Read [[references/publisher-file-lifecycle|Publisher File Lifecycle]] only for versioning, expiry, download, or deletion.

## Use the URL in GitHub

- Embed images (`png`, `jpg`, `jpeg`, `gif`, `webp`) as `![description](URL)`.
- Link videos (`mp4`, `mov`, `webm`) as `[screen recording](URL)` because GitHub does not inline-play externally hosted video.
- When an inline preview genuinely helps and the clip is shorter than about 30 seconds, also upload a GIF preview:

```bash
ffmpeg -i recording.mp4 -vf "fps=10,scale=800:-1" -loop 0 preview.gif
```

Embed the GIF and link the full-quality video below it.
