# Notion Copy Paste Vault Workflow

## Prior Scrape Method

Use this sequence to reproduce the LinkedIn Copy N Paste Vault scrape or adapt it to another public Notion page.

1. Fetch the public page HTML with `curl -L <url>`.
2. Inspect the HTML for `requiredRedirectMetadata.pageId`.
3. Call Notion's public app API through `notion-client` instead of relying on the skeleton HTML.
4. Start from the root page ID and run `api.getPage(pageId)`.
5. Save every returned record map to `raw_record_maps/<page-id>.json`.
6. Merge record maps into `all-record-map.json`.
7. Discover more page IDs from:
   - `recordMap.block[*].value.value.content`
   - child blocks of type `page`
   - `recordMap.collection_query[*][*][*].blockIds`
   - collection view `page_sort`
8. Recursively fetch every discovered page ID.
9. Cache record maps and resume from cache to survive Notion `429 Too Many Requests`.
10. Use exponential/backoff retry for network pages; cached pages can be replayed quickly.
11. For databases:
   - read `recordMap.collection` for schema names
   - read database row pages from collection query `blockIds`
   - export CSV from row page properties plus `id` and source URL
12. For assets:
   - collect `properties.source`, `format.display_source`, `format.page_icon`, `format.page_cover`, and `format.social_media_image_preview_url`
   - prefer `recordMap.signed_urls[block.id]` for Notion file assets
   - fall back to Notion image proxy and original URL
   - dedupe by `blockId + originalUrl`
   - write `assets_manifest.json`
13. Write:
   - `pages/*.md`
   - `pages_html/*.html`
   - `raw_html/*.html`
   - `databases/*.csv`
   - `assets/*`
   - `manifest.json`
   - `README.md`

For the original LinkedIn vault scrape, final verified counts were:

- 101 pages
- 2 databases
- 625 blocks
- 62 unique downloaded asset URLs
- 9 blocked `social_media_image_preview_url` assets
- 20 Post Templates rows
- 70 Media Engine Master Swipe File rows

## Organization Method

Use the root Notion page only for topic order. Do not duplicate the root rollup in final notes.

For the LinkedIn vault, write exactly 10 topic files:

1. The Profile Template
2. Post Templates
3. DM Templates
4. 365 Day AI Content Plan Template Generator
5. 7-Minute Content Creation Routine
6. 71 Winning Content Ideas
7. LinkedIn Profile Launch Checklist
8. Master Swipe File Of Top Content That Booked Calls
9. Accelerate Leads: Custom Micro Offer Generator
10. Accelerate Leads: 15 Micro Offer Ideas

Use database CSVs as row authority:

- `post-templates-*.csv`: 20 rows, row pages contain template bodies and example images.
- `media-engine-master-swipe-file-*.csv`: 70 rows, row pages contain swipe details and post images.

## OCR Rules

Run `tesseract <asset> stdout --psm 6` on content-bearing PNG/GIF assets.

Keep OCR text when it contains enough readable words to recover post/copy text. Keep local image references when layout or visual proof matters, especially:

- screenshots of social posts
- carousel examples
- visual-only social posts
- diagrams/frameworks

Drop or log as omitted:

- Notion SVG icons
- page covers
- generic social preview images
- aesthetic/humour-only images
- images with empty or unusable OCR that are not source content

## Tracking Requirements

Create `_tracking.md` in the final folder before processing.

Append after every successfully processed page or database:

- timestamp
- source path or ID
- target final file
- status
- assets inspected
- OCR kept/dropped
- notes

Finish with:

- processed page count
- processed database count
- unprocessed source page count
- unresolved/blocked asset count
- validation commands run
