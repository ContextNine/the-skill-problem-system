---
name: infra-file-upload
description: Publishes intentional PR media, public resources, videos, and lead-magnet files through CTX9 Publisher. Use when the user asks to upload, host, share, replace, or delete a file or video for a PR, public resource, or lead magnet.
---

# Infra · File Upload

Use `publish` with `kind=file`. Read [[references/publisher-file-lifecycle|Publisher File Lifecycle]] before the first upload in a task.

## Workflow

1. Classify purpose as `pr`, `public-resource`, or `lead-magnet` and choose the narrowest collection and owner reference.
2. Inspect the local file name, type, and relevant contents for credentials, private data, hidden metadata, or material the user did not intend to publish. Stop on meaningful risk; do not silently redact.
3. Run `publish doctor --json` before the first mutation.
4. Upload with explicit visibility and purpose:

```bash
publish upload ./evidence.mp4 --visibility unlisted --purpose pr --collection repo --owner-domain github --owner-type pull-request --owner-reference pr-123 --media-type video/mp4
publish upload ./guide.pdf --visibility public --purpose public-resource --collection guides --owner-reference guide-v2 --media-type application/pdf
publish upload ./resource.pdf --visibility public --purpose lead-magnet --collection offer-slug --owner-reference offer-v1 --media-type application/pdf
```

5. Return the stable URL, publication ID, version, checksum, byte size, MIME type, visibility, and local source disposition.

## Safety

- Public upload is an external mutation and must be authorized by the request.
- Never upload env files, credentials, private keys, authentication exports, cookies, database dumps, or unreviewed archives.
- Prefer a new immutable publication version. Exact replacement or deletion requires the current ETag, exact publication ID, and explicit intent.
- Delete only with `publish delete <id> --etag <etag> --yes`; never infer a collection deletion.
- Do not create buckets, enable public access, or bind domains during an ordinary upload.
- Use `$marketing-lead-magnets` when the asset belongs to a signup, confirmation, download, or VSL flow.

If doctor fails, report missing configuration names or the connectivity boundary without printing values. Do not create plaintext credential copies or switch services silently.
