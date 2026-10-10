import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookyp import ocr


class SortAndMergeTests(unittest.TestCase):
    def test_merges_fragments_on_same_row(self):
        lines = [
            ocr.OcrLine("Item", 0.9, (10, 10, 60, 30)),
            ocr.OcrLine("Price", 0.8, (100, 12, 150, 32)),
            ocr.OcrLine("Total", 0.7, (10, 60, 60, 80)),
        ]
        merged = ocr.sort_and_merge(lines)
        self.assertEqual(merged, ["Item Price", "Total"])

    def test_orders_rows_top_to_bottom(self):
        lines = [
            ocr.OcrLine("second", 0.9, (10, 100, 80, 120)),
            ocr.OcrLine("first", 0.9, (10, 40, 80, 60)),
        ]
        self.assertEqual(ocr.sort_and_merge(lines), ["first", "second"])

    def test_orders_columns_left_to_right(self):
        lines = [
            ocr.OcrLine("B", 0.9, (200, 10, 250, 30)),
            ocr.OcrLine("A", 0.9, (10, 10, 60, 30)),
        ]
        self.assertEqual(ocr.sort_and_merge(lines), ["A B"])

    def test_empty(self):
        self.assertEqual(ocr.sort_and_merge([]), [])

    def test_mean_confidence(self):
        lines = [
            ocr.OcrLine("a", 0.9, (0, 0, 1, 1)),
            ocr.OcrLine("b", 0.7, (0, 2, 1, 3)),
        ]
        self.assertAlmostEqual(ocr.mean_confidence(lines), 0.8)
        self.assertEqual(ocr.mean_confidence([]), 0.0)


if __name__ == "__main__":
    unittest.main()
