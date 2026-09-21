import importlib.util
import sys
import unittest
from decimal import Decimal
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "update_financial_model.py"
SPEC = importlib.util.spec_from_file_location("financial_pipeline", SCRIPT)
pipeline = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


class FinancialPipelineTests(unittest.TestCase):
    def setUp(self):
        self.categories = {row.category_id: row for row in pipeline.category_seed()}
        self.aliases = {
            row["source_label"]: (row["category_id"], Decimal(row["confidence"]))
            for row in pipeline.alias_seed()
        }
        self.rules = pipeline.rule_seed()

    def tx(self, **overrides):
        row = {
            "transaction_id": "tx-1", "entity": "Personal",
            "description_raw": "ordinary purchase", "description_normalized": "ordinary purchase",
            "legacy_category": "Groceries", "principal_amount": "-100.00",
        }
        row.update(overrides)
        return row

    def test_south_african_tax_year_boundary(self):
        self.assertEqual(pipeline.tax_year("2026-02-28"), 2026)
        self.assertEqual(pipeline.tax_year("2026-03-01"), 2027)

    def test_savings_transfer_is_non_reportable(self):
        result = pipeline.classify(
            self.tx(description_raw="Transfer to 32Day account", legacy_category="Transfer"),
            self.categories, self.aliases, self.rules, {},
        )
        self.assertEqual(result["flow_type"], "Asset Movement")
        self.assertEqual(result["reportable"], "No")

    def test_business_capital_rule(self):
        result = pipeline.classify(
            self.tx(
                entity="Business", description_raw="MagTape Credit Matt Deposit",
                description_normalized="magtape credit matt deposit", legacy_category="",
                principal_amount="1000.00",
            ),
            self.categories, self.aliases, self.rules, {},
        )
        self.assertEqual(result["category_id"], "business.receipt.capital_contribution")
        self.assertEqual(result["flow_type"], "Receipt")

    def test_override_precedes_merchant_rule(self):
        overrides = {
            "tx-1": {
                "category_id": "personal.expense.education", "confidence": "1.00",
                "reason": "reviewed", "reportable": "Yes",
            }
        }
        result = pipeline.classify(
            self.tx(description_raw="Checkers grocery"),
            self.categories, self.aliases, self.rules, overrides,
        )
        self.assertEqual(result["category_id"], "personal.expense.education")

    def test_personal_fee_aggregates_separately(self):
        row = {
            "entity": "Personal", "statement_month": "2025-07-01", "flow_type": "Expense",
            "model_category": "Groceries & household supplies", "model_amount": "100.00",
            "reportable": "Yes", "recurring_status": "Variable", "fee_amount": "-2.50",
        }
        _, personal = pipeline.aggregate([row])
        by_category = {item["Category"]: Decimal(item["Actual"]) for item in personal}
        self.assertEqual(by_category["Groceries & household supplies"], Decimal("100.00"))
        self.assertEqual(by_category["Bank fees"], Decimal("2.50"))

    def test_expense_credit_reduces_expense_without_refund_keyword(self):
        self.assertEqual(
            pipeline.signed_model_amount(Decimal("1500.75"), "Expense", "Yes"),
            Decimal("-1500.75"),
        )

    def test_merchant_rule_precedes_legacy_investment_hint(self):
        result = pipeline.classify(
            self.tx(description_raw="Empire Cafe Cape Town", legacy_category="Investments"),
            self.categories, self.aliases, self.rules, {},
        )
        self.assertEqual(result["category_id"], "personal.expense.dining_takeaways")

    def test_owner_pay_pair_eliminates_duplicate_personal_income(self):
        business = {
            "transaction_id": "biz", "entity": "Business", "category_id": "business.owner.owner_pay",
            "principal_amount": "-5000.00", "transaction_date": "2025-07-25", "transfer_group_id": "",
        }
        personal = {
            "transaction_id": "pers", "entity": "Personal", "category_id": "personal.income.other",
            "principal_amount": "5000.00", "transaction_date": "2025-07-26", "transfer_group_id": "",
            "model_amount": "5000.00",
        }
        pipeline.pair_inter_entity_transfers([business, personal], self.categories)
        self.assertTrue(business["transfer_group_id"])
        self.assertEqual(personal["category_id"], "personal.transfer.owner_pay_receipt")
        self.assertEqual(personal["model_amount"], "0.00")

    def test_personal_actuals_table_is_relocated_without_renaming(self):
        workbook_script = (Path(__file__).parents[1] / "scripts" / "workbook_update.js").read_text(encoding="utf-8")
        self.assertIn("renameSheet(wb, 'Personal Monthly', 'Personal Actuals')", workbook_script)
        self.assertIn("setListObject(wb, 'tblPersonalMonthly'", workbook_script)
        self.assertIn("address: `'Personal Actuals'!${colLetter", workbook_script)
        self.assertNotIn("input.phase === 'personal_bulk'", workbook_script)
        init_block = workbook_script.split("if (input.phase === 'personal_init')", 1)[1].split("if (input.phase === 'personal_finalize')", 1)[0]
        finalize_block = workbook_script.split("if (input.phase === 'personal_finalize')", 1)[1].split("if (input.phase === 'personal_tail')", 1)[0]
        self.assertNotIn("deleteListObject(wb, 'tblPersonalMonthly')", init_block)
        self.assertNotIn("deleteListObject(wb, 'tblPersonalMonthly')", finalize_block)
        self.assertIn("setListObject(wb, 'tblPersonalMonthly'", init_block)

    def test_personal_phase_order_finishes_after_chunks(self):
        pipeline_script = SCRIPT.read_text(encoding="utf-8")
        init_pos = pipeline_script.index('(\"personal_init\"')
        finalize_pos = pipeline_script.index('(\"personal_finalize\"')
        insert_pos = pipeline_script.index('personal_insert =')
        self.assertLess(init_pos, finalize_pos)
        self.assertGreater(insert_pos, finalize_pos)
        self.assertNotIn('(\"personal_suspend\"', pipeline_script)
        self.assertNotIn("--bulk-personal", pipeline_script)

    def test_nonforecastable_review_categories(self):
        for category_id in [
            "personal.income.tax_refund", "personal.income.unidentified_receipt",
            "personal.expense.cash_withdrawal", "personal.expense.unidentified_person_payment",
            "personal.transfer.savings_investments", "business.receipt.capital_contribution",
        ]:
            self.assertEqual(self.categories[category_id].forecastable, "No")

    def test_sars_credit_is_positive_tax_refund_income(self):
        result = pipeline.classify(
            self.tx(
                description_raw="Payment Received: A SARS 0360104293",
                description_normalized="a sars", principal_amount="27299.07", direction="credit",
                legacy_category="Tax",
            ), self.categories, self.aliases, self.rules, {},
        )
        self.assertEqual(result["category_id"], "personal.income.tax_refund")
        self.assertEqual(result["flow_type"], "Income")
        self.assertEqual(pipeline.signed_model_amount(Decimal("27299.07"), result["flow_type"], result["reportable"]), Decimal("27299.07"))

    def test_atm_correction_offsets_original_with_pair(self):
        withdrawal = {
            "transaction_id": "wd", "entity": "Personal", "description_raw": "ATM Cash Withdrawal: Mataram",
            "principal_amount": "-1203.94", "transaction_date": "2026-06-27", "transfer_group_id": "",
        }
        correction = {
            "transaction_id": "cr", "entity": "Personal", "description_raw": "ATM Correction: Cash Withdrawal",
            "principal_amount": "1203.94", "transaction_date": "2026-06-27", "transfer_group_id": "",
        }
        pipeline.pair_atm_corrections([withdrawal, correction], self.categories)
        self.assertEqual(withdrawal["transfer_group_id"], correction["transfer_group_id"])
        self.assertEqual(Decimal(withdrawal["model_amount"]) + Decimal(correction["model_amount"]), Decimal("0"))

    def test_recurring_rule_respects_start_and_end_month(self):
        rule = {"entity": "Business", "match_key": "adobe", "start_month": "2025-07-01", "end_month": "2025-12-01"}
        self.assertTrue(pipeline.recurring_rule_matches({"entity": "Business", "description_normalized": "adobe", "statement_month": "2025-12-01"}, rule))
        self.assertFalse(pipeline.recurring_rule_matches({"entity": "Business", "description_normalized": "adobe", "statement_month": "2026-01-01"}, rule))

    def test_owner_direction_rules_distinguish_draw_and_funding(self):
        credit = pipeline.classify(
            self.tx(entity="Business", description_raw="MagTape Credit Matt Deposit", description_normalized="magtape credit matt deposit", principal_amount="1000", direction="credit", legacy_category=""),
            self.categories, self.aliases, self.rules, {},
        )
        debit = pipeline.classify(
            self.tx(entity="Business", description_raw="Payment to Example Person", description_normalized="payment to example person", principal_amount="-1000", direction="debit", legacy_category=""),
            self.categories, self.aliases, self.rules, {},
        )
        self.assertEqual(credit["category_id"], "business.receipt.capital_contribution")
        self.assertEqual(debit["category_id"], "business.owner.owner_pay")

    def test_workbook_contains_owner_control_and_kpi_reconciliation(self):
        workbook_script = (Path(__file__).parents[1] / "scripts" / "workbook_update.js").read_text(encoding="utf-8")
        self.assertIn("Owner pay mechanism conflict", workbook_script)
        self.assertIn("Business receipt KPI reconciliation", workbook_script)
        self.assertIn("Core operating expenses", workbook_script)
        self.assertIn("const ownerPayCategory = '\"Salary / owner pay\"'", workbook_script)
        self.assertIn("tblBizForecastInputs[Category],${ownerPayCategory}", workbook_script)
        self.assertIn("setChart(wb, 'Dashboard', 'BusinessTrend'", workbook_script)
        self.assertIn("setChart(wb, 'Dashboard', 'PersonalTrend'", workbook_script)


if __name__ == "__main__":
    unittest.main()
