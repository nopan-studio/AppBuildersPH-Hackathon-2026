import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookyp import cli


class CliFlagTests(unittest.TestCase):
    def test_scan_defaults(self):
        args = cli.build_parser().parse_args(["scan", "receipt.jpg"])
        self.assertEqual(args.model, "qwen3:1.7b")
        self.assertEqual(args.ocr_tier, "small")
        self.assertEqual(args.min_conf, 0.80)

    def test_ocr_tier_choices(self):
        for tier in ("tiny", "small", "medium"):
            args = cli.build_parser().parse_args(
                ["scan", "receipt.jpg", "--ocr-tier", tier]
            )
            self.assertEqual(args.ocr_tier, tier)


if __name__ == "__main__":
    unittest.main()
