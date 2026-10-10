import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookyp import pipeline


class FloatParsingTests(unittest.TestCase):
    def test_plain_numbers(self):
        self.assertEqual(pipeline._to_float(3), 3.0)
        self.assertEqual(pipeline._to_float(3.5), 3.5)

    def test_currency_and_separators(self):
        self.assertEqual(pipeline._to_float("$1,234.56"), 1234.56)
        self.assertEqual(pipeline._to_float("1.234,56"), 1234.56)
        self.assertEqual(pipeline._to_float("12,50"), 12.50)

    def test_negative_in_parentheses(self):
        self.assertEqual(pipeline._to_float("(4.00)"), -4.0)

    def test_garbage(self):
        self.assertIsNone(pipeline._to_float("abc"))
        self.assertIsNone(pipeline._to_float(None))
        self.assertIsNone(pipeline._to_float(True))


class CurrencyTests(unittest.TestCase):
    def test_keeps_code_present_in_text(self):
        self.assertEqual(
            pipeline._normalize_currency("usd", "Total USD 5.00"), "USD"
        )

    def test_keeps_unambiguous_symbol(self):
        self.assertEqual(
            pipeline._normalize_currency("EUR", "Total \u20ac5.00"), "EUR"
        )

    def test_drops_ungrounded_code(self):
        # model guesses USD, but the receipt shows neither code nor symbol
        self.assertIsNone(
            pipeline._normalize_currency("USD", "TOTAL P505.00")
        )

    def test_drops_ambiguous_symbols(self):
        self.assertIsNone(pipeline._normalize_currency("$"))
        self.assertIsNone(pipeline._normalize_currency("P"))
        self.assertIsNone(pipeline._normalize_currency("US Dollars"))
        self.assertIsNone(pipeline._normalize_currency(None))


class NormalizeTests(unittest.TestCase):
    def test_normalizes_model_output(self):
        result = pipeline.empty_result("r.jpg")
        pipeline._normalize(
            result,
            {
                "merchant": "  Shop  ",
                "date": "2024-03-05",
                "currency": None,
                "items": [
                    {"name": "Milk", "qty": "2", "unit_price": "$1.50", "amount": "3.00"},
                    {"name": "  ", "qty": None, "unit_price": None, "amount": None},
                ],
                "subtotal": "3.00",
                "tax": "0.25",
                "total": "3.25",
            },
        )
        self.assertEqual(result["merchant"], "Shop")
        self.assertIsNone(result["currency"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["qty"], 2)
        self.assertEqual(result["items"][0]["unit_price"], 1.5)
        self.assertEqual(result["total"], 3.25)


if __name__ == "__main__":
    unittest.main()
