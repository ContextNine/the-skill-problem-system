# Page-streaming refinery

Pipeline:

```text
PDF -> page candidates with coordinates -> normalized records
    -> exceptions/repairs -> validation -> CSV
```

## 1. Inspect

`inspect` hashes source, records page count and geometry, probes representative pages, measures embedded text and raster-image coverage, and creates job-local adapter template. It does not extract whole document.

Encrypted PDFs fail explicitly. Obtain authorized decrypted copy instead of embedding passwords in commands or job files.

## 2. Design adapter

Arbitrary PDFs have no universal record schema. Treat adapter as executable specification for one document family:

- canonical fields and required fields;
- page-layout variants;
- extraction regions and table settings;
- header/footer and non-record classifications;
- wrapped-row and page-boundary stitching;
- normalization and document invariants.

Use coordinate-aware words/cells. Do not clean an intermediate CSV: spatial evidence would be lost.

For borderless tables, useful `pdfplumber` controls include `vertical_strategy`, `horizontal_strategy`, `explicit_vertical_lines`, `explicit_horizontal_lines`, `snap_x_tolerance`, `snap_y_tolerance`, `text_x_tolerance`, and `text_y_tolerance`. Crop first when page contains several regions. Use `Page.to_image().debug_tablefinder(...)` while developing. `snap_header_resolution` is not a supported setting.

Reference: [pdfplumber table extraction](https://github.com/jsvine/pdfplumber/blob/stable/README.md#extracting-tables).

## 3. Extract

Process pages independently. Each page produces atomic `pages/NNNNNN.candidates.jsonl`; completed shards become resume checkpoints. Pipeline closes `pdfplumber` page caches after each page.

Resume requires exact source SHA-256, adapter ID, and adapter version. Adapter edits require version bump. Hash mismatch rejects stale checkpoints.

Page candidates retain:

- `candidate_id`
- `source_sha256`
- `page`
- `bbox` in PDF points `(x0, top, x1, bottom)`
- `sequence`
- `extraction_method`
- `layout_variant`
- `raw_text` and/or `cells`
- `flags`

Repeated margins are detected across completed pages and marked before normalization. Adapter handles multiple tables, layout changes, wraps, and page transitions.

PDF content streams can require far more memory than file size. Page sharding and cache closure bound retained working state. See [pypdf text-extraction memory note](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

## 4. OCR fallback

Default `--ocr auto` prefers digital words. Page OCR triggers only when:

- embedded text has fewer than 20 useful non-whitespace characters; and
- raster images cover at least half page.

Blank vector pages stay blank. Likely scans never disappear silently.

OCR flow:

1. Poppler renders one page at 300 DPI.
2. Tesseract emits TSV word boxes and confidence.
3. Pixel boxes convert back to PDF points.
4. Temporary page image is deleted unless `--keep-page-images`.

Unavailable Poppler, Tesseract, or Pillow creates page candidate flagged `ocr_unavailable` and a documented exception later.

## 5. Normalize and repair

Adapter stitches candidate streams before constructing canonical records. Canonical numbers originate as `Decimal`; dates originate as `date`; serialized JSON/CSV uses exact decimal strings and ISO dates.

Codex may repair a small unresolved set using raw candidate, coordinates, and adjacent candidates. Never submit whole document. Record each repair in JSONL:

```json
{"source_candidate_ids":["..."],"changed_fields":{"description":"corrected text"},"method":"codex_bounded_review","confidence":0.94}
```

IDs must exist. Repairs change normalized fields only; raw candidates remain immutable. Do not guess absent values.

## 6. Validate and export

Run validation after every normalization change. Inspect failures and exception counts before export. Normal export blocks on invalid jobs. Use `--allow-invalid` only for deliberate partial output; manifest records override and failed checks.

## Job bundle

```text
manifest.json
probe.json
pages/*.candidates.jsonl
normalized.jsonl
exceptions.jsonl
repairs.jsonl
validation.json
output.csv
adapter.py
```
