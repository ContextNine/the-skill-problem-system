"""Job-local adapter template for pdf_data_pipeline.py.

Replace placeholder schema and functions for one document family. Keep raw
candidate evidence unchanged. Increment ADAPTER_VERSION after every behavior
change so stale page checkpoints cannot resume.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Iterable


ADAPTER_ID = "replace-with-document-family"
ADAPTER_VERSION = "1"
FIELDS = ("date", "description", "amount")
REQUIRED_FIELDS = ("date", "description", "amount")
FIELD_TYPES = {
    "date": "date",
    "description": "string",
    "amount": "decimal",
}


def classify_page(page: dict[str, Any]) -> str:
    """Return stable layout label using page text, words, and dimensions."""
    text = page.get("text", "")
    if "REPLACE_WITH_LAYOUT_MARKER" in text:
        return "alternate"
    return "default"


def extract_candidates(page: dict[str, Any], layout_variant: str) -> list[dict[str, Any]]:
    """Extract coordinate-aware raw rows without semantic cleanup.

    Placeholder groups words into visual lines. Replace with document-specific
    crops, column bands, or pdfplumber table settings when needed.
    """
    del layout_variant
    lines: list[list[dict[str, Any]]] = []
    for word in sorted(page.get("words", []), key=lambda item: (round(item["top"], 1), item["x0"])):
        if not lines or abs(lines[-1][0]["top"] - word["top"]) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)

    candidates = []
    for line in lines:
        line.sort(key=lambda item: item["x0"])
        candidates.append(
            {
                "bbox": [
                    min(word["x0"] for word in line),
                    min(word["top"] for word in line),
                    max(word["x1"] for word in line),
                    max(word["bottom"] for word in line),
                ],
                "raw_text": " ".join(word["text"] for word in line),
                "cells": [],
                "flags": [],
            }
        )
    return candidates


def parse_decimal(value: str) -> Decimal:
    cleaned = value.strip().replace(",", "").replace(" ", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal: {value!r}") from exc


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value.strip())


def normalize(candidates: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Convert candidates to records and documented exceptions.

    Replace this placeholder. It intentionally emits exceptions rather than
    guessing a schema from arbitrary lines.
    """
    exceptions = []
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        exceptions.append(
            {
                "exception_id": "placeholder-" + sha256(candidate_id.encode()).hexdigest()[:16],
                "source_candidate_ids": [candidate_id],
                "code": "adapter_not_implemented",
                "message": "Replace adapter normalize() for this document family",
                "severity": "error",
            }
        )
    return {"records": [], "exceptions": exceptions}


def validate(
    records: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return document-specific invariants after generic validation."""
    del records, exceptions, manifest
    return [
        {
            "id": "adapter-implemented",
            "status": "fail",
            "severity": "error",
            "message": "Replace placeholder adapter before extraction",
            "details": {},
        }
    ]
