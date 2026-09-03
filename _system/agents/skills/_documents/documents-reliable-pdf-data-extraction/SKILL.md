---
name: documents-reliable-pdf-data-extraction
description: Extract large or complex PDFs into validated structured data with page-streaming, coordinate provenance, resumable shards, OCR fallback, bounded repairs, and auditable CSV export. Invoke explicitly for transactional documents, statements, registers, reports, or other PDFs where accuracy and completeness matter.
---

# Documents · Reliable PDF Data Extraction

Use this skill when structured data must be complete, traceable, and validated—not merely copied from PDF text.

Keep provider `pdf:pdf` for general PDF reading/rendering. Use this skill for data pipelines.

## Workflow

1. Read [workflow](references/WORKFLOW.md), [adapter contract](references/ADAPTERS.md), and [validation contract](references/VALIDATION.md).
2. Create isolated work directory. Never modify source PDF.
3. Run inspection:

   ```bash
   python scripts/pdf_data_pipeline.py inspect INPUT.pdf --work-dir WORK
   ```

4. Edit generated `WORK/adapter.py` for document schema and layouts. Do not proceed with placeholder adapter.
5. Test extraction on representative pages: first, middle, last, every layout variant, and known difficult pages.
6. Run page-streaming extraction, normalization, validation, then export:

   ```bash
   python scripts/pdf_data_pipeline.py extract INPUT.pdf --work-dir WORK --adapter WORK/adapter.py --resume --ocr auto
   python scripts/pdf_data_pipeline.py normalize --work-dir WORK --adapter WORK/adapter.py
   python scripts/pdf_data_pipeline.py validate --work-dir WORK --adapter WORK/adapter.py
   python scripts/pdf_data_pipeline.py export --work-dir WORK --output OUTPUT.csv
   ```

7. Review `exceptions.jsonl` and `validation.json`. Repair only bounded unresolved candidates. Preserve raw extraction.
8. Re-run normalize, validate, and export after every adapter or repair change.

## Hard rules

- Process one page at a time. Never concatenate full PDF text or send whole document to LLM.
- Preserve source hash, page, bounding box, sequence, extraction method, raw cells/text, flags, and candidate ID.
- Prefer embedded text. OCR only clearly scanned pages unless user explicitly overrides.
- Missing OCR dependencies produce `ocr_unavailable`; never silently omit likely scanned content.
- Use `Decimal` for numbers and ISO dates in canonical records.
- Every candidate must map to exactly one output record or documented exception.
- Never invent missing values. Codex repairs require exact candidate IDs, small context, method, and confidence.
- Normal export stays blocked while validation fails. `--allow-invalid` is explicit, recorded override.

## Resources

- Pipeline: `scripts/pdf_data_pipeline.py`
- Adapter template: `assets/adapter_template.py`
- Synthetic tests: `tests/test_pdf_data_pipeline.py`
