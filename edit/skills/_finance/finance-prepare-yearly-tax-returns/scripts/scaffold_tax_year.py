#!/usr/bin/env python3
"""Safely scaffold a Vault yearly tax-control note without overwriting evidence."""

from __future__ import annotations

import argparse
import calendar
from datetime import date, timedelta
from pathlib import Path


def last_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def clamp_date(year: int, month: int, day: int | None) -> date:
    return date(year, month, min(day or calendar.monthrange(year, month)[1], calendar.monthrange(year, month)[1]))


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return clamp_date(year, month, day.day)


def render(
    year: int,
    taxpayer: str,
    kind: str,
    year_end_month: int | None = None,
    year_end_day: int | None = None,
) -> str:
    if kind == "individual":
        year_end = month_end(year, 2)
    else:
        if year_end_month is None:
            raise ValueError("company scaffolds require --year-end-month")
        year_end = clamp_date(year, year_end_month, year_end_day)
    previous_year_end = clamp_date(year - 1, year_end.month, year_end.day)
    period_start = previous_year_end + timedelta(days=1)
    itr14_due = clamp_date(year + 1, year_end.month, year_end.day)
    first_due = last_weekday(add_months(period_start, 6) - timedelta(days=1))
    second_due = last_weekday(year_end)
    returns = ["IRP6", "ITR12" if kind == "individual" else "ITR14"]
    annual = (
        "Confirm the ITR12 filing-season deadline with SARS."
        if kind == "individual"
        else f"ITR14 is due within 12 months after year end, by {itr14_due.isoformat()}."
    )
    return f"""---
tax_year: {year}
taxpayer: {taxpayer}
return_types:
  - {returns[0]}
  - {returns[1]}
status: scaffold
last_reconciled:
---

## Period and required returns

- Period: {period_start.strftime('%-d %B %Y')} to {year_end.strftime('%-d %B %Y')}.
- IRP6 period 1 is normally due {first_due.isoformat()}; confirm public-holiday treatment with SARS.
- IRP6 period 2 is normally due {second_due.isoformat()}; confirm public-holiday treatment with SARS.
- {annual}

## Source coverage

- Statements:
- Invoices and income certificates:
- Expenses and deductions:
- Prior returns, payments, and assessments:

## Working figures

- Gross income:
- Exclusions and non-income credits:
- Supported deductions:
- Taxable income:
- Tax, credits, and provisional payment:

## Filing status and proof

- IRP6 period 1:
- IRP6 period 2:
- {returns[1]}:

## Open items

- Reconcile all source gaps and classifications.
- Verify current SARS rules and dates before capture.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", required=True, type=Path)
    parser.add_argument("--context", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--taxpayer", required=True)
    parser.add_argument("--kind", required=True, choices=("individual", "company"))
    parser.add_argument("--year-end-month", type=int, choices=range(1, 13))
    parser.add_argument("--year-end-day", type=int, choices=range(1, 32))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not 2000 <= args.year <= 2200:
        parser.error("year must be between 2000 and 2200")
    finance = args.vault_root.resolve() / args.context / "_finance"
    if not (finance / "AGENTS.md").is_file():
        parser.error(f"missing finance instructions: {finance / 'AGENTS.md'}")
    target = finance / "0_Yearly_Returns" / f"{args.year}.md"
    if target.exists():
        print(f"EXISTS {target}")
        return 0
    if args.kind == "company" and args.year_end_month is None:
        parser.error("company scaffolds require --year-end-month from the entity's finance AGENTS.md")
    body = render(
        args.year,
        args.taxpayer,
        args.kind,
        args.year_end_month,
        args.year_end_day,
    )
    if args.dry_run:
        print(f"WOULD CREATE {target}\n\n{body}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    print(f"CREATED {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
