from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


SKILL_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = SKILL_ROOT / "scripts" / "pdf_data_pipeline.py"
SPEC = importlib.util.spec_from_file_location("pdf_data_pipeline_for_tests", PIPELINE_PATH)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


SYNTHETIC_ADAPTER = '''
from datetime import date
from decimal import Decimal
from hashlib import sha256

ADAPTER_ID = "synthetic-records"
ADAPTER_VERSION = "1"
FIELDS = ("date", "description", "amount")
REQUIRED_FIELDS = FIELDS
FIELD_TYPES = {"date": "date", "description": "string", "amount": "decimal"}

def classify_page(page):
    return "alternate" if "ALT LAYOUT" in page.get("text", "") else "default"

def extract_candidates(page, layout_variant):
    del layout_variant
    lines = []
    for word in sorted(page.get("words", []), key=lambda item: (round(float(item["top"]), 1), float(item["x0"]))):
        if not lines or abs(float(lines[-1][0]["top"]) - float(word["top"])) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)
    output = []
    for line in lines:
        line.sort(key=lambda item: float(item["x0"]))
        output.append({
            "bbox": [min(item["x0"] for item in line), min(item["top"] for item in line), max(item["x1"] for item in line), max(item["bottom"] for item in line)],
            "raw_text": " ".join(item["text"] for item in line),
            "cells": [item["text"] for item in line],
            "flags": [],
        })
    return output

def _exception(candidate, code, severity):
    return {
        "exception_id": code + "-" + candidate["candidate_id"][-12:],
        "source_candidate_ids": [candidate["candidate_id"]],
        "code": code,
        "message": code.replace("_", " "),
        "severity": severity,
    }

def normalize(candidates):
    records = []
    exceptions = []
    for candidate in candidates:
        raw = candidate["raw_text"].strip()
        if raw.startswith("HEADER"):
            exceptions.append(_exception(candidate, "repeated_header", "info"))
        elif raw.startswith("FOOTER"):
            exceptions.append(_exception(candidate, "repeated_footer", "info"))
        elif raw == "ALT LAYOUT":
            exceptions.append(_exception(candidate, "layout_marker", "info"))
        elif raw.startswith("ROW|"):
            parts = raw.split("|", 3)
            if len(parts) != 4:
                exceptions.append(_exception(candidate, "malformed_row", "error"))
                continue
            _, date_text, description, amount_text = parts
            records.append({
                "record_id": "row-" + sha256(candidate["candidate_id"].encode()).hexdigest()[:16],
                "source_candidate_ids": [candidate["candidate_id"]],
                "fields": {"date": date.fromisoformat(date_text), "description": description, "amount": Decimal(amount_text)},
            })
        elif raw.startswith("CONT|") and records:
            records[-1]["source_candidate_ids"].append(candidate["candidate_id"])
            records[-1]["fields"]["description"] += " " + raw.split("|", 1)[1]
        elif raw.startswith("MALFORMED"):
            exceptions.append(_exception(candidate, "malformed_row", "error"))
        elif raw:
            exceptions.append(_exception(candidate, "non_record", "info"))
        else:
            exceptions.append(_exception(candidate, "blank", "info"))
    return {"records": records, "exceptions": exceptions}

def validate(records, exceptions, manifest):
    del exceptions, manifest
    return [{
        "id": "synthetic-records",
        "status": "pass" if records else "fail",
        "severity": "error",
        "message": "Synthetic records exist",
        "details": {"count": len(records)},
    }]
'''


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_pdf(self, path: Path, pages: list[list[tuple[float, str]]]) -> None:
        pdf = canvas.Canvas(str(path), pagesize=letter)
        for lines in pages:
            for y, text in lines:
                pdf.drawString(36, y, text)
            pdf.showPage()
        pdf.save()

    def inspect_and_install_adapter(self, pdf: Path, work: Path) -> Path:
        self.assertEqual(pipeline.main(["inspect", str(pdf), "--work-dir", str(work)]), 0)
        adapter = work / "adapter.py"
        adapter.write_text(SYNTHETIC_ADAPTER, encoding="utf-8")
        return adapter

    def test_digital_refinery_repair_validation_and_export(self):
        pdf = self.root / "mixed-layout.pdf"
        work = self.root / "job"
        output = self.root / "records.csv"
        self.make_pdf(
            pdf,
            [
                [
                    (760, "HEADER COMMON"),
                    (700, "ROW|2024-01-01|first|10.25"),
                    (650, "ROW|2024-01-02|wrapped|-2.50"),
                    (25, "FOOTER COMMON"),
                ],
                [
                    (760, "HEADER COMMON"),
                    (720, "CONT|across page"),
                    (680, "ALT LAYOUT"),
                    (620, "ROW|2024-01-03|third|7.00"),
                    (560, "MALFORMED missing fields"),
                    (25, "FOOTER COMMON"),
                ],
            ],
        )
        adapter = self.inspect_and_install_adapter(pdf, work)
        self.assertEqual(
            pipeline.main(["extract", str(pdf), "--work-dir", str(work), "--adapter", str(adapter), "--resume", "--ocr", "auto"]),
            0,
        )
        manifest = json.loads((work / "manifest.json").read_text())
        self.assertEqual(manifest["page_metadata"]["2"]["layout_variant"], "alternate")
        page_one = pipeline.read_jsonl(work / "pages" / "000001.candidates.jsonl")
        self.assertIn("repeated_header", page_one[0]["flags"])
        self.assertIn("repeated_footer", page_one[-1]["flags"])
        self.assertEqual(pipeline.main(["normalize", "--work-dir", str(work), "--adapter", str(adapter)]), 0)
        records = pipeline.read_jsonl(work / "normalized.jsonl")
        self.assertEqual(records[1]["fields"]["description"], "wrapped across page")
        self.assertEqual(records[0]["fields"]["amount"], "10.25")
        self.assertEqual(pipeline.main(["validate", "--work-dir", str(work), "--adapter", str(adapter)]), 1)
        self.assertEqual(pipeline.main(["export", "--work-dir", str(work), "--output", str(output)]), 2)
        self.assertEqual(
            pipeline.main(["export", "--work-dir", str(work), "--output", str(output), "--allow-invalid"]),
            0,
        )
        invalid_manifest = json.loads((work / "manifest.json").read_text())
        self.assertTrue(invalid_manifest["export"]["allow_invalid"])

        malformed = next(item for item in pipeline.read_jsonl(work / "exceptions.jsonl") if item["code"] == "malformed_row")
        bogus = {
            "source_candidate_ids": ["cand_fabricated"],
            "changed_fields": {"date": "2024-01-04", "description": "repaired", "amount": "1.25"},
            "method": "human_review",
            "confidence": 1.0,
        }
        pipeline.atomic_write_jsonl(work / "repairs.jsonl", [bogus])
        self.assertEqual(pipeline.main(["normalize", "--work-dir", str(work), "--adapter", str(adapter)]), 2)

        repair = dict(bogus)
        repair["source_candidate_ids"] = malformed["source_candidate_ids"]
        pipeline.atomic_write_jsonl(work / "repairs.jsonl", [repair])
        self.assertEqual(pipeline.main(["normalize", "--work-dir", str(work), "--adapter", str(adapter)]), 0)
        self.assertEqual(pipeline.main(["validate", "--work-dir", str(work), "--adapter", str(adapter)]), 0)
        self.assertEqual(pipeline.main(["export", "--work-dir", str(work), "--output", str(output)]), 0)
        self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 5)
        self.assertEqual(output.read_bytes(), (work / "output.csv").read_bytes())

    def test_page_shards_resume_idempotence_and_stale_hash_rejection(self):
        pdf = self.root / "large.pdf"
        work = self.root / "large-job"
        self.make_pdf(
            pdf,
            [[(760, "HEADER COMMON"), (700, f"ROW|2024-01-{page:02d}|page {page}|{page}.00"), (25, "FOOTER COMMON")] for page in range(1, 26)],
        )
        adapter = self.inspect_and_install_adapter(pdf, work)
        first = ["extract", str(pdf), "--work-dir", str(work), "--adapter", str(adapter), "--pages", "1-5", "--ocr", "never"]
        self.assertEqual(pipeline.main(first), 0)
        self.assertEqual(len(list((work / "pages").glob("*.candidates.jsonl"))), 5)
        self.assertEqual(
            pipeline.main(["extract", str(pdf), "--work-dir", str(work), "--adapter", str(adapter), "--resume", "--ocr", "never"]),
            0,
        )
        shards = sorted((work / "pages").glob("*.candidates.jsonl"))
        self.assertEqual(len(shards), 25)
        mtimes = {path.name: path.stat().st_mtime_ns for path in shards}
        self.assertEqual(
            pipeline.main(["extract", str(pdf), "--work-dir", str(work), "--adapter", str(adapter), "--resume", "--ocr", "never"]),
            0,
        )
        self.assertEqual(mtimes, {path.name: path.stat().st_mtime_ns for path in shards})

        self.make_pdf(pdf, [[(700, "ROW|2024-02-01|changed|1.00")], [(700, "ROW|2024-02-02|extra|2.00")]])
        self.assertEqual(
            pipeline.main(["extract", str(pdf), "--work-dir", str(work), "--adapter", str(adapter), "--resume", "--ocr", "never"]),
            2,
        )

    def test_adapter_version_change_rejects_resume(self):
        pdf = self.root / "version.pdf"
        work = self.root / "version-job"
        self.make_pdf(pdf, [[(700, "ROW|2024-01-01|one|1.00")], [(700, "ROW|2024-01-02|two|2.00")]])
        adapter = self.inspect_and_install_adapter(pdf, work)
        self.assertEqual(
            pipeline.main(["extract", str(pdf), "--work-dir", str(work), "--adapter", str(adapter), "--pages", "1", "--ocr", "never"]),
            0,
        )
        adapter.write_text(SYNTHETIC_ADAPTER.replace('ADAPTER_VERSION = "1"', 'ADAPTER_VERSION = "2"'), encoding="utf-8")
        self.assertEqual(
            pipeline.main(["extract", str(pdf), "--work-dir", str(work), "--adapter", str(adapter), "--resume", "--ocr", "never"]),
            2,
        )

    def test_image_only_page_triggers_ocr_and_preserves_point_coordinates(self):
        if not all(pipeline.ocr_tools()):
            self.skipTest("Poppler or Tesseract unavailable")
        png = self.root / "scan.png"
        image = Image.new("RGB", (1275, 1650), "white")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 60)
        except OSError:
            font = ImageFont.load_default()
        draw.text((120, 300), "SCAN ROW 2024", fill="black", font=font)
        image.save(png)
        pdf = self.root / "scan.pdf"
        out = canvas.Canvas(str(pdf), pagesize=letter)
        out.drawImage(ImageReader(str(png)), 0, 0, width=letter[0], height=letter[1])
        out.showPage()
        out.save()
        work = self.root / "scan-job"
        adapter = self.inspect_and_install_adapter(pdf, work)
        probe = json.loads((work / "probe.json").read_text())
        self.assertTrue(probe["sample_pages"][0]["ocr_recommended"])
        self.assertEqual(
            pipeline.main(["extract", str(pdf), "--work-dir", str(work), "--adapter", str(adapter), "--resume", "--ocr", "auto"]),
            0,
        )
        manifest = json.loads((work / "manifest.json").read_text())
        self.assertEqual(manifest["page_metadata"]["1"]["extraction_method"], "ocr")
        candidates = pipeline.read_jsonl(work / "pages" / "000001.candidates.jsonl")
        self.assertTrue(candidates)
        self.assertTrue(any("SCAN" in candidate["raw_text"].upper() for candidate in candidates))
        for candidate in candidates:
            x0, top, x1, bottom = candidate["bbox"]
            self.assertTrue(0 <= x0 <= x1 <= letter[0])
            self.assertTrue(0 <= top <= bottom <= letter[1])
        self.assertFalse((work / "page-images").exists())

    def test_ocr_unavailable_and_low_confidence_flags_are_explicit(self):
        with mock.patch.object(pipeline.shutil, "which", return_value=None):
            words, error = pipeline.ocr_page(
                self.root / "missing.pdf", 1, letter[0], letter[1], self.root / "job", keep_image=False
            )
        self.assertEqual(words, [])
        self.assertEqual(error, "ocr_unavailable:pdftoppm,tesseract")
        candidates = [{"bbox": [0, 0, 100, 100], "flags": []}]
        words = [{"x0": 10, "top": 10, "x1": 30, "bottom": 20, "confidence": 42}]
        pipeline.flag_low_confidence_ocr(candidates, words)
        self.assertIn("ocr_low_confidence", candidates[0]["flags"])


if __name__ == "__main__":
    unittest.main()
