import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - optional web deps
    TestClient = None


@unittest.skipIf(TestClient is None, "fastapi not installed")
class ApiTests(unittest.TestCase):
    def setUp(self):
        from bookyp import api, extract

        self.api = api
        self.extract = extract
        self.client = TestClient(api.app)

    def test_health_reports_ollama_status(self):
        original = self.extract.check_ollama
        self.extract.check_ollama = lambda model=None: (True, "ok")
        try:
            response = self.client.get("/api/health")
        finally:
            self.extract.check_ollama = original
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_scan_rejects_unknown_tier(self):
        response = self.client.post(
            "/api/scan",
            data={"ocr_tier": "huge"},
            files={"files": ("a.png", b"x", "image/png")},
        )
        self.assertEqual(response.status_code, 400)

    def test_export_returns_spreadsheet(self):
        payload = {
            "results": [
                {
                    "file": "r.jpg",
                    "items": [{"name": "x", "qty": 1, "unit_price": 1.0, "amount": 1.0}],
                    "status": "accepted",
                    "review_reasons": [],
                }
            ]
        }
        response = self.client.post("/api/export", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertGreater(len(response.content), 0)


if __name__ == "__main__":
    unittest.main()
