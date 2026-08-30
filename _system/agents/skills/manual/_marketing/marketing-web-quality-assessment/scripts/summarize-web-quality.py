#!/usr/bin/env python3
"""Summarize Lighthouse CLI or PageSpeed Insights JSON as Markdown."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LAB_METRICS = (
    ("First Contentful Paint", "first-contentful-paint"),
    ("Largest Contentful Paint", "largest-contentful-paint"),
    ("Total Blocking Time", "total-blocking-time"),
    ("Cumulative Layout Shift", "cumulative-layout-shift"),
    ("Speed Index", "speed-index"),
)

FIELD_METRICS = (
    ("Largest Contentful Paint", "LARGEST_CONTENTFUL_PAINT_MS"),
    ("Interaction to Next Paint", "INTERACTION_TO_NEXT_PAINT"),
    ("Cumulative Layout Shift", "CUMULATIVE_LAYOUT_SHIFT_SCORE"),
    ("First Contentful Paint", "FIRST_CONTENTFUL_PAINT_MS"),
    ("Time to First Byte", "EXPERIMENTAL_TIME_TO_FIRST_BYTE"),
)


def escape(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def percent(value: Any) -> str:
    return "—" if not isinstance(value, (int, float)) else f"{round(value * 100)}"


def summarize(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    lighthouse = payload.get("lighthouseResult", payload)
    categories = lighthouse.get("categories", {})
    audits = lighthouse.get("audits", {})

    print(f"## {escape(path.name)}")
    print()
    print(f"- Requested URL: {escape(lighthouse.get('requestedUrl') or payload.get('id'))}")
    print(f"- Final URL: {escape(lighthouse.get('finalDisplayedUrl') or lighthouse.get('finalUrl'))}")
    print(f"- Fetch time: {escape(lighthouse.get('fetchTime') or payload.get('analysisUTCTimestamp'))}")
    print(f"- Lighthouse: {escape(lighthouse.get('lighthouseVersion'))}")
    print()
    print("### Category scores")
    print()
    print("| Category | Score / 100 |")
    print("|---|---:|")
    for key in ("performance", "accessibility", "best-practices", "seo"):
        item = categories.get(key, {})
        print(f"| {escape(item.get('title') or key)} | {percent(item.get('score'))} |")

    print()
    print("### Lab metrics")
    print()
    print("| Metric | Value | Score / 100 |")
    print("|---|---:|---:|")
    for label, key in LAB_METRICS:
        audit = audits.get(key, {})
        print(f"| {label} | {escape(audit.get('displayValue'))} | {percent(audit.get('score'))} |")

    field = payload.get("loadingExperience", {}).get("metrics", {})
    if field:
        print()
        print("### URL-level CrUX field data")
        print()
        print("| Metric | 75th percentile (API units) | Category |")
        print("|---|---:|---|")
        for label, key in FIELD_METRICS:
            metric = field.get(key)
            if metric:
                print(f"| {label} | {escape(metric.get('percentile'))} | {escape(metric.get('category'))} |")

    opportunities = []
    for audit in audits.values():
        details = audit.get("details") or {}
        savings = details.get("overallSavingsMs") or 0
        if audit.get("score") not in (None, 1) and (savings or details.get("type") == "opportunity"):
            opportunities.append((float(savings), audit.get("title"), audit.get("displayValue")))
    if opportunities:
        print()
        print("### Largest lab opportunities")
        print()
        print("| Audit | Display value | Estimated savings |")
        print("|---|---:|---:|")
        for savings, title, display in sorted(opportunities, reverse=True)[:10]:
            print(f"| {escape(title)} | {escape(display)} | {round(savings)} ms |")
    warnings = lighthouse.get("runWarnings") or []
    if warnings:
        print()
        print("### Run warnings")
        for warning in warnings:
            print(f"- {escape(warning)}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="Lighthouse or PSI JSON reports")
    args = parser.parse_args()
    print("# Web Quality Measurement Summary\n")
    for report in args.reports:
        try:
            summarize(report)
        except (OSError, json.JSONDecodeError, TypeError) as error:
            raise SystemExit(f"Failed to summarize {report}: {error}") from error


if __name__ == "__main__":
    main()
