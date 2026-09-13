#!/usr/bin/env python3
"""Resumable, coordinate-preserving PDF-to-CSV refinery.

No universal PDF schema exists. Every job requires a local adapter.py.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator


PIPELINE_VERSION = "1"
SUPPORTED_FIELD_TYPES = {"string", "decimal", "integer", "date", "boolean"}
USEFUL_TEXT_THRESHOLD = 20
SCAN_IMAGE_COVERAGE_THRESHOLD = 0.50


class PipelineError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(json_safe(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def atomic_write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    lines = [json.dumps(json_safe(row), ensure_ascii=False, sort_keys=True) for row in rows]
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"expected JSON object: {path}")
    return value


def read_jsonl(path: Path, *, missing_ok: bool = False) -> list[dict[str, Any]]:
    if not path.exists():
        if missing_ok:
            return []
        raise PipelineError(f"missing required file: {path}")
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise PipelineError(f"expected object at {path}:{line_number}")
        rows.append(value)
    return rows


def require_pdf(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise PipelineError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise PipelineError(f"input must be a PDF: {path}")
    return path


def load_adapter(path: Path) -> Any:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise PipelineError(f"adapter not found: {path}")
    module_name = "pdf_data_adapter_" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    module = types.ModuleType(module_name)
    module.__file__ = str(path)
    try:
        source = path.read_text(encoding="utf-8")
        exec(compile(source, str(path), "exec"), module.__dict__)
    except (OSError, SyntaxError) as exc:
        raise PipelineError(f"cannot load adapter {path}: {exc}") from exc
    required_constants = ("ADAPTER_ID", "ADAPTER_VERSION", "FIELDS", "REQUIRED_FIELDS", "FIELD_TYPES")
    required_functions = ("classify_page", "extract_candidates", "normalize", "validate")
    missing = [name for name in required_constants + required_functions if not hasattr(module, name)]
    if missing:
        raise PipelineError(f"adapter missing: {', '.join(missing)}")
    if not str(module.ADAPTER_ID).strip() or not str(module.ADAPTER_VERSION).strip():
        raise PipelineError("adapter ID and version must be non-empty")
    fields = tuple(module.FIELDS)
    required_fields = tuple(module.REQUIRED_FIELDS)
    if not fields or len(fields) != len(set(fields)):
        raise PipelineError("adapter FIELDS must be non-empty and unique")
    if not set(required_fields).issubset(fields):
        raise PipelineError("adapter REQUIRED_FIELDS must be a subset of FIELDS")
    unknown_types = set(module.FIELD_TYPES.values()) - SUPPORTED_FIELD_TYPES
    if unknown_types or set(module.FIELD_TYPES) != set(fields):
        raise PipelineError("adapter FIELD_TYPES must declare one supported type for every field")
    return module


def adapter_identity(adapter: Any) -> dict[str, str]:
    return {"id": str(adapter.ADAPTER_ID), "version": str(adapter.ADAPTER_VERSION)}


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_job_adapter(work_dir: Path) -> Path:
    destination = work_dir / "adapter.py"
    if destination.exists():
        return destination
    source = skill_root() / "assets" / "adapter_template.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def pdf_page_count(path: Path) -> tuple[int, bool]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PipelineError("pypdf unavailable; run with bundled PDF runtime") from exc
    reader = PdfReader(str(path))
    encrypted = bool(reader.is_encrypted)
    if encrypted:
        return 0, True
    return len(reader.pages), False


def useful_characters(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def image_coverage(page: Any) -> float:
    page_area = float(page.width) * float(page.height)
    if page_area <= 0:
        return 0.0
    area = 0.0
    for image in page.images:
        x0 = max(0.0, min(float(page.width), float(image.get("x0", 0.0))))
        x1 = max(0.0, min(float(page.width), float(image.get("x1", 0.0))))
        top = max(0.0, min(float(page.height), float(image.get("top", 0.0))))
        bottom = max(0.0, min(float(page.height), float(image.get("bottom", 0.0))))
        area += max(0.0, x1 - x0) * max(0.0, bottom - top)
    return min(1.0, area / page_area)


def line_signatures(words: list[dict[str, Any]], page_height: float) -> tuple[str, str]:
    grouped: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda item: (round(float(item["top"]), 1), float(item["x0"]))):
        if not grouped or abs(float(grouped[-1][0]["top"]) - float(word["top"])) > 3:
            grouped.append([word])
        else:
            grouped[-1].append(word)
    top_lines = [line for line in grouped if min(float(word["top"]) for word in line) <= page_height * 0.15]
    bottom_lines = [line for line in grouped if max(float(word["bottom"]) for word in line) >= page_height * 0.85]

    def normalized(line: list[dict[str, Any]] | None) -> str:
        if not line:
            return ""
        text = " ".join(str(word["text"]) for word in sorted(line, key=lambda item: float(item["x0"])))
        return re.sub(r"\s+", " ", text).strip().casefold()

    return normalized(top_lines[0] if top_lines else None), normalized(bottom_lines[-1] if bottom_lines else None)


def candidate_id(source_hash: str, page_number: int, sequence: int, candidate: dict[str, Any]) -> str:
    evidence = {
        "source_sha256": source_hash,
        "page": page_number,
        "sequence": sequence,
        "bbox": candidate.get("bbox"),
        "raw_text": candidate.get("raw_text", ""),
        "cells": candidate.get("cells", []),
    }
    return "cand_" + sha256_json(evidence)[:24]


def normalize_bbox(value: Any, width: float, height: float) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise PipelineError(f"candidate bbox must have four numbers, got {value!r}")
    try:
        x0, top, x1, bottom = (float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"candidate bbox must contain numbers, got {value!r}") from exc
    if x0 < -0.5 or top < -0.5 or x1 > width + 0.5 or bottom > height + 0.5 or x1 < x0 or bottom < top:
        raise PipelineError(f"candidate bbox outside page: {value!r}")
    return [round(max(0.0, x0), 4), round(max(0.0, top), 4), round(min(width, x1), 4), round(min(height, bottom), 4)]


def enrich_candidates(
    raw_candidates: Any,
    *,
    source_hash: str,
    page_number: int,
    width: float,
    height: float,
    method: str,
    layout_variant: str,
) -> list[dict[str, Any]]:
    if raw_candidates is None:
        raw_candidates = []
    if not isinstance(raw_candidates, list):
        raise PipelineError(f"adapter extract_candidates must return list on page {page_number}")
    enriched = []
    for sequence, raw in enumerate(raw_candidates, 1):
        if not isinstance(raw, dict):
            raise PipelineError(f"candidate {sequence} on page {page_number} is not an object")
        candidate = {
            "source_sha256": source_hash,
            "page": page_number,
            "bbox": normalize_bbox(raw.get("bbox", [0, 0, width, height]), width, height),
            "sequence": sequence,
            "extraction_method": method,
            "layout_variant": str(layout_variant),
            "raw_text": str(raw.get("raw_text", "")),
            "cells": json_safe(raw.get("cells", [])),
            "flags": sorted(set(str(flag) for flag in raw.get("flags", []))),
        }
        candidate["candidate_id"] = candidate_id(source_hash, page_number, sequence, candidate)
        enriched.append(candidate)
    return enriched


def flag_low_confidence_ocr(candidates: list[dict[str, Any]], words: list[dict[str, Any]], threshold: float = 60.0) -> None:
    low_confidence = []
    for word in words:
        try:
            confidence = float(word.get("confidence", 100.0))
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence < threshold:
            low_confidence.append(word)
    for candidate in candidates:
        x0, top, x1, bottom = candidate["bbox"]
        overlaps = [
            word
            for word in low_confidence
            if float(word.get("x1", 0)) >= x0
            and float(word.get("x0", 0)) <= x1
            and float(word.get("bottom", 0)) >= top
            and float(word.get("top", 0)) <= bottom
        ]
        if overlaps:
            candidate["flags"] = sorted(set(candidate.get("flags", [])) | {"ocr_low_confidence"})


def parse_page_range(value: str | None, page_count: int) -> list[int]:
    if not value:
        return list(range(1, page_count + 1))
    selected: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if end < start:
                raise PipelineError(f"invalid page range: {part}")
            selected.update(range(start, end + 1))
        else:
            selected.add(int(part))
    if not selected or min(selected) < 1 or max(selected) > page_count:
        raise PipelineError(f"page range outside 1-{page_count}: {value}")
    return sorted(selected)


def ocr_tools() -> tuple[str | None, str | None]:
    return shutil.which("pdftoppm"), shutil.which("tesseract")


def ocr_page(
    input_pdf: Path,
    page_number: int,
    width_points: float,
    height_points: float,
    work_dir: Path,
    *,
    keep_image: bool,
) -> tuple[list[dict[str, Any]], str | None]:
    pdftoppm, tesseract = ocr_tools()
    if not pdftoppm or not tesseract:
        missing = [name for name, path in (("pdftoppm", pdftoppm), ("tesseract", tesseract)) if not path]
        return [], "ocr_unavailable:" + ",".join(missing)
    try:
        from PIL import Image
    except ImportError:
        return [], "ocr_unavailable:pillow"

    image_dir = work_dir / "page-images"
    image_dir.mkdir(parents=True, exist_ok=True)
    prefix = image_dir / f"page-{page_number:06d}"
    image_path = prefix.with_suffix(".png")
    render = subprocess.run(
        [pdftoppm, "-f", str(page_number), "-l", str(page_number), "-singlefile", "-r", "300", "-png", str(input_pdf), str(prefix)],
        capture_output=True,
        text=True,
    )
    if render.returncode != 0 or not image_path.exists():
        return [], "ocr_render_failed:" + (render.stderr.strip() or f"exit_{render.returncode}")
    try:
        with Image.open(image_path) as image:
            pixel_width, pixel_height = image.size
        result = subprocess.run(
            [tesseract, str(image_path), "stdout", "tsv"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return [], "ocr_failed:" + (result.stderr.strip() or f"exit_{result.returncode}")
        words = []
        reader = csv.DictReader(result.stdout.splitlines(), delimiter="\t")
        for row in reader:
            if row.get("level") != "5" or not (row.get("text") or "").strip():
                continue
            try:
                left = float(row["left"])
                top = float(row["top"])
                word_width = float(row["width"])
                word_height = float(row["height"])
                confidence = float(row.get("conf", "-1"))
            except (KeyError, TypeError, ValueError):
                continue
            x_scale = width_points / pixel_width
            y_scale = height_points / pixel_height
            words.append(
                {
                    "text": row["text"].strip(),
                    "x0": left * x_scale,
                    "top": top * y_scale,
                    "x1": (left + word_width) * x_scale,
                    "bottom": (top + word_height) * y_scale,
                    "confidence": confidence,
                }
            )
        return words, None
    finally:
        if not keep_image:
            image_path.unlink(missing_ok=True)
            try:
                image_dir.rmdir()
            except OSError:
                pass


def page_probe(page: Any, page_number: int) -> dict[str, Any]:
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False) or []
    text = " ".join(str(word.get("text", "")) for word in words)
    coverage = image_coverage(page)
    useful = useful_characters(text)
    return {
        "page": page_number,
        "width": float(page.width),
        "height": float(page.height),
        "embedded_useful_characters": useful,
        "image_coverage": round(coverage, 6),
        "ocr_recommended": useful < USEFUL_TEXT_THRESHOLD and coverage >= SCAN_IMAGE_COVERAGE_THRESHOLD,
    }


def manifest_source(input_pdf: Path) -> dict[str, Any]:
    return {
        "path": str(input_pdf),
        "sha256": sha256_file(input_pdf),
        "size_bytes": input_pdf.stat().st_size,
    }


def cmd_inspect(args: argparse.Namespace) -> int:
    input_pdf = require_pdf(Path(args.input_pdf))
    work_dir = Path(args.work_dir).expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    page_count, encrypted = pdf_page_count(input_pdf)
    if encrypted:
        raise PipelineError("encrypted PDF unsupported; provide authorized decrypted copy")
    adapter_path = ensure_job_adapter(work_dir)
    source = manifest_source(input_pdf)
    sample_pages = sorted({1, max(1, (page_count + 1) // 2), page_count}) if page_count else []
    probes = []
    try:
        import pdfplumber
    except ImportError as exc:
        raise PipelineError("pdfplumber unavailable; run with bundled PDF runtime") from exc
    with pdfplumber.open(str(input_pdf)) as pdf:
        for page_number in sample_pages:
            page = pdf.pages[page_number - 1]
            try:
                probes.append(page_probe(page, page_number))
            finally:
                page.close()
    probe = {
        "source": source,
        "page_count": page_count,
        "sample_pages": probes,
        "ocr_rule": {
            "useful_character_threshold": USEFUL_TEXT_THRESHOLD,
            "image_coverage_threshold": SCAN_IMAGE_COVERAGE_THRESHOLD,
        },
        "created_at": utc_now(),
    }
    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "source": source,
        "page_count": page_count,
        "adapter_path": str(adapter_path),
        "completed_pages": [],
        "page_metadata": {},
        "status": "inspected",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    atomic_write_json(work_dir / "probe.json", probe)
    atomic_write_json(work_dir / "manifest.json", manifest)
    (work_dir / "pages").mkdir(exist_ok=True)
    print(f"inspected {page_count} pages; adapter: {adapter_path}")
    return 0


def prepare_extract_manifest(
    work_dir: Path,
    input_pdf: Path,
    adapter: Any,
    *,
    resume: bool,
    page_count: int,
) -> dict[str, Any]:
    manifest_path = work_dir / "manifest.json"
    source = manifest_source(input_pdf)
    identity = adapter_identity(adapter)
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        existing_source = manifest.get("source", {})
        if existing_source.get("sha256") != source["sha256"]:
            raise PipelineError("source hash changed; stale job cannot resume")
        if int(manifest.get("page_count", -1)) != page_count:
            raise PipelineError("source page count changed; stale job cannot resume")
    else:
        manifest = {
            "pipeline_version": PIPELINE_VERSION,
            "source": source,
            "page_count": page_count,
            "completed_pages": [],
            "page_metadata": {},
            "created_at": utc_now(),
        }
    completed = set(int(page) for page in manifest.get("completed_pages", []))
    existing_identity = manifest.get("adapter")
    if completed and existing_identity != identity:
        raise PipelineError("adapter identity/version changed; stale checkpoints rejected")
    pages_dir = work_dir / "pages"
    existing_shards = list(pages_dir.glob("*.candidates.jsonl")) if pages_dir.exists() else []
    if existing_shards and not resume:
        raise PipelineError("page shards already exist; use --resume or a new work directory")
    manifest.update(
        {
            "pipeline_version": PIPELINE_VERSION,
            "source": source,
            "page_count": page_count,
            "adapter": identity,
            "adapter_path": str((work_dir / "adapter.py").resolve()),
            "completed_pages": sorted(completed),
            "page_metadata": manifest.get("page_metadata", {}),
            "status": "extracting",
            "updated_at": utc_now(),
        }
    )
    atomic_write_json(manifest_path, manifest)
    return manifest


def repeated_signatures(page_metadata: dict[str, Any], processed_pages: set[int]) -> tuple[set[str], set[str]]:
    top_pages: dict[str, set[int]] = defaultdict(set)
    bottom_pages: dict[str, set[int]] = defaultdict(set)
    for page_text, metadata in page_metadata.items():
        page_number = int(page_text)
        if page_number not in processed_pages:
            continue
        top = metadata.get("top_signature", "")
        bottom = metadata.get("bottom_signature", "")
        if top:
            top_pages[top].add(page_number)
        if bottom:
            bottom_pages[bottom].add(page_number)
    minimum = max(2, (len(processed_pages) + 1) // 2)
    return (
        {text for text, pages in top_pages.items() if len(pages) >= minimum},
        {text for text, pages in bottom_pages.items() if len(pages) >= minimum},
    )


def mark_repeated_margins(work_dir: Path, manifest: dict[str, Any]) -> None:
    processed_pages = set(int(page) for page in manifest.get("completed_pages", []))
    tops, bottoms = repeated_signatures(manifest.get("page_metadata", {}), processed_pages)
    for page_number in sorted(processed_pages):
        shard = work_dir / "pages" / f"{page_number:06d}.candidates.jsonl"
        if not shard.exists():
            continue
        rows = read_jsonl(shard)
        metadata = manifest["page_metadata"].get(str(page_number), {})
        height = float(metadata.get("height", 0.0))
        changed = False
        for row in rows:
            normalized = re.sub(r"\s+", " ", row.get("raw_text", "")).strip().casefold()
            flags = set(row.get("flags", []))
            bbox = row.get("bbox", [0, 0, 0, 0])
            if normalized in tops and float(bbox[1]) <= height * 0.15:
                flags.add("repeated_header")
            if normalized in bottoms and float(bbox[3]) >= height * 0.85:
                flags.add("repeated_footer")
            new_flags = sorted(flags)
            if new_flags != row.get("flags", []):
                row["flags"] = new_flags
                changed = True
        if changed:
            atomic_write_jsonl(shard, rows)
    manifest["repeated_margin_signatures"] = {"headers": sorted(tops), "footers": sorted(bottoms)}


def cmd_extract(args: argparse.Namespace) -> int:
    input_pdf = require_pdf(Path(args.input_pdf))
    work_dir = Path(args.work_dir).expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    adapter_path = Path(args.adapter).expanduser().resolve()
    expected_adapter = (work_dir / "adapter.py").resolve()
    if adapter_path != expected_adapter:
        raise PipelineError(f"adapter must be job-local: {expected_adapter}")
    adapter = load_adapter(adapter_path)
    page_count, encrypted = pdf_page_count(input_pdf)
    if encrypted:
        raise PipelineError("encrypted PDF unsupported; provide authorized decrypted copy")
    manifest = prepare_extract_manifest(work_dir, input_pdf, adapter, resume=args.resume, page_count=page_count)
    pages = parse_page_range(args.pages, page_count)
    completed = set(int(page) for page in manifest.get("completed_pages", []))
    pages_dir = work_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    try:
        import pdfplumber
    except ImportError as exc:
        raise PipelineError("pdfplumber unavailable; run with bundled PDF runtime") from exc

    with pdfplumber.open(str(input_pdf)) as pdf:
        for page_number in pages:
            shard = pages_dir / f"{page_number:06d}.candidates.jsonl"
            if args.resume and page_number in completed and shard.exists():
                continue
            page = pdf.pages[page_number - 1]
            try:
                embedded_words = page.extract_words(keep_blank_chars=False, use_text_flow=False) or []
                embedded_text = " ".join(str(word.get("text", "")) for word in embedded_words)
                coverage = image_coverage(page)
                useful = useful_characters(embedded_text)
                likely_scan = useful < USEFUL_TEXT_THRESHOLD and coverage >= SCAN_IMAGE_COVERAGE_THRESHOLD
                method = "embedded_text"
                words = embedded_words
                ocr_error = None
                use_ocr = args.ocr == "always" or (args.ocr == "auto" and likely_scan)
                if use_ocr:
                    words, ocr_error = ocr_page(
                        input_pdf,
                        page_number,
                        float(page.width),
                        float(page.height),
                        work_dir,
                        keep_image=args.keep_page_images,
                    )
                    method = "ocr" if not ocr_error else "ocr_unavailable"
                elif useful == 0:
                    method = "blank_vector"
                text = " ".join(str(word.get("text", "")) for word in words)
                top_signature, bottom_signature = line_signatures(words, float(page.height))
                page_context = {
                    "page_number": page_number,
                    "width": float(page.width),
                    "height": float(page.height),
                    "extraction_method": method,
                    "text": text,
                    "words": words,
                    "embedded_useful_characters": useful,
                    "image_coverage": coverage,
                    "likely_scan": likely_scan,
                    "top_signature": top_signature,
                    "bottom_signature": bottom_signature,
                    "pdf_page": page,
                }
                layout_variant = str(adapter.classify_page(page_context))
                raw_candidates = adapter.extract_candidates(page_context, layout_variant)
                if ocr_error:
                    raw_candidates = list(raw_candidates or [])
                    raw_candidates.append(
                        {
                            "bbox": [0, 0, float(page.width), float(page.height)],
                            "raw_text": "",
                            "cells": [],
                            "flags": ["ocr_unavailable", ocr_error],
                        }
                    )
                candidates = enrich_candidates(
                    raw_candidates,
                    source_hash=manifest["source"]["sha256"],
                    page_number=page_number,
                    width=float(page.width),
                    height=float(page.height),
                    method=method,
                    layout_variant=layout_variant,
                )
                if method == "ocr":
                    flag_low_confidence_ocr(candidates, words)
                atomic_write_jsonl(shard, candidates)
                completed.add(page_number)
                manifest["completed_pages"] = sorted(completed)
                manifest["page_metadata"][str(page_number)] = {
                    "width": float(page.width),
                    "height": float(page.height),
                    "layout_variant": layout_variant,
                    "extraction_method": method,
                    "embedded_useful_characters": useful,
                    "image_coverage": round(coverage, 6),
                    "candidate_count": len(candidates),
                    "top_signature": top_signature,
                    "bottom_signature": bottom_signature,
                    "ocr_error": ocr_error,
                }
                manifest["updated_at"] = utc_now()
                atomic_write_json(work_dir / "manifest.json", manifest)
            finally:
                page.close()
    mark_repeated_margins(work_dir, manifest)
    manifest["status"] = "extracted" if len(completed) == page_count else "partially_extracted"
    manifest["updated_at"] = utc_now()
    atomic_write_json(work_dir / "manifest.json", manifest)
    print(f"extracted {len(completed)}/{page_count} pages")
    return 0


def iter_candidates(work_dir: Path) -> Iterator[dict[str, Any]]:
    pages_dir = work_dir / "pages"
    if not pages_dir.is_dir():
        raise PipelineError(f"missing pages directory: {pages_dir}")
    for shard in sorted(pages_dir.glob("*.candidates.jsonl")):
        yield from read_jsonl(shard)


def validate_record_shape(record: dict[str, Any], fields: tuple[str, ...]) -> None:
    if not isinstance(record, dict):
        raise PipelineError("adapter record must be an object")
    if not str(record.get("record_id", "")).strip():
        raise PipelineError("adapter record missing record_id")
    ids = record.get("source_candidate_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(value, str) for value in ids):
        raise PipelineError(f"record {record['record_id']} needs source_candidate_ids")
    values = record.get("fields")
    if not isinstance(values, dict) or not set(values).issubset(fields):
        raise PipelineError(f"record {record['record_id']} has invalid fields")


def validate_exception_shape(exception: dict[str, Any]) -> None:
    if not isinstance(exception, dict):
        raise PipelineError("adapter exception must be an object")
    if not str(exception.get("exception_id", "")).strip():
        raise PipelineError("adapter exception missing exception_id")
    ids = exception.get("source_candidate_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(value, str) for value in ids):
        raise PipelineError(f"exception {exception['exception_id']} needs source_candidate_ids")
    if exception.get("severity") not in {"info", "warning", "error"}:
        raise PipelineError(f"exception {exception['exception_id']} has invalid severity")


def load_repairs(path: Path, candidate_ids: set[str], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    repairs = read_jsonl(path, missing_ok=True)
    seen: set[str] = set()
    for index, repair in enumerate(repairs, 1):
        ids = repair.get("source_candidate_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(value, str) for value in ids):
            raise PipelineError(f"repair {index} needs source_candidate_ids")
        unknown = set(ids) - candidate_ids
        if unknown:
            raise PipelineError(f"repair {index} references fabricated candidate IDs: {sorted(unknown)}")
        overlap = seen.intersection(ids)
        if overlap:
            raise PipelineError(f"candidate IDs repaired more than once: {sorted(overlap)}")
        seen.update(ids)
        changed = repair.get("changed_fields")
        if not isinstance(changed, dict) or not changed or not set(changed).issubset(fields):
            raise PipelineError(f"repair {index} changed_fields must use adapter FIELDS")
        if not str(repair.get("method", "")).strip():
            raise PipelineError(f"repair {index} needs method")
        try:
            confidence = float(repair.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise PipelineError(f"repair {index} needs confidence from 0 to 1") from exc
        if not 0 <= confidence <= 1:
            raise PipelineError(f"repair {index} confidence outside 0 to 1")
    return repairs


def apply_repairs(
    records: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
    repairs: list[dict[str, Any]],
    required_fields: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    for repair in repairs:
        repair_ids = set(repair["source_candidate_ids"])
        matching_records = [record for record in records if set(record["source_candidate_ids"]) == repair_ids]
        matching_exceptions = [exception for exception in exceptions if set(exception["source_candidate_ids"]) == repair_ids]
        if len(matching_records) + len(matching_exceptions) != 1:
            raise PipelineError("repair candidate IDs must exactly match one record or exception")
        if matching_records:
            record = matching_records[0]
            record["fields"].update(repair["changed_fields"])
            record["repair"] = {
                "method": repair["method"],
                "confidence": float(repair["confidence"]),
            }
        else:
            if not set(required_fields).issubset(repair["changed_fields"]):
                raise PipelineError("repairing exception into record requires all required fields")
            exception = matching_exceptions[0]
            exceptions.remove(exception)
            records.append(
                {
                    "record_id": repair.get("record_id") or "repair_" + sha256_json(sorted(repair_ids))[:20],
                    "source_candidate_ids": repair["source_candidate_ids"],
                    "fields": repair["changed_fields"],
                    "repair": {"method": repair["method"], "confidence": float(repair["confidence"])},
                }
            )
    return records, exceptions


def cmd_normalize(args: argparse.Namespace) -> int:
    work_dir = Path(args.work_dir).expanduser().resolve()
    adapter_path = Path(args.adapter).expanduser().resolve()
    expected_adapter = (work_dir / "adapter.py").resolve()
    if adapter_path != expected_adapter:
        raise PipelineError(f"adapter must be job-local: {expected_adapter}")
    adapter = load_adapter(adapter_path)
    manifest = read_json(work_dir / "manifest.json")
    if manifest.get("adapter") != adapter_identity(adapter):
        raise PipelineError("adapter identity/version differs from extraction checkpoints")
    if len(manifest.get("completed_pages", [])) != int(manifest.get("page_count", 0)):
        raise PipelineError("all pages must be extracted before normalization")
    candidate_ids: set[str | None] = set()
    candidate_count = 0
    for candidate in iter_candidates(work_dir):
        candidate_count += 1
        candidate_ids.add(candidate.get("candidate_id"))
    if None in candidate_ids or len(candidate_ids) != candidate_count:
        raise PipelineError("candidate IDs missing or duplicated")
    result = adapter.normalize(iter_candidates(work_dir))
    if not isinstance(result, dict) or not isinstance(result.get("records"), list) or not isinstance(result.get("exceptions"), list):
        raise PipelineError("adapter normalize must return records and exceptions lists")
    fields = tuple(adapter.FIELDS)
    records = result["records"]
    exceptions = result["exceptions"]
    for record in records:
        validate_record_shape(record, fields)
    for exception in exceptions:
        validate_exception_shape(exception)
    repair_path = Path(args.repairs).expanduser().resolve() if args.repairs else work_dir / "repairs.jsonl"
    if args.repairs and repair_path != work_dir / "repairs.jsonl":
        repairs = read_jsonl(repair_path)
        atomic_write_jsonl(work_dir / "repairs.jsonl", repairs)
        repair_path = work_dir / "repairs.jsonl"
    elif not repair_path.exists():
        atomic_write_jsonl(repair_path, [])
    repairs = load_repairs(repair_path, {value for value in candidate_ids if value is not None}, fields)
    records, exceptions = apply_repairs(records, exceptions, repairs, tuple(adapter.REQUIRED_FIELDS))
    for record in records:
        validate_record_shape(record, fields)
    atomic_write_jsonl(work_dir / "normalized.jsonl", [json_safe(record) for record in records])
    atomic_write_jsonl(work_dir / "exceptions.jsonl", [json_safe(exception) for exception in exceptions])
    manifest["normalization"] = {
        "candidate_count": candidate_count,
        "record_count": len(records),
        "exception_count": len(exceptions),
        "repair_count": len(repairs),
        "repairs_sha256": sha256_file(work_dir / "repairs.jsonl"),
        "adapter": adapter_identity(adapter),
        "completed_at": utc_now(),
    }
    manifest["status"] = "normalized"
    manifest["updated_at"] = utc_now()
    manifest.pop("validation", None)
    manifest.pop("export", None)
    atomic_write_json(work_dir / "manifest.json", manifest)
    print(f"normalized {len(records)} records; {len(exceptions)} exceptions")
    return 0


def check_type(value: Any, declared_type: str) -> bool:
    if value is None:
        return True
    if declared_type == "string":
        return isinstance(value, str)
    if declared_type == "decimal":
        try:
            parsed = Decimal(str(value))
            return not isinstance(value, bool) and parsed.is_finite()
        except (InvalidOperation, ValueError):
            return False
    if declared_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool) or isinstance(value, str) and bool(re.fullmatch(r"[+-]?\d+", value))
    if declared_type == "date":
        try:
            date.fromisoformat(str(value))
            return True
        except ValueError:
            return False
    if declared_type == "boolean":
        return isinstance(value, bool)
    return False


def make_check(check_id: str, passed: bool, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "pass" if passed else "fail",
        "severity": "error",
        "message": message,
        "details": details or {},
    }


def cmd_validate(args: argparse.Namespace) -> int:
    work_dir = Path(args.work_dir).expanduser().resolve()
    adapter_path = Path(args.adapter).expanduser().resolve()
    expected_adapter = (work_dir / "adapter.py").resolve()
    if adapter_path != expected_adapter:
        raise PipelineError(f"adapter must be job-local: {expected_adapter}")
    adapter = load_adapter(adapter_path)
    manifest = read_json(work_dir / "manifest.json")
    if manifest.get("adapter") != adapter_identity(adapter):
        raise PipelineError("adapter identity/version differs from extraction checkpoints")
    records = read_jsonl(work_dir / "normalized.jsonl")
    exceptions = read_jsonl(work_dir / "exceptions.jsonl")
    all_candidate_ids: set[str] = set()
    provenance_errors = []
    last_key = (0, 0)
    candidate_count = 0
    for candidate in iter_candidates(work_dir):
        candidate_count += 1
        candidate_id_value = candidate.get("candidate_id")
        if isinstance(candidate_id_value, str):
            all_candidate_ids.add(candidate_id_value)
        key = (int(candidate.get("page", 0)), int(candidate.get("sequence", 0)))
        if candidate.get("source_sha256") != manifest.get("source", {}).get("sha256") or key <= last_key:
            provenance_errors.append(candidate_id_value)
        last_key = key
    references: list[str] = []
    for record in records:
        references.extend(record.get("source_candidate_ids", []))
    for exception in exceptions:
        references.extend(exception.get("source_candidate_ids", []))
    reference_counts = Counter(references)
    missing_references = sorted(set(references) - all_candidate_ids)
    unaccounted = sorted(all_candidate_ids - set(references))
    multiply_accounted = sorted(candidate_id for candidate_id, count in reference_counts.items() if count != 1)
    checks = [
        make_check(
            "candidate-accounting",
            not missing_references and not unaccounted and not multiply_accounted,
            "Every candidate maps exactly once to a record or exception",
            {"missing_references": missing_references, "unaccounted": unaccounted, "multiply_accounted": multiply_accounted},
        )
    ]
    required = tuple(adapter.REQUIRED_FIELDS)
    missing_fields = []
    type_errors = []
    invalid_fields = []
    for record in records:
        values = record.get("fields", {})
        for field in required:
            if field not in values or values[field] in (None, ""):
                missing_fields.append({"record_id": record.get("record_id"), "field": field})
        for field in values:
            if field not in adapter.FIELDS:
                invalid_fields.append({"record_id": record.get("record_id"), "field": field})
            elif not check_type(values[field], adapter.FIELD_TYPES[field]):
                type_errors.append({"record_id": record.get("record_id"), "field": field, "value": values[field]})
    checks.append(make_check("required-fields", not missing_fields, "Required fields are present", {"errors": missing_fields}))
    checks.append(make_check("field-schema", not invalid_fields, "Record fields match adapter schema", {"errors": invalid_fields}))
    checks.append(make_check("field-types", not type_errors, "Record field types are valid", {"errors": type_errors}))
    record_ids = [record.get("record_id") for record in records]
    duplicate_record_ids = sorted(key for key, count in Counter(record_ids).items() if not key or count > 1)
    checks.append(make_check("unique-record-ids", not duplicate_record_ids, "Record IDs are non-empty and unique", {"duplicates": duplicate_record_ids}))
    if len(all_candidate_ids) != candidate_count:
        provenance_errors.append("missing_or_duplicate_candidate_id")
    checks.append(make_check("provenance-order", not provenance_errors, "Candidate source hash and page order are valid", {"errors": provenance_errors}))
    repair_error = None
    try:
        load_repairs(work_dir / "repairs.jsonl", all_candidate_ids, tuple(adapter.FIELDS))
    except PipelineError as exc:
        repair_error = str(exc)
    expected_repairs_hash = manifest.get("normalization", {}).get("repairs_sha256")
    current_repairs_hash = sha256_file(work_dir / "repairs.jsonl") if (work_dir / "repairs.jsonl").exists() else None
    checks.append(
        make_check(
            "repair-integrity",
            repair_error is None and expected_repairs_hash == current_repairs_hash,
            "Repairs are valid and unchanged since normalization",
            {"error": repair_error, "expected_sha256": expected_repairs_hash, "current_sha256": current_repairs_hash},
        )
    )
    error_exceptions = [exception.get("exception_id") for exception in exceptions if exception.get("severity") == "error"]
    checks.append(make_check("unresolved-errors", not error_exceptions, "No unresolved error exceptions remain", {"exceptions": error_exceptions}))

    adapter_checks = adapter.validate(records, exceptions, manifest)
    if not isinstance(adapter_checks, list):
        raise PipelineError("adapter validate must return a list")
    for check in adapter_checks:
        if not isinstance(check, dict) or check.get("status") not in {"pass", "fail"} or check.get("severity") not in {"info", "warning", "error"}:
            raise PipelineError("adapter validation check has invalid shape")
    all_checks = checks + adapter_checks
    failed = [check["id"] for check in all_checks if check["status"] == "fail" and check["severity"] == "error"]
    normalized_hash = sha256_file(work_dir / "normalized.jsonl")
    validation = {
        "status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "counts": {
            "candidates": candidate_count,
            "records": len(records),
            "exceptions": len(exceptions),
            "error_exceptions": len(error_exceptions),
        },
        "checks": all_checks,
        "normalized_sha256": normalized_hash,
        "adapter": adapter_identity(adapter),
        "validated_at": utc_now(),
    }
    atomic_write_json(work_dir / "validation.json", validation)
    manifest["validation"] = {
        "status": validation["status"],
        "failed_checks": failed,
        "normalized_sha256": normalized_hash,
        "completed_at": validation["validated_at"],
    }
    manifest["status"] = "validated" if not failed else "validation_failed"
    manifest["updated_at"] = utc_now()
    atomic_write_json(work_dir / "manifest.json", manifest)
    print(f"validation {validation['status']}; {len(failed)} blocking checks")
    return 0 if not failed else 1


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    try:
        shutil.copy2(source, temp_name)
        os.replace(temp_name, destination)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def cmd_export(args: argparse.Namespace) -> int:
    work_dir = Path(args.work_dir).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    adapter_path = work_dir / "adapter.py"
    adapter = load_adapter(adapter_path)
    manifest = read_json(work_dir / "manifest.json")
    validation = read_json(work_dir / "validation.json")
    normalized_path = work_dir / "normalized.jsonl"
    current_hash = sha256_file(normalized_path)
    if validation.get("normalized_sha256") != current_hash:
        raise PipelineError("normalized data changed after validation; run validate again")
    invalid = validation.get("status") != "pass"
    if invalid and not args.allow_invalid:
        raise PipelineError("validation failed; export blocked (use --allow-invalid for recorded override)")
    records = read_jsonl(normalized_path)
    artifact = work_dir / "output.csv"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".output.", suffix=".csv.tmp", dir=artifact.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(adapter.FIELDS), extrasaction="ignore")
            writer.writeheader()
            for record in records:
                writer.writerow({field: json_safe(record.get("fields", {}).get(field, "")) for field in adapter.FIELDS})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, artifact)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
    if output != artifact.resolve():
        atomic_copy(artifact, output)
    manifest["export"] = {
        "output": str(output),
        "job_output": str(artifact),
        "record_count": len(records),
        "allow_invalid": bool(args.allow_invalid),
        "validation_status": validation.get("status"),
        "failed_checks": validation.get("failed_checks", []),
        "completed_at": utc_now(),
    }
    manifest["status"] = "exported_invalid" if invalid else "exported"
    manifest["updated_at"] = utc_now()
    atomic_write_json(work_dir / "manifest.json", manifest)
    print(f"exported {len(records)} records to {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="probe PDF and create job bundle")
    inspect_parser.add_argument("input_pdf")
    inspect_parser.add_argument("--work-dir", required=True)
    inspect_parser.set_defaults(func=cmd_inspect)

    extract_parser = subparsers.add_parser("extract", help="extract atomic per-page candidate shards")
    extract_parser.add_argument("input_pdf")
    extract_parser.add_argument("--work-dir", required=True)
    extract_parser.add_argument("--adapter", required=True)
    extract_parser.add_argument("--resume", action="store_true")
    extract_parser.add_argument("--ocr", choices=("auto", "never", "always"), default="auto")
    extract_parser.add_argument("--pages", help="optional 1-based range, e.g. 1-5,9")
    extract_parser.add_argument("--keep-page-images", action="store_true")
    extract_parser.set_defaults(func=cmd_extract)

    normalize_parser = subparsers.add_parser("normalize", help="stitch and normalize candidates")
    normalize_parser.add_argument("--work-dir", required=True)
    normalize_parser.add_argument("--adapter", required=True)
    normalize_parser.add_argument("--repairs")
    normalize_parser.set_defaults(func=cmd_normalize)

    validate_parser = subparsers.add_parser("validate", help="run generic and adapter checks")
    validate_parser.add_argument("--work-dir", required=True)
    validate_parser.add_argument("--adapter", required=True)
    validate_parser.set_defaults(func=cmd_validate)

    export_parser = subparsers.add_parser("export", help="write validated CSV")
    export_parser.add_argument("--work-dir", required=True)
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--allow-invalid", action="store_true")
    export_parser.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
