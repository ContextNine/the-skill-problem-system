#!/usr/bin/env python3
"""Build canonical financial ledgers and update linked workbook safely."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


PIPELINE_VERSION = "1.1.0"
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
VAULT_ROOT = SKILL_DIR.parents[4]
DEFAULT_CONFIG = VAULT_ROOT / "_system/agents/_package/instance/skills/config/spreadsheets-update-financial-model-from-statements/private/workflow.json"

PERSONAL_SCHEMA = {
    "date", "description", "category", "money_in", "money_out", "fee",
    "net_amount", "balance", "status", "tax_year", "calendar_month",
    "source_page", "source_candidate_ids",
}
BUSINESS_SCHEMA = {
    "date", "description", "amount", "amount_direction", "signed_amount",
    "balance", "balance_direction", "accrued_bank_charges",
}

LEDGER_FIELDS = [
    "transaction_id", "entity", "account_id", "source_path", "source_sha256",
    "source_row", "source_page", "source_candidate_ids", "transaction_date",
    "statement_month", "tax_year", "currency", "description_raw",
    "description_normalized", "principal_amount", "fee_amount", "net_amount",
    "balance", "direction", "flow_type", "category_id", "model_category",
    "model_amount", "reportable", "transfer_group_id", "recurring_key",
    "recurring_status", "rule_id", "classification_confidence",
    "classification_reason", "status",
]


@dataclass(frozen=True)
class Category:
    category_id: str
    entity: str
    parent_id: str
    label: str
    model_category: str
    flow_type: str
    reportable: str
    active: str = "Yes"
    sort_order: int = 0
    forecastable: str = "Yes"


def D(value: Any, default: str = "0") -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal(default)
    try:
        return Decimal(str(value).replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal: {value!r}") from exc


def money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def month_start(value: str | date) -> str:
    if isinstance(value, date):
        return value.replace(day=1).isoformat()
    return f"{value[:7]}-01"


def tax_year(value: str) -> int:
    d = date.fromisoformat(value)
    return d.year + 1 if d.month >= 3 else d.year


def add_months(value: str, count: int) -> str:
    d = date.fromisoformat(month_start(value))
    idx = d.year * 12 + d.month - 1 + count
    return date(idx // 12, idx % 12 + 1, 1).isoformat()


def months_between(start: str, end: str) -> list[str]:
    result: list[str] = []
    current = month_start(start)
    end = month_start(end)
    while current <= end:
        result.append(current)
        current = add_months(current, 1)
    return result


def normalize_description(value: str) -> str:
    s = value.lower().replace("&", " and ")
    s = re.sub(r"\(card\s+\d+\)", " ", s)
    s = re.sub(r"\b\d{6,}\b", " ", s)
    s = re.sub(r"\*+\d+", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def merchant_key(value: str) -> str:
    s = value.lower()
    prefixes = [
        r"^recurring card purchase:\s*", r"^online purchase:\s*",
        r"^purchase refund:\s*", r"^banking app external payshap payment:\s*",
        r"^banking app external payment:\s*", r"^payment received:\s*",
        r"^payshap payment received:\s*", r"^swift payment received:\s*",
        r"^pos purchase\s+(?:\d+(?:\.\d+)?\s+)?",
        r"^credit voucher vouch\s+", r"^refund chq card purchase cr vc\s+",
    ]
    for prefix in prefixes:
        s = re.sub(prefix, "", s)
    s = re.sub(r"\(card\s+\d+\)", " ", s)
    s = re.sub(r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", " ", s)
    s = re.sub(r"\b(?:payment|transfer)\s+\d{7,}\b", " ", s)
    s = re.sub(r"\b\d{6,}\b", " ", s)
    s = re.sub(r"\*+\d+", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    words = [w for w in s.split() if not re.fullmatch(r"\d+(?:\.\d+)?", w)]
    return " ".join(words[:8])


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    os.close(fd)
    try:
        with open(tmp_name, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    os.close(fd)
    try:
        with open(tmp_name, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def category_seed() -> list[Category]:
    rows = [
        Category("business.receipt.customer_revenue", "Business", "business.receipts", "Customer revenue", "Customer revenue", "Receipt", "Yes", sort_order=10),
        Category("business.receipt.other_operating_income", "Business", "business.receipts", "Other operating income", "Other operating income", "Receipt", "Yes", sort_order=20),
        Category("business.receipt.capital_contribution", "Business", "business.receipts", "Funding / capital contributions", "Funding / capital contributions", "Receipt", "Yes", sort_order=30, forecastable="No"),
        Category("business.receipt.loans_received", "Business", "business.receipts", "Loans received", "Loans received", "Receipt", "Yes", sort_order=40, forecastable="No"),
        Category("business.opex.accounting_professional", "Business", "business.opex", "Accounting & professional", "Accounting & professional", "Operating Expense", "Yes", sort_order=50),
        Category("business.opex.bank_charges", "Business", "business.opex", "Bank charges", "Bank charges", "Operating Expense", "Yes", sort_order=60),
        Category("business.opex.software_saas", "Business", "business.opex", "Software & SaaS", "Software & SaaS", "Operating Expense", "Yes", sort_order=70),
        Category("business.opex.marketing_advertising", "Business", "business.opex", "Marketing & advertising", "Marketing & advertising", "Operating Expense", "Yes", sort_order=80),
        Category("business.opex.contractors_staff", "Business", "business.opex", "Contractors & staff", "Contractors & staff", "Operating Expense", "Yes", sort_order=90),
        Category("business.owner.owner_pay", "Business", "business.owner", "Owner pay / draw", "Owner pay / draw", "Owner Pay", "Yes", sort_order=100, forecastable="No"),
        Category("business.opex.office_admin", "Business", "business.opex", "Office & admin", "Office & admin", "Operating Expense", "Yes", sort_order=110),
        Category("business.opex.computer_small_assets", "Business", "business.opex", "Computer & small assets", "Computer & small assets", "Operating Expense", "Yes", sort_order=120),
        Category("business.opex.mobile_internet", "Business", "business.opex", "Mobile & internet", "Mobile & internet", "Operating Expense", "Yes", sort_order=130),
        Category("business.opex.training_networking", "Business", "business.opex", "Training & networking", "Training & networking", "Operating Expense", "Yes", sort_order=140),
        Category("business.opex.entertainment", "Business", "business.opex", "Entertainment", "Entertainment", "Operating Expense", "Yes", sort_order=150),
        Category("business.opex.interest_finance", "Business", "business.opex", "Interest & finance costs", "Interest & finance costs", "Operating Expense", "Yes", sort_order=160),
        Category("business.opex.compliance", "Business", "business.opex", "CIPC & compliance", "CIPC & compliance", "Operating Expense", "Yes", sort_order=170),
        Category("business.opex.other", "Business", "business.opex", "Other operating expenses", "Other operating expenses", "Operating Expense", "Yes", sort_order=180, forecastable="No"),
        Category("business.adjustment.refund_unmatched", "Business", "business.adjustments", "Unmatched refund adjustment", "Other operating expenses", "Operating Expense", "Yes", sort_order=185, forecastable="No"),
        Category("business.tax.tax_vat", "Business", "business.tax", "Tax / VAT reserve", "Tax / VAT reserve", "Tax", "Yes", sort_order=190),
        Category("business.capital.capex", "Business", "business.capital", "Capital expenditure", "Capital expenditure", "Capital", "Yes", sort_order=200),
        Category("business.financing.loan_repayments", "Business", "business.financing", "Loan repayments", "Loan repayments", "Financing", "Yes", sort_order=210),
        Category("business.financing.other", "Business", "business.financing", "Other financing", "Other financing", "Financing", "Yes", sort_order=220),
        Category("business.transfer.internal", "Business", "business.transfer", "Internal transfer", "", "Transfer", "No", sort_order=230, forecastable="No"),
        Category("personal.income.salary_owner_pay", "Personal", "personal.income", "Salary / wages", "Salary / wages", "Income", "Yes", sort_order=310),
        Category("personal.income.tax_refund", "Personal", "personal.income", "Tax refunds", "Tax refunds", "Income", "Yes", sort_order=315, forecastable="No"),
        Category("personal.income.gifts_support", "Personal", "personal.income", "Gifts and support received", "Gifts and support received", "Income", "Yes", sort_order=316, forecastable="No"),
        Category("personal.income.sale_proceeds", "Personal", "personal.income", "Marketplace / asset-sale proceeds", "Marketplace / asset-sale proceeds", "Income", "Yes", sort_order=317, forecastable="No"),
        Category("personal.income.unidentified_receipt", "Personal", "personal.income", "Unidentified receipts", "Unidentified receipts", "Income", "Yes", sort_order=318, forecastable="No"),
        Category("personal.income.other", "Personal", "personal.income", "Other income", "Other income", "Income", "Yes", sort_order=320, forecastable="No"),
        Category("personal.income.interest_investment", "Personal", "personal.income", "Interest & investment income", "Interest & investment income", "Income", "Yes", sort_order=330),
        Category("personal.expense.housing", "Personal", "personal.expense", "Housing", "Housing", "Expense", "Yes", sort_order=340),
        Category("personal.expense.utilities_connectivity", "Personal", "personal.expense", "Utilities & connectivity", "Utilities & connectivity", "Expense", "Yes", sort_order=350),
        Category("personal.expense.groceries_household", "Personal", "personal.expense", "Groceries & household supplies", "Groceries & household supplies", "Expense", "Yes", sort_order=360),
        Category("personal.expense.dining_takeaways", "Personal", "personal.expense", "Dining & takeaways", "Dining & takeaways", "Expense", "Yes", sort_order=370),
        Category("personal.expense.home_domestic", "Personal", "personal.expense", "Home & domestic", "Home & domestic", "Expense", "Yes", sort_order=380),
        Category("personal.expense.fuel", "Personal", "personal.expense", "Fuel", "Fuel", "Expense", "Yes", sort_order=390),
        Category("personal.expense.public_transport", "Personal", "personal.expense", "Public transport & rides", "Public transport & rides", "Expense", "Yes", sort_order=400),
        Category("personal.expense.vehicle", "Personal", "personal.expense", "Vehicle costs", "Vehicle costs", "Expense", "Yes", sort_order=410),
        Category("personal.expense.health_insurance", "Personal", "personal.expense", "Health insurance", "Health insurance", "Expense", "Yes", sort_order=420),
        Category("personal.expense.medical_pharmacy", "Personal", "personal.expense", "Medical & pharmacy", "Medical & pharmacy", "Expense", "Yes", sort_order=430),
        Category("personal.expense.fitness_sport", "Personal", "personal.expense", "Fitness & sport", "Fitness & sport", "Expense", "Yes", sort_order=440),
        Category("personal.expense.insurance", "Personal", "personal.expense", "Insurance", "Insurance", "Expense", "Yes", sort_order=450),
        Category("personal.expense.clothing_personal_care", "Personal", "personal.expense", "Clothing & personal care", "Clothing & personal care", "Expense", "Yes", sort_order=460),
        Category("personal.expense.entertainment_recreation", "Personal", "personal.expense", "Entertainment & recreation", "Entertainment & recreation", "Expense", "Yes", sort_order=470),
        Category("personal.expense.travel_holidays", "Personal", "personal.expense", "Travel & holidays", "Travel & holidays", "Expense", "Yes", sort_order=480),
        Category("personal.expense.subscriptions_software", "Personal", "personal.expense", "Subscriptions & software", "Subscriptions & software", "Expense", "Yes", sort_order=490),
        Category("personal.expense.education", "Personal", "personal.expense", "Education", "Education", "Expense", "Yes", sort_order=500),
        Category("personal.expense.family_gifts_dependants", "Personal", "personal.expense", "Family, gifts & dependants", "Family, gifts & dependants", "Expense", "Yes", sort_order=510),
        Category("personal.expense.bank_fees", "Personal", "personal.expense", "Bank fees", "Bank fees", "Expense", "Yes", sort_order=520),
        Category("personal.expense.tax", "Personal", "personal.expense", "Tax", "Tax", "Expense", "Yes", sort_order=530, forecastable="No"),
        Category("personal.expense.online_shopping", "Personal", "personal.expense", "Online shopping and goods", "Online shopping and goods", "Expense", "Yes", sort_order=535),
        Category("personal.expense.cash_withdrawal", "Personal", "personal.expense", "Cash withdrawals", "Cash withdrawals", "Expense", "Yes", sort_order=536, forecastable="No"),
        Category("personal.expense.unidentified_person_payment", "Personal", "personal.expense", "Unidentified person payments", "Unidentified person payments", "Expense", "Yes", sort_order=537, forecastable="No"),
        Category("personal.expense.unidentified_oneoff", "Personal", "personal.expense", "Unidentified one-off expenses", "Unidentified one-off expenses", "Expense", "Yes", sort_order=538, forecastable="No"),
        Category("personal.expense.other", "Personal", "personal.expense", "Other expenses", "Other expenses", "Expense", "Yes", sort_order=540, forecastable="No"),
        Category("personal.adjustment.refund_unmatched", "Personal", "personal.adjustments", "Unmatched refund adjustments", "Unmatched refund adjustments", "Expense", "Yes", sort_order=545, forecastable="No"),
        Category("personal.transfer.internal", "Personal", "personal.transfer", "Internal transfer", "", "Transfer", "No", sort_order=550, forecastable="No"),
        Category("personal.transfer.savings_investments", "Personal", "personal.transfer", "Savings & investments", "", "Asset Movement", "No", sort_order=560, forecastable="No"),
        Category("personal.transfer.business_capital", "Personal", "personal.transfer", "Business capital contribution", "", "Asset Movement", "No", sort_order=570, forecastable="No"),
        Category("personal.transfer.owner_pay_receipt", "Personal", "personal.transfer", "Linked business owner pay", "", "Transfer", "No", sort_order=580, forecastable="No"),
    ]
    return rows


def alias_seed() -> list[dict[str, str]]:
    mapping = {
        "Groceries": "personal.expense.groceries_household",
        "Restaurants": "personal.expense.dining_takeaways",
        "Takeaways": "personal.expense.dining_takeaways",
        "Alcohol": "personal.expense.dining_takeaways",
        "Going Out": "personal.expense.entertainment_recreation",
        "Clothing & Shoes": "personal.expense.clothing_personal_care",
        "Personal Care": "personal.expense.clothing_personal_care",
        "Toiletries & cleaning": "personal.expense.groceries_household",
        "Laundry": "personal.expense.home_domestic",
        "Parking": "personal.expense.vehicle",
        "Fuel": "personal.expense.fuel",
        "Public Transport": "personal.expense.public_transport",
        "Other Transport": "personal.expense.public_transport",
        "Tolls": "personal.expense.vehicle",
        "Licence": "personal.expense.vehicle",
        "Vehicle Payments": "personal.expense.vehicle",
        "Car Maintenance": "personal.expense.vehicle",
        "Other Personal & Family": "personal.expense.family_gifts_dependants",
        "Children & Dependants": "personal.expense.family_gifts_dependants",
        "Allowance": "personal.expense.family_gifts_dependants",
        "Other Income": "personal.income.unidentified_receipt",
        "Interest": "personal.income.interest_investment",
        "Internet": "personal.expense.utilities_connectivity",
        "WiFi & internet": "personal.expense.utilities_connectivity",
        "Phone": "personal.expense.utilities_connectivity",
        "Electricity": "personal.expense.utilities_connectivity",
        "Software /Games": "personal.expense.subscriptions_software",
        "/Games": "personal.expense.subscriptions_software",
        "Digital Subscriptions": "personal.expense.subscriptions_software",
        "Holiday": "personal.expense.travel_holidays",
        "Other Entertainment": "personal.expense.entertainment_recreation",
        "Movies": "personal.expense.entertainment_recreation",
        "Activities": "personal.expense.entertainment_recreation",
        "Sport & Hobbies": "personal.expense.fitness_sport",
        "Home Maintenance": "personal.expense.home_domestic",
        "Housekeeping": "personal.expense.home_domestic",
        "Other Household": "personal.expense.home_domestic",
        "Furniture & Appliances": "personal.expense.home_domestic",
        "Fees": "personal.expense.bank_fees",
        "Doctors & Therapists": "personal.expense.medical_pharmacy",
        "Pharmacy": "personal.expense.medical_pharmacy",
        "Other Insurance": "personal.expense.insurance",
        "Tax": "personal.expense.tax",
        "Education": "personal.expense.education",
        "Pension": "personal.income.salary_owner_pay",
        "Transfer": "personal.transfer.internal",
        "Investments": "personal.transfer.savings_investments",
        "Cash Deposit": "personal.income.unidentified_receipt",
        "Online Store": "personal.expense.online_shopping",
        "Digital Payments": "personal.expense.unidentified_oneoff",
        "Other expenses": "personal.expense.unidentified_oneoff",
        "Uncategorised": "personal.expense.unidentified_oneoff",
        "": "personal.expense.unidentified_oneoff",
    }
    rows = []
    for source, category_id in mapping.items():
        confidence = "0.86"
        if source in {"Uncategorised", "", "Online Store", "Digital Payments", "Cash Deposit"}:
            confidence = "0.65"
        rows.append({"entity": "Personal", "source_label": source, "category_id": category_id, "confidence": confidence, "active": "Yes"})
    return rows


def default_instance_config() -> dict[str, Any]:
    if not DEFAULT_CONFIG.is_file():
        return {}
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def rule_seed(pattern_overrides: dict[str, str] | None = None) -> list[dict[str, str]]:
    patterns = pattern_overrides if pattern_overrides is not None else default_instance_config().get("rule_patterns", {})
    rules: list[tuple[str, str, int, str, str, str, str]] = [
        ("business_owner_credit", "Business", 5, "regex", patterns.get("business_owner_credit", r"$^"), "business.receipt.capital_contribution", "0.99"),
        ("business_owner_debit", "Business", 5, "regex", patterns.get("business_owner_debit", r"$^"), "business.owner.owner_pay", "0.99"),
        ("business_capital_matt", "Business", 10, "regex", r"(?:magtape|payshap) credit .*matt deposit", "business.receipt.capital_contribution", "0.99"),
        ("business_customer_lemon", "Business", 20, "contains", "lemon squeezy", "business.receipt.customer_revenue", "0.99"),
        ("business_bank_fees", "Business", 20, "regex", r"#(?:service fees|monthly account fee)|electronic payments bis/int", "business.opex.bank_charges", "0.99"),
        ("business_tax_sars", "Business", 20, "contains", "payment to sars", "business.tax.tax_vat", "0.99"),
        ("business_cipc", "Business", 20, "contains", "cipc", "business.opex.compliance", "0.99"),
        ("business_financing_transfer", "Business", 20, "contains", "payoff dr transfer", "business.financing.other", "0.98"),
        ("business_marketing_ads", "Business", 30, "regex", r"google \*?ads|facebook ads|meta ads", "business.opex.marketing_advertising", "0.96"),
        ("business_computer_assets", "Business", 40, "regex", r"temu|takealot|apple\.com/us", "business.opex.computer_small_assets", "0.86"),
        ("business_afrihost_internet", "Business", 35, "contains", "afrihost", "business.opex.mobile_internet", "0.98"),
        ("business_software", "Business", 50, "regex", r"dataimpulse|google (?:gsuite|worksp|cloud)|econseo|cursor|adobe|oxylabs|moonshot|anthropic|midjourney|spaceship\.com|kilo code|openrouter|freepik|medium monthly|multilogin|gettoby|claude\.ai|hetzner|polar\*|dynadot|openai|xneelo|elevenlabs|cloudflare|copyblogger|web operations|windscribe|buypersona|paddle\.net|illustrator", "business.opex.software_saas", "0.96"),
        ("personal_notice_transfer", "Personal", 10, "contains", "notice transfer received", "personal.transfer.internal", "0.99"),
        ("personal_32day_transfer", "Personal", 10, "contains", "transfer to 32day", "personal.transfer.savings_investments", "0.99"),
        ("personal_salary_wages", "Personal", 15, "regex", r"soulv software|pilot platform", "personal.income.salary_owner_pay", "0.99"),
        ("personal_sars_refund", "Personal", 15, "regex", r"\bsars\b", "personal.income.tax_refund", "0.99"),
        ("personal_csfloat_sale", "Personal", 15, "contains", "csfloat", "personal.income.sale_proceeds", "0.98"),
        ("personal_shyft_movement", "Personal", 15, "contains", "shyft", "personal.transfer.savings_investments", "0.99"),
        ("personal_atm_cash", "Personal", 15, "regex", r"atm (?:cash withdrawal|correction)", "personal.expense.cash_withdrawal", "0.99"),
        ("personal_interest", "Personal", 20, "contains", "interest received", "personal.income.interest_investment", "0.99"),
        ("personal_bank_fees", "Personal", 20, "regex", r"service fee|monthly account fee|bank charges", "personal.expense.bank_fees", "0.98"),
        ("personal_subscriptions", "Personal", 40, "regex", r"apple\.com itunes|spotify|netflix|youtube|google one|adobe|icloud|webflow|bright data|dynadot", "personal.expense.subscriptions_software", "0.94"),
        ("personal_connectivity", "Personal", 40, "regex", r"afrihost", "personal.expense.utilities_connectivity", "0.96"),
        ("personal_booking_travel", "Personal", 35, "regex", r"booking\.com|bkg\*hotel|taxis on booking", "personal.expense.travel_holidays", "0.97"),
        ("personal_marketplace_goods", "Personal", 35, "regex", r"\bebay\b|shopee|taobao|takealot|temu", "personal.expense.online_shopping", "0.94"),
        ("personal_wild_leather", "Personal", 35, "contains", "wild leather", "personal.expense.clothing_personal_care", "0.98"),
        ("personal_skynet_review", "Personal", 35, "contains", "skynet", "personal.expense.unidentified_oneoff", "0.95"),
        ("personal_fitness", "Personal", 45, "regex", r"\bgym\b|rbsi gym", "personal.expense.fitness_sport", "0.94"),
        ("personal_care", "Personal", 45, "regex", r"\bbarber\b", "personal.expense.clothing_personal_care", "0.94"),
        ("personal_groceries", "Personal", 50, "regex", r"pick n pay|checkers|shoprite|woolworths|food lovers|spar ", "personal.expense.groceries_household", "0.94"),
        ("personal_takeaways", "Personal", 50, "regex", r"uber eats|mr d|dineplan|restaurant|coffee|cafe|hussar|bootlegger", "personal.expense.dining_takeaways", "0.92"),
        ("personal_fuel", "Personal", 50, "regex", r"engen|shell |bp |caltex|totalenergies", "personal.expense.fuel", "0.92"),
        ("personal_vehicle", "Personal", 40, "regex", r"parking|panelbeater|auto enterprises|suspension city|toll", "personal.expense.vehicle", "0.94"),
        ("personal_family_outgoing", "Personal", 60, "regex", patterns.get("personal_family_outgoing", r"$^"), "personal.expense.family_gifts_dependants", "0.95"),
        ("personal_family_incoming", "Personal", 60, "regex", patterns.get("personal_family_incoming", r"$^"), "personal.income.gifts_support", "0.95"),
        ("personal_home", "Personal", 60, "regex", r"pinepine furniture", "personal.expense.home_domestic", "0.90"),
        ("personal_opaque_person_payment", "Personal", 90, "regex", r"banking app external (?:payshap )?payment:|immediate capitec pay payment:", "personal.expense.unidentified_person_payment", "0.82"),
    ]
    now = "2026-07-15"
    output = []
    directions = {
        "business_owner_credit": "credit", "business_owner_debit": "debit",
        "personal_sars_refund": "credit", "personal_family_incoming": "credit",
        "personal_family_outgoing": "debit", "personal_opaque_person_payment": "debit",
    }
    for rule_id, entity, priority, match_type, pattern, category_id, confidence in rules:
        output.append({
            "rule_id": rule_id, "entity": entity, "priority": str(priority),
            "match_type": match_type, "pattern": pattern, "category_id": category_id,
            "direction": directions.get(rule_id, ""), "reportable": "", "confidence": confidence, "active": "Yes",
            "created_at": now, "updated_at": now, "evidence_count": "0",
            "notes": "Seeded from initial statement review",
        })
    return output


def ensure_reference_files(data_root: Path, config: dict[str, Any] | None = None) -> None:
    config = config or default_instance_config()
    taxonomy = data_root / "taxonomy" / "categories.csv"
    aliases = data_root / "taxonomy" / "aliases.csv"
    rules = data_root / "rules" / "category_rules.csv"
    overrides = data_root / "rules" / "transaction_overrides.csv"
    recurring = data_root / "rules" / "recurring_rules.csv"
    commitments = data_root / "rules" / "recurring_commitments.csv"
    if not taxonomy.exists():
        write_csv(taxonomy, ["category_id", "entity", "parent_id", "label", "model_category", "flow_type", "reportable", "active", "sort_order", "forecastable"], [c.__dict__ for c in category_seed()])
    if not aliases.exists():
        write_csv(aliases, ["entity", "source_label", "category_id", "confidence", "active"], alias_seed())
    if not rules.exists():
        write_csv(rules, ["rule_id", "entity", "priority", "match_type", "pattern", "category_id", "direction", "reportable", "confidence", "active", "created_at", "updated_at", "evidence_count", "notes"], rule_seed(config.get("rule_patterns")))
    if not overrides.exists():
        write_csv(overrides, ["transaction_id", "category_id", "reportable", "confidence", "reason", "active"], [])
    if not recurring.exists():
        write_csv(recurring, ["match_key", "entity", "category_id", "frequency", "amount", "start_month", "end_month", "active", "source"], [])
    if not commitments.exists():
        write_csv(commitments, ["commitment_id", "entity", "flow_type", "item", "category", "amount", "frequency", "start_month", "end_month", "annual_escalation", "active", "notes"], [])

    # Schema/content migrations are idempotent. Stable seed IDs update; user-added rows survive.
    category_fields = ["category_id", "entity", "parent_id", "label", "model_category", "flow_type", "reportable", "active", "sort_order", "forecastable"]
    existing_categories = {r["category_id"]: r for r in read_csv(taxonomy)}
    for seeded in category_seed():
        existing_categories[seeded.category_id] = {field: getattr(seeded, field) for field in category_fields}
    write_csv(taxonomy, category_fields, sorted(existing_categories.values(), key=lambda r: int(r.get("sort_order") or 0)))

    alias_fields = ["entity", "source_label", "category_id", "confidence", "active"]
    existing_aliases = {(r["entity"], r["source_label"]): r for r in read_csv(aliases)}
    for seeded in alias_seed():
        existing_aliases[(seeded["entity"], seeded["source_label"])] = seeded
    write_csv(aliases, alias_fields, existing_aliases.values())

    rule_fields = ["rule_id", "entity", "priority", "match_type", "pattern", "category_id", "direction", "reportable", "confidence", "active", "created_at", "updated_at", "evidence_count", "notes"]
    existing_rules = {r["rule_id"]: r for r in read_csv(rules)}
    for seeded in rule_seed(config.get("rule_patterns")):
        existing_rules[seeded["rule_id"]] = seeded
    write_csv(rules, rule_fields, sorted(existing_rules.values(), key=lambda r: (int(r.get("priority") or 999), r["rule_id"])))

    override_fields = ["transaction_id", "category_id", "reportable", "confidence", "reason", "active"]
    override_rows = read_csv(overrides)
    for row in override_rows:
        if row.get("category_id") in {"personal.income.other", "personal.expense.other"} and D(row.get("confidence") or "1") < Decimal("0.80"):
            row["active"] = "No"
            row["reason"] = f"{row.get('reason', '')}; superseded by taxonomy/rules v1.1".strip("; ")
    write_csv(overrides, override_fields, override_rows)

    recurring_rows = config.get("recurring_seed", [])
    recurring_by_key = {(r["match_key"], r["entity"]): r for r in read_csv(recurring)}
    for row in recurring_rows:
        recurring_by_key[(row["match_key"], row["entity"])] = row
    write_csv(recurring, ["match_key", "entity", "category_id", "frequency", "amount", "start_month", "end_month", "active", "source"], recurring_by_key.values())

    commitment_rows = config.get("commitment_seed", [])
    commitments_by_id = {r["commitment_id"]: r for r in read_csv(commitments)}
    for row in commitment_rows:
        commitments_by_id[row["commitment_id"]] = row
    write_csv(commitments, ["commitment_id", "entity", "flow_type", "item", "category", "amount", "frequency", "start_month", "end_month", "annual_escalation", "active", "notes"], commitments_by_id.values())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_categories(data_root: Path) -> dict[str, Category]:
    result = {}
    for row in read_csv(data_root / "taxonomy" / "categories.csv"):
        result[row["category_id"]] = Category(
            row["category_id"], row["entity"], row["parent_id"], row["label"],
            row["model_category"], row["flow_type"], row["reportable"],
            row.get("active", "Yes"), int(row.get("sort_order") or 0),
            row.get("forecastable", "Yes"),
        )
    return result


def load_aliases(data_root: Path) -> dict[str, tuple[str, Decimal]]:
    return {
        row["source_label"]: (row["category_id"], D(row["confidence"]))
        for row in read_csv(data_root / "taxonomy" / "aliases.csv")
        if row.get("active", "Yes") == "Yes"
    }


def load_rules(data_root: Path) -> list[dict[str, str]]:
    rows = [r for r in read_csv(data_root / "rules" / "category_rules.csv") if r.get("active", "Yes") == "Yes"]
    return sorted(rows, key=lambda r: (int(r.get("priority") or 999), r["rule_id"]))


def load_overrides(data_root: Path) -> dict[str, dict[str, str]]:
    return {
        row["transaction_id"]: row
        for row in read_csv(data_root / "rules" / "transaction_overrides.csv")
        if row.get("active", "Yes") == "Yes"
    }


def load_recurring_rules(data_root: Path) -> list[dict[str, str]]:
    return [r for r in read_csv(data_root / "rules" / "recurring_rules.csv") if r.get("active", "Yes") == "Yes" and r.get("match_key")]


def recurring_rule_matches(tx: dict[str, Any], recurring: dict[str, str]) -> bool:
    in_window = (
        (not recurring.get("start_month") or tx["statement_month"] >= month_start(recurring["start_month"]))
        and (not recurring.get("end_month") or tx["statement_month"] <= month_start(recurring["end_month"]))
    )
    return recurring["entity"] == tx["entity"] and in_window and recurring["match_key"].lower() in tx["description_normalized"]


def category_result(category_id: str, categories: dict[str, Category], confidence: Decimal, reason: str, rule_id: str) -> dict[str, Any]:
    cat = categories[category_id]
    return {
        "category_id": category_id,
        "flow_type": cat.flow_type,
        "model_category": cat.model_category,
        "reportable": cat.reportable,
        "classification_confidence": f"{confidence:.2f}",
        "classification_reason": reason,
        "rule_id": rule_id,
    }


def signed_model_amount(principal: Decimal, flow_type: str, reportable: str) -> Decimal:
    if reportable != "Yes":
        return Decimal("0")
    return principal if flow_type in {"Income", "Receipt"} else -principal


def apply_rule(tx: dict[str, Any], rules: list[dict[str, str]], categories: dict[str, Category]) -> dict[str, Any] | None:
    raw = tx["description_raw"].lower()
    normalized = tx["description_normalized"]
    for rule in rules:
        if rule["entity"] != tx["entity"]:
            continue
        if rule.get("direction") and rule["direction"] != tx.get("direction"):
            continue
        pattern = rule["pattern"].lower()
        match_type = rule["match_type"]
        matched = False
        if match_type == "exact":
            matched = normalized == pattern
        elif match_type == "contains":
            matched = pattern in raw
        elif match_type == "regex":
            matched = re.search(rule["pattern"], raw, flags=re.I) is not None
        if matched:
            result = category_result(rule["category_id"], categories, D(rule["confidence"]), "merchant rule", rule["rule_id"])
            if rule.get("reportable"):
                result["reportable"] = rule["reportable"]
            return result
    return None


def classify(tx: dict[str, Any], categories: dict[str, Category], aliases: dict[str, tuple[str, Decimal]], rules: list[dict[str, str]], overrides: dict[str, dict[str, str]]) -> dict[str, Any]:
    if tx["transaction_id"] in overrides:
        row = overrides[tx["transaction_id"]]
        result = category_result(row["category_id"], categories, D(row["confidence"]), row.get("reason") or "transaction override", f"override:{tx['transaction_id']}")
        if row.get("reportable"):
            result["reportable"] = row["reportable"]
        return result

    raw = tx["description_raw"].lower()
    if tx["entity"] == "Personal":
        if "transfer to 32day" in raw:
            return category_result("personal.transfer.savings_investments", categories, Decimal("0.99"), "own savings transfer", "transfer:savings")
        if "notice transfer received" in raw:
            return category_result("personal.transfer.internal", categories, Decimal("0.99"), "own-account transfer", "transfer:internal")
    else:
        if "payoff dr transfer" in raw:
            return category_result("business.financing.other", categories, Decimal("0.98"), "cash transfer classified outside operating spend", "transfer:business_financing")

    matched = apply_rule(tx, rules, categories)
    if matched:
        return matched

    if tx["entity"] == "Personal" and tx.get("legacy_category") in aliases:
        category_id, confidence = aliases[tx.get("legacy_category", "")]
        return category_result(category_id, categories, confidence, f"legacy category hint: {tx.get('legacy_category') or 'blank'}", f"alias:{tx.get('legacy_category') or 'blank'}")

    principal = D(tx["principal_amount"])
    if tx["entity"] == "Personal":
        category_id = "personal.income.unidentified_receipt" if principal > 0 else "personal.expense.unidentified_oneoff"
    else:
        category_id = "business.receipt.other_operating_income" if principal > 0 else "business.opex.other"
    return category_result(category_id, categories, Decimal("0.60"), "conservative fallback", "agent:fallback")


def is_refund(tx: dict[str, Any]) -> bool:
    raw = tx["description_raw"].lower()
    return "refund" in raw or "credit voucher" in raw or tx.get("legacy_category") == "Refunds"


def validate_source_rollforward(entity: str, rows: list[dict[str, str]], source: str) -> list[dict[str, Any]]:
    failures = []
    previous_balance: Decimal | None = None
    for idx, row in enumerate(rows, 2):
        balance_raw = row.get("balance", "").strip()
        if not balance_raw:
            previous_balance = None
            continue
        balance = D(balance_raw)
        if entity == "Business" and row.get("balance_direction", "Cr").lower() == "dr":
            balance = -balance
        movement = D(row.get("net_amount") if entity == "Personal" else row.get("signed_amount"))
        if previous_balance is not None and abs((previous_balance + movement) - balance) > Decimal("0.01"):
            failures.append({
                "source": source, "row": idx, "code": "balance_rollforward",
                "expected": money(previous_balance + movement), "actual": money(balance),
            })
        previous_balance = balance
    return failures


def discover_and_normalize(config: dict[str, Any], data_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cutoff = config["cutoff_date"]
    through = config.get("through_date", "9999-12-31")
    manifests: list[dict[str, Any]] = []
    transactions: list[dict[str, Any]] = []
    validation_failures: list[dict[str, Any]] = []
    personal_roots = config.get("personal_source_dirs") or [config["personal_source_dir"]]
    business_roots = config.get("business_source_dirs") or [config["business_source_dir"]]
    source_specs = [
        *(("Personal", Path(root)) for root in personal_roots),
        *(("Business", Path(root)) for root in business_roots),
    ]
    for entity, root in source_specs:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            suffix = path.suffix.lower()
            if suffix not in {".csv", ".pdf"}:
                continue
            source_hash = sha256_file(path)
            if suffix == ".pdf":
                manifests.append({
                    "entity": entity, "source_path": str(path), "source_sha256": source_hash,
                    "source_type": "pdf", "schema": "transaction_pdf", "row_count": "",
                    "included_rows": "", "period_start": "", "period_end": "",
                    "validation_status": "available_not_used_initial",
                    "validation_level": "future_page_streaming_required",
                })
                continue
            rows = read_csv(path)
            headers = set(rows[0].keys()) if rows else set()
            expected = PERSONAL_SCHEMA if entity == "Personal" else BUSINESS_SCHEMA
            if rows and not expected.issubset(headers):
                manifests.append({
                    "entity": entity, "source_path": str(path), "source_sha256": source_hash,
                    "source_type": "csv", "schema": "unknown", "row_count": str(len(rows)),
                    "included_rows": "0", "period_start": "", "period_end": "",
                    "validation_status": "blocked_unknown_schema", "validation_level": "none",
                })
                validation_failures.append({"source": str(path), "code": "unknown_schema", "headers": sorted(headers)})
                continue
            validation_failures.extend(validate_source_rollforward(entity, rows, str(path)))
            included = [r for r in rows if cutoff <= r.get("date", "") <= through]
            dates = [r.get("date", "") for r in rows if r.get("date")]
            manifests.append({
                "entity": entity, "source_path": str(path), "source_sha256": source_hash,
                "source_type": "csv", "schema": "personal_v1" if entity == "Personal" else "business_v1",
                "row_count": str(len(rows)), "included_rows": str(len(included)),
                "period_start": min(dates) if dates else "", "period_end": max(dates) if dates else "",
                "validation_status": "pass" if not any(f.get("source") == str(path) for f in validation_failures) else "fail",
                "validation_level": "candidate_provenance_and_balance" if entity == "Personal" else "csv_internal_balance",
            })
            for source_row, row in enumerate(rows, 2):
                tx_date = row.get("date", "")
                if tx_date < cutoff or tx_date > through:
                    continue
                if entity == "Personal":
                    principal = D(row.get("money_in")) + D(row.get("money_out"))
                    fee = D(row.get("fee"))
                    net = D(row.get("net_amount"))
                    balance = D(row.get("balance"))
                    account_id = config.get("account_ids", {}).get("personal", "personal-primary")
                    legacy = row.get("category", "")
                    page = row.get("source_page", "")
                    candidates = row.get("source_candidate_ids", "")
                    status = row.get("status", "posted")
                else:
                    principal = D(row.get("signed_amount"))
                    fee = Decimal("0")
                    net = principal
                    balance = D(row.get("balance"))
                    if row.get("balance_direction", "Cr").lower() == "dr":
                        balance = -balance
                    account_id = config.get("account_ids", {}).get("business", "business-primary")
                    legacy = ""
                    page = ""
                    candidates = ""
                    status = "posted"
                tx_id = sha256_text("|".join([entity, source_hash, str(source_row), tx_date, row.get("description", ""), money(net)]))[:32]
                transactions.append({
                    "transaction_id": tx_id, "entity": entity, "account_id": account_id,
                    "source_path": str(path), "source_sha256": source_hash,
                    "source_row": str(source_row), "source_page": page,
                    "source_candidate_ids": candidates, "transaction_date": tx_date,
                    "statement_month": month_start(tx_date), "tax_year": str(tax_year(tx_date)),
                    "currency": config.get("currency", "ZAR"),
                    "description_raw": row.get("description", ""),
                    "description_normalized": merchant_key(row.get("description", "")),
                    "principal_amount": money(principal), "fee_amount": money(fee),
                    "net_amount": money(net), "balance": money(balance),
                    "direction": "credit" if principal > 0 else "debit" if principal < 0 else "zero",
                    "legacy_category": legacy, "status": status,
                })
    return transactions, manifests, validation_failures


def classify_transactions(transactions: list[dict[str, Any]], data_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    categories = load_categories(data_root)
    aliases = load_aliases(data_root)
    rules = load_rules(data_root)
    overrides = load_overrides(data_root)
    recurring_rules = load_recurring_rules(data_root)
    sorted_txs = sorted(transactions, key=lambda t: (t["transaction_date"], t["entity"], t["source_path"], int(t["source_row"])))
    history: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    new_overrides: list[dict[str, str]] = []

    for tx in sorted_txs:
        if tx["transaction_id"] in overrides:
            result = classify(tx, categories, aliases, rules, overrides)
        elif is_refund(tx):
            candidates = history.get((tx["entity"], tx["description_normalized"]), [])
            prior = next((p for p in reversed(candidates) if D(p["model_amount"]) > 0 and p["flow_type"] in {"Expense", "Operating Expense"}), None)
            if prior:
                result = category_result(prior["category_id"], categories, Decimal("0.96"), f"refund matched to {prior['transaction_id']}", f"refund:{prior['transaction_id']}")
            else:
                result = apply_rule(tx, rules, categories)
                if result is None:
                    fallback = "personal.adjustment.refund_unmatched" if tx["entity"] == "Personal" else "business.adjustment.refund_unmatched"
                    result = category_result(fallback, categories, Decimal("0.72"), "unmatched refund adjustment", "agent:refund_unmatched")
        else:
            result = classify(tx, categories, aliases, rules, overrides)
        tx.update(result)

        principal = D(tx["principal_amount"])
        tx["model_amount"] = money(signed_model_amount(principal, tx["flow_type"], tx["reportable"]))

        tx["transfer_group_id"] = ""
        tx["recurring_key"] = ""
        tx["recurring_status"] = "Variable"
        for recurring in recurring_rules:
            if recurring_rule_matches(tx, recurring):
                tx["recurring_key"] = recurring["match_key"]
                tx["recurring_status"] = "Recurring"
                break

        confidence = D(tx["classification_confidence"])
        if confidence < Decimal("0.80") and tx["transaction_id"] not in overrides:
            tx["rule_id"] = f"override:{tx['transaction_id']}"
            new_overrides.append({
                "transaction_id": tx["transaction_id"], "category_id": tx["category_id"],
                "reportable": tx["reportable"], "confidence": tx["classification_confidence"],
                "reason": tx["classification_reason"], "active": "Yes",
            })
        history[(tx["entity"], tx["description_normalized"])].append(tx)

    pair_inter_entity_transfers(sorted_txs, categories)
    pair_atm_corrections(sorted_txs, categories)
    if new_overrides:
        combined = list(overrides.values()) + new_overrides
        combined.sort(key=lambda r: r["transaction_id"])
        write_csv(data_root / "rules" / "transaction_overrides.csv", ["transaction_id", "category_id", "reportable", "confidence", "reason", "active"], combined)
    for tx in sorted_txs:
        tx.pop("legacy_category", None)
    return sorted_txs, new_overrides


def pair_inter_entity_transfers(transactions: list[dict[str, Any]], categories: dict[str, Category]) -> None:
    personal = [t for t in transactions if t["entity"] == "Personal"]
    for business in [t for t in transactions if t["entity"] == "Business"]:
        if business["category_id"] not in {"business.receipt.capital_contribution", "business.owner.owner_pay"}:
            continue
        amount = abs(D(business["principal_amount"]))
        bdate = date.fromisoformat(business["transaction_date"])
        candidates = []
        for p in personal:
            pdate = date.fromisoformat(p["transaction_date"])
            if abs((pdate - bdate).days) <= 3 and abs(abs(D(p["principal_amount"])) - amount) <= Decimal("0.01"):
                if business["category_id"] == "business.receipt.capital_contribution" and D(p["principal_amount"]) < 0:
                    candidates.append(p)
                if business["category_id"] == "business.owner.owner_pay" and D(p["principal_amount"]) > 0:
                    candidates.append(p)
        if len(candidates) == 1:
            p = candidates[0]
            group = sha256_text(f"transfer|{business['transaction_id']}|{p['transaction_id']}")[:20]
            business["transfer_group_id"] = group
            p["transfer_group_id"] = group
            target = "personal.transfer.business_capital" if business["category_id"] == "business.receipt.capital_contribution" else "personal.transfer.owner_pay_receipt"
            result = category_result(target, categories, Decimal("0.99"), "paired business/personal transfer", f"transfer_pair:{group}")
            p.update(result)
            p["model_amount"] = "0.00"


def pair_atm_corrections(transactions: list[dict[str, Any]], categories: dict[str, Category]) -> None:
    withdrawals = [t for t in transactions if t["entity"] == "Personal" and "atm cash withdrawal" in t["description_raw"].lower() and D(t["principal_amount"]) < 0]
    corrections = [t for t in transactions if t["entity"] == "Personal" and "atm correction" in t["description_raw"].lower() and D(t["principal_amount"]) > 0]
    used: set[str] = set()
    for correction in corrections:
        cdate = date.fromisoformat(correction["transaction_date"])
        matches = [
            row for row in withdrawals
            if row["transaction_id"] not in used
            and abs((date.fromisoformat(row["transaction_date"]) - cdate).days) <= 1
            and abs(abs(D(row["principal_amount"])) - D(correction["principal_amount"])) <= Decimal("0.01")
        ]
        if len(matches) != 1:
            continue
        withdrawal = matches[0]
        used.add(withdrawal["transaction_id"])
        group = sha256_text(f"atm|{withdrawal['transaction_id']}|{correction['transaction_id']}")[:20]
        for row in (withdrawal, correction):
            row["transfer_group_id"] = group
            row.update(category_result("personal.expense.cash_withdrawal", categories, Decimal("0.99"), "matched ATM withdrawal/correction reversal", f"atm_pair:{group}"))
            row["model_amount"] = money(signed_model_amount(D(row["principal_amount"]), row["flow_type"], row["reportable"]))


def aggregate(transactions: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    totals: dict[tuple[str, str, str, str], dict[str, Decimal]] = defaultdict(lambda: {"amount": Decimal("0"), "recurring": Decimal("0"), "variable": Decimal("0")})
    for tx in transactions:
        if tx["reportable"] == "Yes" and tx["model_category"]:
            key = (tx["entity"], tx["statement_month"], tx["flow_type"], tx["model_category"])
            amount = D(tx["model_amount"])
            totals[key]["amount"] += amount
            if tx["recurring_status"] == "Recurring":
                totals[key]["recurring"] += amount
            else:
                totals[key]["variable"] += amount
        fee = D(tx["fee_amount"])
        if tx["entity"] == "Personal" and fee != 0:
            key = ("Personal", tx["statement_month"], "Expense", "Bank fees")
            fee_amount = -fee
            totals[key]["amount"] += fee_amount
            totals[key]["variable"] += fee_amount

    business_rows = []
    personal_rows = []
    for (entity, month, flow, category), values in sorted(totals.items()):
        if values["amount"] == 0:
            continue
        if entity == "Business":
            business_rows.append({
                "Month": month, "Tax Year": str(tax_year(month)), "Flow Type": flow,
                "Category": category, "Amount": money(values["amount"]),
                "Recurring Amount": money(values["recurring"]), "Variable Amount": money(values["variable"]),
            })
        else:
            personal_rows.append({
                "Month": month, "Tax Year": str(tax_year(month)), "Type": flow,
                "Category": category, "Actual": money(values["amount"]),
                "Recurring Actual": money(values["recurring"]), "Variable Actual": money(values["variable"]),
            })
    return business_rows, personal_rows


def recurring_candidates(transactions: list[dict[str, Any]]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for tx in transactions:
        if tx["reportable"] == "Yes" and D(tx["model_amount"]) > 0 and tx["flow_type"] in {"Expense", "Operating Expense"}:
            groups[(tx["entity"], tx["description_normalized"], tx["category_id"])].append(tx)
    output = []
    for (entity, key, category_id), rows in sorted(groups.items()):
        months = sorted(set(r["statement_month"] for r in rows))
        if len(months) < 3 or not key:
            continue
        month_indices = [date.fromisoformat(m).year * 12 + date.fromisoformat(m).month for m in months]
        gaps = [b - a for a, b in zip(month_indices, month_indices[1:])]
        median_gap = statistics.median(gaps) if gaps else 0
        frequency = "Monthly" if median_gap <= 1.5 else "Quarterly" if median_gap <= 4 else "Annual"
        amounts = [float(abs(D(r["model_amount"]))) for r in rows]
        median_amount = Decimal(str(statistics.median(amounts)))
        mean_amount = statistics.mean(amounts)
        cv = statistics.pstdev(amounts) / mean_amount if mean_amount else 0
        output.append({
            "entity": entity, "match_key": key, "category_id": category_id,
            "workbook_category": rows[0]["model_category"], "frequency": frequency,
            "occurrences": str(len(rows)), "distinct_months": str(len(months)),
            "first_month": months[0], "last_month": months[-1],
            "median_amount": money(median_amount), "amount_cv": f"{cv:.4f}",
            "status": "Suggested", "reason": "Repeated merchant pattern; review before activation",
        })
    return output


def monthly_closing_balances(transactions: list[dict[str, Any]], entity: str) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    rows = sorted([t for t in transactions if t["entity"] == entity], key=lambda t: (t["transaction_date"], t["source_path"], int(t["source_row"])))
    for tx in rows:
        result[tx["statement_month"]] = D(tx["balance"])
    return result


def opening_balance(transactions: list[dict[str, Any]], entity: str) -> Decimal:
    first = sorted([t for t in transactions if t["entity"] == entity], key=lambda t: (t["transaction_date"], t["source_path"], int(t["source_row"])))[0]
    return D(first["balance"]) - D(first["net_amount"])


def six_month_average(rows: list[dict[str, str]], actual_through: str, flow_field: str, amount_field: str, variable_field: str, allowed_flows: set[str], excluded_categories: set[str] | None = None) -> dict[tuple[str, str], Decimal]:
    excluded_categories = excluded_categories or set()
    months = months_between(add_months(actual_through, -5), actual_through)
    values: dict[tuple[str, str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    keys: set[tuple[str, str]] = set()
    for row in rows:
        flow = row[flow_field]
        category = row["Category"]
        if flow not in allowed_flows or category in excluded_categories:
            continue
        keys.add((flow, category))
        values[(row["Month"], flow, category)] += D(row[variable_field])
    result = {}
    for flow, category in sorted(keys):
        result[(flow, category)] = sum((values[(m, flow, category)] for m in months), Decimal("0")) / Decimal(len(months))
    return result


def add_trailing_metrics(rows: list[dict[str, str]], flow_field: str, amount_field: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        current_index = date.fromisoformat(row["Month"]).year * 12 + date.fromisoformat(row["Month"]).month
        prior = [
            candidate for candidate in rows
            if candidate["Category"] == row["Category"]
            and candidate[flow_field] == row[flow_field]
            and current_index - 6 <= date.fromisoformat(candidate["Month"]).year * 12 + date.fromisoformat(candidate["Month"]).month < current_index
        ]
        enriched = dict(row)
        if prior:
            average = sum((D(candidate[amount_field]) for candidate in prior), Decimal("0")) / Decimal(len(prior))
            amount = D(row[amount_field])
            variance = amount / average - Decimal("1") if average else None
            enriched["Trailing 6M Average"] = money(average)
            enriched["Variance %"] = f"{variance:.6f}" if variance is not None else ""
            enriched["Anomaly"] = "CHECK" if variance is not None and abs(amount - average) >= Decimal("500") and abs(variance) >= Decimal("0.25") else ""
        else:
            enriched.update({"Trailing 6M Average": "", "Variance %": "", "Anomaly": ""})
        output.append(enriched)
    return output


def build_payload(config: dict[str, Any], transactions: list[dict[str, Any]], business_rows: list[dict[str, str]], personal_rows: list[dict[str, str]], manifests: list[dict[str, Any]], validation: dict[str, Any], data_root: Path) -> dict[str, Any]:
    business_actual = max(r["Month"] for r in business_rows)
    personal_actual = max(r["Month"] for r in personal_rows)
    timeline_end = add_months(business_actual, int(config["future_forecast_months"]))
    timeline = months_between(config["cutoff_date"], timeline_end)
    categories = load_categories(data_root)
    nonforecastable = {
        category.model_category for category in categories.values()
        if category.forecastable != "Yes" and category.model_category
    }
    business_avg = six_month_average(
        business_rows, business_actual, "Flow Type", "Amount", "Variable Amount",
        {"Receipt", "Operating Expense"},
        nonforecastable | {"Funding / capital contributions", "Loans received", "Owner pay / draw"},
    )
    business_forecast_inputs = []
    for month in months_between(add_months(business_actual, 1), timeline_end):
        for (flow, category), amount in sorted(business_avg.items()):
            if amount == 0:
                continue
            business_forecast_inputs.append({
                "Month": month, "Category": category, "Scenario": "All",
                "Input Type": "Additive", "Amount": money(amount),
                "Notes": "pipeline-variable-baseline",
            })

    personal_avg = six_month_average(personal_rows, personal_actual, "Type", "Actual", "Variable Actual", {"Expense"}, nonforecastable)
    personal_future = []
    baseline_month = add_months(personal_actual, 1)
    for (flow, category), amount in sorted(personal_avg.items()):
        if amount == 0:
            continue
        personal_future.append({
            "Month": baseline_month, "Tax Year": str(tax_year(baseline_month)), "Type": flow,
            "Category": category, "Budget Adjustment": money(amount),
            "Actual": "0.00", "Recurring Actual": "0.00", "Variable Actual": "0.00",
            "Notes": "pipeline-variable-baseline",
        })

    personal_closing = monthly_closing_balances(transactions, "Personal")
    personal_cash_rows = [
        {"Month": month, "Item": "Personal bank account", "Position Type": "Asset", "Value": money(balance), "Include in Net Worth": "Yes", "Notes": "pipeline-personal-cash"}
        for month, balance in sorted(personal_closing.items())
    ]
    commitments = read_csv(data_root / "rules" / "recurring_commitments.csv")
    personal_categories = [c.model_category for c in sorted(categories.values(), key=lambda c: c.sort_order) if c.entity == "Personal" and c.reportable == "Yes" and c.model_category]
    business_categories = [c.model_category for c in sorted(categories.values(), key=lambda c: c.sort_order) if c.entity == "Business" and c.reportable == "Yes" and c.category_id != "business.adjustment.refund_unmatched"]
    personal_categories = list(dict.fromkeys(personal_categories))
    business_categories = list(dict.fromkeys(business_categories))
    source_hash = sha256_text(stable_json(manifests))[:12]
    business_payload_rows = add_trailing_metrics(business_rows, "Flow Type", "Amount")
    personal_payload_rows = add_trailing_metrics(personal_rows, "Type", "Actual")
    return {
        "pipeline_version": PIPELINE_VERSION,
        "cutoff_date": config["cutoff_date"],
        "model_start": month_start(config["cutoff_date"]),
        "business_actual_through": business_actual,
        "personal_actual_through": personal_actual,
        "timeline_end": timeline_end,
        "timeline_months": len(timeline),
        "future_forecast_months": int(config["future_forecast_months"]),
        "business_opening_cash": float(opening_balance(transactions, "Business")),
        "personal_opening_cash": float(opening_balance(transactions, "Personal")),
        "business_rows": business_payload_rows,
        "personal_rows": personal_payload_rows,
        "personal_variable_baseline": float(sum((D(row["Budget Adjustment"]) for row in personal_future), Decimal("0"))),
        "personal_baselines": [[row["Category"], row["Budget Adjustment"]] for row in personal_future],
        "business_forecast_inputs": business_forecast_inputs,
        "business_expense_baseline": float(sum((amount for (flow, _), amount in business_avg.items() if flow == "Operating Expense"), Decimal("0"))),
        "business_receipt_baseline": float(sum((amount for (flow, _), amount in business_avg.items() if flow == "Receipt"), Decimal("0"))),
        "business_baselines": [[flow, category, money(amount)] for (flow, category), amount in sorted(business_avg.items()) if amount != 0],
        "personal_cash_rows": personal_cash_rows,
        "recurring_commitments": commitments,
        "owner_pay_method": "Ad hoc draw",
        "business_categories": business_categories,
        "personal_categories": personal_categories,
        "source_tag": f"pipeline:{source_hash}",
        "status": {
            "personal_transaction_rows": validation["counts"]["personal"],
            "business_transaction_rows": validation["counts"]["business"],
            "personal_source_files": sum(1 for m in manifests if m["entity"] == "Personal" and m["source_type"] == "csv" and int(m.get("included_rows") or 0) > 0),
            "business_source_files": sum(1 for m in manifests if m["entity"] == "Business" and m["source_type"] == "csv" and int(m.get("included_rows") or 0) > 0),
            "personal_coverage": f"{validation['coverage']['personal_start']} to {validation['coverage']['personal_end']}",
            "business_coverage": f"{validation['coverage']['business_start']} to {validation['coverage']['business_end']}",
            "low_confidence": validation["low_confidence"],
            "validation_failures": len(validation["failures"]),
        },
    }


def validate_all(config: dict[str, Any], transactions: list[dict[str, Any]], manifests: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "personal": sum(1 for t in transactions if t["entity"] == "Personal"),
        "business": sum(1 for t in transactions if t["entity"] == "Business"),
    }
    expected = config.get("expected_initial_rows", {})
    for entity in ("personal", "business"):
        if expected.get(entity) is not None and counts[entity] != int(expected[entity]):
            failures.append({"code": "row_count_mismatch", "entity": entity, "expected": int(expected[entity]), "actual": counts[entity]})
    ids = [t["transaction_id"] for t in transactions]
    duplicate_ids = len(ids) - len(set(ids))
    if duplicate_ids:
        failures.append({"code": "duplicate_transaction_ids", "count": duplicate_ids})
    blank_categories = sum(1 for t in transactions if not t.get("category_id"))
    if blank_categories:
        failures.append({"code": "blank_categories", "count": blank_categories})
    cutoff_violations = sum(1 for t in transactions if t["transaction_date"] < config["cutoff_date"])
    if cutoff_violations:
        failures.append({"code": "cutoff_violations", "count": cutoff_violations})
    noisy_large = [
        t["transaction_id"] for t in transactions
        if t.get("model_category") in {"Other income", "Other expenses"}
        and abs(D(t.get("model_amount"))) > Decimal("1000")
    ]
    if noisy_large:
        failures.append({"code": "large_generic_categories", "count": len(noisy_large), "transaction_ids": noisy_large})
    negative_tax = [t["transaction_id"] for t in transactions if t.get("model_category") == "Tax" and D(t.get("model_amount")) < 0]
    if negative_tax:
        failures.append({"code": "negative_tax_expense", "count": len(negative_tax), "transaction_ids": negative_tax})
    atm_other = [
        t["transaction_id"] for t in transactions
        if "atm correction" in t.get("description_raw", "").lower() and t.get("model_category") == "Other income"
    ]
    if atm_other:
        failures.append({"code": "atm_correction_other_income", "count": len(atm_other), "transaction_ids": atm_other})
    low = sum(1 for t in transactions if D(t["classification_confidence"]) < Decimal("0.80"))
    personal_dates = [t["transaction_date"] for t in transactions if t["entity"] == "Personal"]
    business_dates = [t["transaction_date"] for t in transactions if t["entity"] == "Business"]
    return {
        "status": "pass" if not failures else "fail",
        "pipeline_version": PIPELINE_VERSION,
        "counts": counts,
        "duplicate_ids": duplicate_ids,
        "blank_categories": blank_categories,
        "low_confidence": low,
        "coverage": {
            "personal_start": min(personal_dates), "personal_end": max(personal_dates),
            "business_start": min(business_dates), "business_end": max(business_dates),
        },
        "failures": failures,
        "source_manifest_rows": len(manifests),
    }


def validate_aggregates(transactions: list[dict[str, Any]], business_rows: list[dict[str, str]], personal_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for entity, rows, amount_field, recurring_field, variable_field in [
        ("Business", business_rows, "Amount", "Recurring Amount", "Variable Amount"),
        ("Personal", personal_rows, "Actual", "Recurring Actual", "Variable Actual"),
    ]:
        split_errors = [row for row in rows if abs(D(row[amount_field]) - D(row[recurring_field]) - D(row[variable_field])) > Decimal("0.01")]
        if split_errors:
            failures.append({"code": "recurring_variable_split", "entity": entity, "count": len(split_errors)})
        ledger_total = sum((D(t["model_amount"]) for t in transactions if t["entity"] == entity and t["reportable"] == "Yes" and t["model_category"]), Decimal("0"))
        if entity == "Personal":
            ledger_total += sum((-D(t["fee_amount"]) for t in transactions if t["entity"] == "Personal"), Decimal("0"))
        aggregate_total = sum((D(row[amount_field]) for row in rows), Decimal("0"))
        if abs(ledger_total - aggregate_total) > Decimal("0.01"):
            failures.append({"code": "ledger_aggregate_total", "entity": entity, "ledger": money(ledger_total), "aggregate": money(aggregate_total)})
    return failures


def prepare(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Path]:
    data_root = Path(config["data_root"])
    for name in ["taxonomy", "rules", "manifests", "ledgers", "aggregates", "recurring", "runs", "backups", "extracted"]:
        (data_root / name).mkdir(parents=True, exist_ok=True)
    ensure_reference_files(data_root, config)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_dir = data_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    raw_transactions, manifests, failures = discover_and_normalize(config, data_root)
    transactions, _ = classify_transactions(raw_transactions, data_root)
    business_rows, personal_rows = aggregate(transactions)
    failures.extend(validate_aggregates(transactions, business_rows, personal_rows))
    validation = validate_all(config, transactions, manifests, failures)

    write_csv(data_root / "manifests" / "sources.csv", ["entity", "source_path", "source_sha256", "source_type", "schema", "row_count", "included_rows", "period_start", "period_end", "validation_status", "validation_level"], manifests)
    write_csv(data_root / "ledgers" / "personal_transactions.csv", LEDGER_FIELDS, [t for t in transactions if t["entity"] == "Personal"])
    write_csv(data_root / "ledgers" / "business_transactions.csv", LEDGER_FIELDS, [t for t in transactions if t["entity"] == "Business"])
    write_csv(data_root / "aggregates" / "business_monthly.csv", ["Month", "Tax Year", "Flow Type", "Category", "Amount", "Recurring Amount", "Variable Amount"], business_rows)
    write_csv(data_root / "aggregates" / "personal_monthly.csv", ["Month", "Tax Year", "Type", "Category", "Actual", "Recurring Actual", "Variable Actual"], personal_rows)
    candidates = recurring_candidates(transactions)
    write_csv(data_root / "recurring" / "recurring_candidates.csv", ["entity", "match_key", "category_id", "workbook_category", "frequency", "occurrences", "distinct_months", "first_month", "last_month", "median_amount", "amount_cv", "status", "reason"], candidates)
    low_conf = [t for t in transactions if D(t["classification_confidence"]) < Decimal("0.80")]
    write_csv(run_dir / "classification_review.csv", LEDGER_FIELDS, low_conf)
    write_json(run_dir / "validation.json", validation)
    write_json(run_dir / "source_manifest.json", manifests)

    snapshot_dir = run_dir / "rule_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for path in [
        data_root / "taxonomy" / "categories.csv",
        data_root / "taxonomy" / "aliases.csv",
        data_root / "rules" / "category_rules.csv",
        data_root / "rules" / "transaction_overrides.csv",
        data_root / "rules" / "recurring_rules.csv",
        data_root / "rules" / "recurring_commitments.csv",
    ]:
        shutil.copy2(path, snapshot_dir / path.name)

    payload = build_payload(config, transactions, business_rows, personal_rows, manifests, validation, data_root)
    reference_hashes = {}
    for path in [
        data_root / "taxonomy" / "categories.csv", data_root / "taxonomy" / "aliases.csv",
        data_root / "rules" / "category_rules.csv", data_root / "rules" / "transaction_overrides.csv",
        data_root / "rules" / "recurring_rules.csv",
        data_root / "rules" / "recurring_commitments.csv",
    ]:
        reference_hashes[str(path)] = sha256_file(path)
    state = {
        "pipeline_version": PIPELINE_VERSION,
        "sources": [(m["source_path"], m["source_sha256"], m["included_rows"]) for m in manifests if m["source_type"] == "csv"],
        "references": reference_hashes,
        "payload_hash": sha256_text(stable_json(payload)),
    }
    state["state_hash"] = sha256_text(stable_json(state))
    payload["state_hash"] = state["state_hash"]
    write_json(data_root / "manifests" / "state.json", state)
    write_json(run_dir / "workbook_payload.json", payload)
    if validation["status"] != "pass":
        raise RuntimeError(f"Validation failed; see {run_dir / 'validation.json'}")
    return payload, validation, run_dir


def run_command(
    args: list[str], output_path: Path | None = None, allow: set[int] | None = None,
    attempts: int = 1, retry_delay: int = 5, timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    allowed = allow or {0}
    last: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, attempts + 1):
        try:
            proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            proc = subprocess.CompletedProcess(args, 124, stdout, stderr + f"\nTimed out after {timeout_seconds}s")
        last = proc
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            prefix = f"ATTEMPT {attempt}/{attempts}\n" if attempts > 1 else ""
            output_path.write_text(prefix + proc.stdout + ("\nSTDERR\n" + proc.stderr if proc.stderr else ""), encoding="utf-8")
        if proc.returncode in allowed:
            return proc
        if attempt < attempts:
            time.sleep(retry_delay * attempt)
    assert last is not None
    raise RuntimeError(f"Command failed ({last.returncode}): {' '.join(args)}\n{last.stdout}\n{last.stderr}")


def update_workbook(
    config: dict[str, Any], payload: dict[str, Any], run_dir: Path, force: bool,
    resume_candidate: Path | None = None, resume_from_phase: str | None = None,
    chunk_size: int = 5, rotate_every: int = 1, witan_timeout_ms: int = 20000,
    stop_after_phase: str | None = None, witan_outer_attempts: int = 1,
) -> dict[str, Any]:
    data_root = Path(config["data_root"])
    last_success_path = data_root / "manifests" / "last_success.json"
    if last_success_path.exists() and not force:
        last = json.loads(last_success_path.read_text(encoding="utf-8"))
        if last.get("state_hash") == payload["state_hash"]:
            result = {"status": "unchanged", "state_hash": payload["state_hash"], "workbook": config["workbook_path"]}
            workbook_hash = sha256_file(Path(config["workbook_path"]))
            write_json(run_dir / "workbook_diff.json", {
                "status": "unchanged", "before_sha256": workbook_hash,
                "after_sha256": workbook_hash, "state_hash": payload["state_hash"],
            })
            write_json(run_dir / "workbook_result.json", result)
            return result

    workbook = Path(config["workbook_path"])
    if not workbook.exists():
        raise FileNotFoundError(workbook)
    before_sha256 = sha256_file(workbook)
    staging_dir = Path(tempfile.mkdtemp(prefix="financial-model-stage-"))
    candidate = staging_dir / "candidate.xlsx"
    if resume_candidate is None:
        shutil.copy2(workbook, candidate)
    else:
        if not resume_candidate.exists():
            raise FileNotFoundError(resume_candidate)
        shutil.copy2(resume_candidate, candidate)
    witan = config["witan_path"]
    update_script = SCRIPT_DIR / "workbook_update.js"
    update_source = update_script.read_text(encoding="utf-8")
    phase_prefix = update_source.split("if (input.phase ===", 1)[0]
    phase_script_dir = run_dir / "phase_scripts"
    phase_script_dir.mkdir(parents=True, exist_ok=True)

    def phase_script(phase_name: str) -> Path:
        marker = f"if (input.phase === '{phase_name}')"
        start = update_source.find(marker)
        if start < 0:
            raise ValueError(f"Workbook phase not found: {phase_name}")
        ends = [
            pos for token in ("\nif (input.phase ===", "\nif (input.phase !==")
            if (pos := update_source.find(token, start + len(marker))) >= 0
        ]
        end = min(ends) if ends else len(update_source)
        path = phase_script_dir / f"{phase_name}.js"
        path.write_text(phase_prefix + update_source[start:end] + "\n", encoding="utf-8")
        return path
    common = {
        "pipeline_version": payload["pipeline_version"], "cutoff_date": payload["cutoff_date"],
        "source_tag": payload["source_tag"], "state_hash": payload["state_hash"],
        "run_timestamp": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
    }
    preservation_path = run_dir / "workbook_preservation.json"
    if preservation_path.exists():
        preservation = json.loads(preservation_path.read_text(encoding="utf-8"))
    else:
        preservation = None
        if last_success_path.exists():
            last_success = json.loads(last_success_path.read_text(encoding="utf-8"))
            prior_path = Path(last_success.get("run_dir", "")) / "workbook_preservation.json"
            prior_hash = last_success.get("workbook_sha256") or last_success.get("after_sha256")
            if prior_hash == before_sha256 and prior_path.exists():
                preservation = json.loads(prior_path.read_text(encoding="utf-8"))
                write_json(run_dir / "preservation_recovery.json", {
                    "status": "reused_verified_snapshot", "source": str(prior_path),
                    "workbook_sha256": before_sha256,
                })
        if preservation is None:
            preservation_proc = run_command(
                [witan, "--stateless", "xlsx", "exec", str(candidate), "--script", str(phase_script("preservation_export")),
                 "--input-json", stable_json({**common, "phase": "preservation_export"}), "--timeout-ms", "20000"],
                run_dir / "witan-preservation-export.txt", attempts=3, timeout_seconds=90,
            )
            preservation = json.loads(preservation_proc.stdout)
        write_json(preservation_path, preservation)
    excel_epoch = date(1899, 12, 30)
    business_matrix = [[
        (date.fromisoformat(row["Month"]) - excel_epoch).days, int(row["Tax Year"]),
        row["Flow Type"], row["Category"], float(row["Amount"]), float(row["Recurring Amount"]),
        float(row["Variable Amount"]), "Yes", "", payload["source_tag"],
        float(row["Trailing 6M Average"]) if row.get("Trailing 6M Average") else "",
        float(row["Variance %"]) if row.get("Variance %") else "", row.get("Anomaly", ""),
    ] for row in payload["business_rows"]]
    personal_matrix = []
    for row in payload["personal_rows"]:
        note = "Variable baseline from trailing 6M actuals" if row.get("Notes") == "pipeline-variable-baseline" else row.get("Notes", "")
        personal_matrix.append([
            (date.fromisoformat(row["Month"]) - excel_epoch).days,
            row["Type"], row["Category"], float(row.get("Budget Adjustment", "0")),
            float(row["Actual"]), float(row["Recurring Actual"]), float(row["Variable Actual"]), note,
        ])

    def pipeline_key(month_iso: str, flow: str, category: str) -> str:
        return f"{date.fromisoformat(month_iso).strftime('%b-%y')}|{flow}|{category}"

    def as_float(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    business_positions = {
        pipeline_key(row["Month"], row["Flow Type"], row["Category"]): idx
        for idx, row in enumerate(payload["business_rows"])
    }
    for saved in preservation.get("business", []):
        key, old = saved.get("key", ""), saved.get("row", {})
        if key in business_positions:
            if old.get("Notes") not in (None, ""):
                business_matrix[business_positions[key]][8] = old["Notes"]
            continue
        source = str(old.get("Source") or "")
        if old.get("Month") and old.get("Flow Type") and old.get("Category") and not source.startswith("pipeline:"):
            business_matrix.append([
                old.get("Month"), old.get("Tax Year") or "", old.get("Flow Type"), old.get("Category"),
                as_float(old.get("Amount")), as_float(old.get("Recurring Amount")),
                as_float(old.get("Variable Amount") or old.get("Amount")), old.get("Verified") or "No",
                old.get("Notes") or "", source, old.get("Trailing 6M Average") or "",
                old.get("Variance %") or "", old.get("Anomaly") or "",
            ])

    personal_positions = {
        pipeline_key(row["Month"], row["Type"], row["Category"]): idx
        for idx, row in enumerate(payload["personal_rows"])
    }
    for saved in preservation.get("personal", []):
        key, old = saved.get("key", ""), saved.get("row", {})
        if key in personal_positions:
            idx = personal_positions[key]
            personal_matrix[idx][3] += as_float(old.get("Budget Adjustment"))
            if old.get("Notes") not in (None, ""):
                personal_matrix[idx][7] = old["Notes"]
            continue
        if (old.get("Month") and old.get("Type") and old.get("Category") and
                (as_float(old.get("Budget Adjustment")) != 0 or old.get("Notes") not in (None, ""))):
            personal_matrix.append([
                old.get("Month"), old.get("Type"), old.get("Category"), as_float(old.get("Budget Adjustment")),
                as_float(old.get("Actual")),
                as_float(old.get("Recurring Actual")), as_float(old.get("Variable Actual") or old.get("Actual")),
                old.get("Notes") or "",
            ])
    phase_inputs = [
        ("model_suspend", {}),
        ("business_init", {"row_count": len(business_matrix)}),
        ("personal_init", {"row_count": len(personal_matrix)}),
        ("personal_finalize", {"row_count": len(personal_matrix), "rows": personal_matrix}),
        ("recurring_setup", {"commitments": payload["recurring_commitments"]}),
        ("net_worth", {"personal_cash_rows": [[
            row["Month"], row["Item"], row["Position Type"], row["Value"], row["Include in Net Worth"]
        ] for row in payload["personal_cash_rows"]]}),
        ("setup_controls", {
            "timeline_months": payload["timeline_months"], "model_start": payload["model_start"],
            "business_actual_through": payload["business_actual_through"],
            "personal_actual_through": payload["personal_actual_through"],
            "business_opening_cash": payload["business_opening_cash"],
            "personal_opening_cash": payload["personal_opening_cash"],
            "personal_variable_baseline": payload["personal_variable_baseline"],
            "business_expense_baseline": payload["business_expense_baseline"],
            "business_receipt_baseline": payload["business_receipt_baseline"],
            "future_forecast_months": payload["future_forecast_months"],
            "owner_pay_method": payload["owner_pay_method"],
        }),
        *[(phase, {
            "business_categories": payload["business_categories"],
            "personal_categories": payload["personal_categories"],
            "business_actual_through": payload["business_actual_through"],
            "personal_actual_through": payload["personal_actual_through"],
            "timeline_end": payload["timeline_end"], "timeline_months": payload["timeline_months"],
            "status": payload["status"], "personal_baselines": payload["personal_baselines"],
            "business_baselines": payload["business_baselines"],
        }) for phase in [
            "finish_categories", "finish_names", "finish_validations", "finish_add_sheets",
            "finish_status_data", "finish_personal_baseline_data", "finish_business_baseline_data",
            "finish_status_style", "finish_baseline_style", "finish_model_style",
        ]],
        *[(
            f"setup_personal_timeline_{start + 1}",
            {"phase_alias": "setup_personal_timeline", "start_row": 6 + start,
             "row_count": 1},
        ) for start in range(payload["timeline_months"])],
        *[(
            f"setup_business_baseline_{start // 6 + 1}",
            {"phase_alias": "setup_business_baseline", "start_col": 2 + start,
             "col_count": min(6, payload["timeline_months"] - start)},
        ) for start in range(0, payload["timeline_months"], 6)],
        ("model_restore", {}),
        ("kpi_split", {"timeline_months": payload["timeline_months"]}),
    ]
    business_chunk_size = chunk_size
    business_insert = next(i for i, item in enumerate(phase_inputs) if item[0] == "business_init") + 1
    for start in range(0, len(business_matrix), business_chunk_size):
        phase_inputs.insert(business_insert + start // business_chunk_size, (
            f"business_chunk_{start // business_chunk_size + 1}",
            {"phase_alias": "business_chunk", "start_row": 6 + start, "rows": business_matrix[start:start + business_chunk_size]},
        ))
    personal_insert = next(i for i, item in enumerate(phase_inputs) if item[0] == "personal_init") + 1
    for start in range(0, len(personal_matrix), chunk_size):
        phase_inputs.insert(personal_insert + start // chunk_size, (
            f"personal_chunk_{start // chunk_size + 1}",
            {"phase_alias": "personal_chunk", "start_row": 6 + start, "rows": personal_matrix[start:start + chunk_size]},
        ))
    resume_reached = resume_from_phase is None
    for phase_index, (phase, specific) in enumerate(phase_inputs):
        if not resume_reached:
            if phase != resume_from_phase:
                continue
            resume_reached = True
        if phase_index and phase_index % rotate_every == 0:
            rotated = staging_dir / f"candidate-stage-{phase_index // rotate_every + 1}.xlsx"
            shutil.copy2(candidate, rotated)
            candidate = rotated
        phase_payload = {**common, **specific, "phase": specific.get("phase_alias", phase)}
        phase_alias = specific.get("phase_alias", phase)
        run_command(
            [witan, "--stateless", "xlsx", "exec", str(candidate), "--script", str(phase_script(phase_alias)),
             "--input-json", stable_json(phase_payload), "--save", "--timeout-ms", str(witan_timeout_ms)],
            run_dir / f"witan-update-{phase}.txt",
            attempts=witan_outer_attempts,
            timeout_seconds=max(180, (witan_timeout_ms // 1000) * 8),
        )
        write_json(run_dir / "workbook_checkpoint.json", {
            "completed_phase": phase, "candidate": str(candidate), "phase_index": phase_index,
        })
        time.sleep(2)
        if phase == stop_after_phase:
            result = {
                "status": "staged", "completed_phase": phase, "candidate": str(candidate),
                "state_hash": payload["state_hash"], "run_dir": str(run_dir),
            }
            write_json(run_dir / "workbook_result.json", result)
            return result
    if not resume_reached:
        raise ValueError(f"Unknown resume phase: {resume_from_phase}")
    calc_proc = run_command([witan, "xlsx", "calc", str(candidate)], run_dir / "witan-calc.txt")
    if not re.search(r"\b0 errors\b", calc_proc.stdout):
        raise RuntimeError(f"Workbook calculation did not report zero errors; see {run_dir / 'witan-calc.txt'}")
    lint_proc = run_command([witan, "xlsx", "lint", str(candidate)], run_dir / "witan-lint.txt", allow={0, 2})
    if re.search(r"^Error \([1-9]", lint_proc.stdout, flags=re.M):
        raise RuntimeError(f"Workbook lint contains formula errors; see {run_dir / 'witan-lint.txt'}")

    render_dir = run_dir / "renders"
    render_specs = [
        ("Dashboard!A1:U56", "dashboard.png"),
        ("'Business Forecast'!A1:AK48", "business-forecast.png"),
        ("'Personal Monthly'!A1:W41", "personal-monthly.png"),
        ("'Assets & Net Worth'!A1:N41", "assets-net-worth.png"),
        ("Recurring!A1:L70", "recurring.png"),
        ("'Setup & Checks'!A1:J32", "setup-checks.png"),
    ]
    for range_ref, filename in render_specs:
        run_command([witan, "xlsx", "render", str(candidate), "-r", range_ref, "-o", str(render_dir / filename)], run_dir / f"render-{filename}.txt")

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = data_root / "backups" / f"Business & Personal Financial Model {stamp}.xlsx"
    shutil.copy2(workbook, backup)
    promotion_temp = workbook.with_name(f".{workbook.stem}.{stamp}.staged.xlsx")
    shutil.copy2(candidate, promotion_temp)
    os.replace(promotion_temp, workbook)
    after_sha256 = sha256_file(workbook)
    result = {
        "status": "updated", "state_hash": payload["state_hash"],
        "workbook": str(workbook), "workbook_sha256": after_sha256,
        "backup": str(backup), "run_dir": str(run_dir),
    }
    write_json(run_dir / "workbook_diff.json", {
        "status": "updated", "before_sha256": before_sha256,
        "after_sha256": after_sha256, "state_hash": payload["state_hash"],
        "table_row_counts": {
            "tblBusinessActuals": len(payload["business_rows"]),
            "tblPersonalMonthly": len(payload["personal_rows"]),
            "business_variable_baselines": len(payload["business_baselines"]),
            "tblNetWorthSnapshots_pipeline": len(payload["personal_cash_rows"]),
        },
    })
    write_json(last_success_path, result)
    write_json(run_dir / "workbook_result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--update-workbook", action="store_true")
    mode.add_argument("--resume-run")
    parser.add_argument("--force-workbook", action="store_true")
    parser.add_argument("--resume-candidate")
    parser.add_argument("--resume-from-phase")
    parser.add_argument("--chunk-size", type=int, default=5)
    parser.add_argument("--rotate-every", type=int, default=1)
    parser.add_argument("--witan-timeout-ms", type=int, default=20000)
    parser.add_argument("--stop-after-phase")
    parser.add_argument("--witan-outer-attempts", type=int, default=1)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.resume_run:
        run_dir = Path(args.resume_run)
        payload = json.loads((run_dir / "workbook_payload.json").read_text(encoding="utf-8"))
        if not args.resume_candidate or not args.resume_from_phase:
            parser.error("--resume-run requires --resume-candidate and --resume-from-phase")
        result = update_workbook(
            config, payload, run_dir, True, Path(args.resume_candidate), args.resume_from_phase,
            args.chunk_size, args.rotate_every, args.witan_timeout_ms, args.stop_after_phase,
            args.witan_outer_attempts,
        )
    else:
        payload, validation, run_dir = prepare(config)
        result = {"status": "prepared", "run_dir": str(run_dir), "validation": validation}
        if args.update_workbook:
            result = update_workbook(
                config, payload, run_dir, args.force_workbook,
                chunk_size=args.chunk_size, rotate_every=args.rotate_every,
                witan_timeout_ms=args.witan_timeout_ms,
                stop_after_phase=args.stop_after_phase,
                witan_outer_attempts=args.witan_outer_attempts,
            )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
