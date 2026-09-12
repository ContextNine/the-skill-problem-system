---
name: infra-i-file-upload
description: Publishes intentional private, public, and Git-owned files through CTX9 Publisher. Use when the user asks to upload, host, share, replace, expire, or delete a file or video for a PR, public resource, or lead magnet.
---

# Infra · File Upload

Use `publish` with `kind=file`. Read [[references/publisher-file-lifecycle|Publisher File Lifecycle]] before the first upload in a task.

## Workflow

1. Choose the namespace: `git` for repository-owned media, `public` for directly shareable resources, or `private` for authenticated delivery. Choose a stable owner reference that identifies the file's real owner.
2. Inspect the local file name, type, and relevant contents for credentials, private data, hidden metadata, or material the user did not intend to publish. Stop on meaningful risk; do not silently redact.
3. Run `publish doctor --json` before the first mutation.
4. Upload with an explicit namespace and compatible visibility. Add `--expires-in` or `--expires-at` only when delivery should end automatically:

```bash
publish upload ./evidence.mp4 --namespace git --visibility unlisted --owner-domain github --owner-type pull-request --owner-reference owner/repo#123 --expires-in 2w --media-type video/mp4
publish upload ./guide.pdf --namespace public --visibility public --owner-domain website --owner-type resource --owner-reference guide-v2 --media-type application/pdf
publish upload ./customer-export.zip --namespace private --visibility tenant --owner-domain support --owner-type customer-export --owner-reference case-123 --expires-in 1w --media-type application/zip
```

5. Return the stable URL, publication ID, version, checksum, byte size, MIME type, namespace, visibility, expiry or `none`, and local source disposition.

## Safety

- Public upload is an external mutation and must be authorized by the request.
- Never upload env files, credentials, private keys, authentication exports, cookies, database dumps, or unreviewed archives.
- Prefer a new immutable publication version. Exact replacement or deletion requires the current ETag, exact publication ID, and explicit intent.
- Delete only with `publish delete <id> --etag <etag> --yes`; never infer a namespace-wide deletion.
- Do not create buckets, enable public access, or bind domains during an ordinary upload.
- A lead-magnet file uses the `public` namespace. Use `$marketing-i-lead-magnets` when the request also includes its signup, confirmation, download, or VSL flow.

If doctor fails, report missing configuration names or the connectivity boundary without printing values. Do not create plaintext credential copies or switch services silently.
