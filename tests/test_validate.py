import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookyp import validate


def base_result(**overrides):
    result = {
        "file": "receipt1.jpg",
        "merchant": "Cafe",
        "date": "2024-03-05",
        "currency": "USD",
        "items": [
            {"name": "Coffee", "qty": 1, "unit_price": 3.00, "amount": 3.00},
            {"name": "Bagel", "qty": 2, "unit_price": 1.50, "amount": 3.00},
        ],
        "subtotal": 6.00,
        "tax": 0.50,
        "total": 6.50,
        "ocr_mean_conf": 0.95,
    }
    result.update(overrides)
    return result


class ValidateTests(unittest.TestCase):
    def test_accepts_valid_receipt(self):
        status, reasons = validate.validate(base_result(), today=date(2024, 6, 1))
        self.assertEqual(status, "accepted")
        self.assertEqual(reasons, [])

    def test_subtotal_mismatch(self):
        status, reasons = validate.validate(
            base_result(subtotal=5.00), today=date(2024, 6, 1)
        )
        self.assertEqual(status, "needs_review")
        self.assertIn("sum of item amounts does not equal subtotal", reasons)

    def test_accepts_tax_inclusive(self):
        # VAT/GST already included: subtotal == total, tax not added on top.
        result = base_result(total=6.00, tax=0.50)
        status, reasons = validate.validate(result, today=date(2024, 6, 1))
        self.assertEqual(status, "accepted")
        self.assertTrue(result["tax_inclusive"])

    def test_total_tax_mismatch(self):
        status, reasons = validate.validate(
            base_result(total=5.00), today=date(2024, 6, 1)
        )
        self.assertEqual(status, "needs_review")
        self.assertIn(
            "neither subtotal + tax nor subtotal alone equals total", reasons
        )

    def test_missing_total(self):
        status, reasons = validate.validate(
            base_result(total=None), today=date(2024, 6, 1)
        )
        self.assertEqual(status, "needs_review")
        self.assertIn("total is missing", reasons)

    def test_zero_total(self):
        status, reasons = validate.validate(
            base_result(total=0.0), today=date(2024, 6, 1)
        )
        self.assertIn("total is not greater than 0", reasons)

    def test_missing_tax(self):
        status, reasons = validate.validate(
            base_result(tax=None), today=date(2024, 6, 1)
        )
        self.assertIn("tax is missing", reasons)

    def test_low_confidence(self):
        status, reasons = validate.validate(
            base_result(ocr_mean_conf=0.10), today=date(2024, 6, 1)
        )
        self.assertIn("mean OCR confidence is below 0.80", reasons)

    def test_bad_date(self):
        status, reasons = validate.validate(
            base_result(date="not-a-date"), today=date(2024, 6, 1)
        )
        self.assertIn("date is missing or not parseable", reasons)

    def test_implausible_date(self):
        status, reasons = validate.validate(
            base_result(date="1899-01-01"), today=date(2024, 6, 1)
        )
        self.assertIn("date is outside the plausible range", reasons)

    def test_missing_item_amount(self):
        result = base_result()
        result["items"][0]["amount"] = None
        status, reasons = validate.validate(result, today=date(2024, 6, 1))
        self.assertIn("one or more item amounts are missing", reasons)


if __name__ == "__main__":
    unittest.main()
