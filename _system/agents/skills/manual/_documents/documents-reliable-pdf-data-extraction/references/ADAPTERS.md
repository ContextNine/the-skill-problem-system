# Adapter contract

Copy `assets/adapter_template.py` into each job as `adapter.py`. `inspect` does this when missing.

## Required constants

```python
ADAPTER_ID = "document-family"
ADAPTER_VERSION = "1"
FIELDS = ("date", "description", "amount")
REQUIRED_FIELDS = ("date", "description", "amount")
FIELD_TYPES = {"date": "date", "description": "string", "amount": "decimal"}
```

`ADAPTER_ID` identifies schema/layout family. Increment `ADAPTER_VERSION` for any extraction or normalization change. Resume refuses version drift.

Supported field types: `string`, `decimal`, `integer`, `date`, `boolean`.

## Required functions

### `classify_page(page)`

Return stable layout name. Page mapping contains dimensions, page number, extraction method, words, text, image coverage, and margin signatures. Classify cover pages, continuation pages, tables, appendices, and layout changes explicitly.

### `extract_candidates(page, layout_variant)`

Return ordered candidate dicts. Minimum useful fields:

```python
{
    "bbox": [x0, top, x1, bottom],
    "raw_text": "verbatim row text",
    "cells": ["verbatim", "cell", "text"],
    "flags": [],
}
```

Pipeline owns provenance and candidate IDs. Keep raw values verbatim. Use `page["words"]` for generic coordinate logic or `page["pdf_page"]` for `pdfplumber` crop/table APIs during extraction only. Never retain page object.

### `normalize(candidates)`

Return:

```python
{
    "records": [
        {
            "record_id": "stable-natural-or-derived-id",
            "source_candidate_ids": ["..."],
            "fields": {"date": date(...), "amount": Decimal("12.34")},
        }
    ],
    "exceptions": [
        {
            "exception_id": "...",
            "source_candidate_ids": ["..."],
            "code": "malformed_row",
            "message": "Amount absent",
            "severity": "error"
        }
    ],
}
```

`candidates` is one-pass iterable over page shards, not full in-memory list. Stitch wrapped lines and page continuations with small pending state while ordered stream is available. Every candidate must appear exactly once in one record or one exception. Headers, footers, page labels, blanks, and explanatory prose still need documented informational exceptions.

### `validate(records, exceptions, manifest)`

Return document-specific check dicts:

```python
[{"id": "row-count", "status": "pass", "severity": "error", "message": "...", "details": {}}]
```

Checks with `status: "fail"` and `severity: "error"` block export.

## Adapter design sequence

1. Inspect representative pages and render difficult pages.
2. Identify coordinate bands and layout variants.
3. Extract candidates without semantic cleanup.
4. Flag headers, footers, continuation lines, totals, and uncertain OCR.
5. Stitch candidates deterministically.
6. Parse dates and numbers explicitly; never use binary floats for money.
7. Add invariants from document, not assumptions.
8. Test malformed and changing layouts before full extraction.

## Candidate IDs and repairs

Candidate IDs derive from immutable source evidence. Do not create them in adapter. Repairs must reference exact existing IDs. A repair may update normalized fields or turn documented exception candidates into one record when it supplies all required fields. It may not change raw text/cells or cite fabricated IDs.
