import json
import unittest
from pathlib import Path

import review_gate


ROOT = Path(__file__).resolve().parents[1]


class ReviewGateTests(unittest.TestCase):
    def test_report_summary_for_reviews_fixture(self):
        with (ROOT / "reviews.json").open(encoding="utf-8") as f:
            reviews = json.load(f)

        report = review_gate.run_report(reviews)

        self.assertEqual(
            report["summary"],
            {
                "status_counts": {
                    "Abgelehnt": 10,
                    "Review": 3,
                    "Freigegeben": 7,
                },
                "review_ids": ["r-2009", "r-2010", "r-2016"],
            },
        )

    def test_classify_handles_manual_review_and_low_value_cases(self):
        self.assertEqual(
            review_gate.classify({"id": "empty", "comment": None, "lang": "de"}),
            {"status": "Abgelehnt", "reason": "Kein SEO-/AEO-Nutzen"},
        )
        self.assertEqual(
            review_gate.classify(
                {
                    "id": "foreign",
                    "comment": "Smells great but does not suit oily skin.",
                    "lang": "en",
                }
            ),
            {
                "status": "Review",
                "reason": "Fremdsprache - manuelle Nachbearbeitung",
            },
        )

    def test_classify_rejects_service_and_counterfeit_claims(self):
        self.assertEqual(
            review_gate.classify(
                {
                    "id": "service",
                    "comment": "Die Lieferung hat viel zu lange gedauert.",
                    "lang": "de",
                }
            ),
            {"status": "Abgelehnt", "reason": "Service-Mangel"},
        )
        self.assertEqual(
            review_gate.classify(
                {
                    "id": "counterfeit",
                    "comment": "Das riecht wie eine billige Fälschung.",
                    "lang": "de",
                }
            ),
            {"status": "Abgelehnt", "reason": "Fälschungsvorwurf"},
        )

    def test_formal_correction_is_minimal_for_approved_reviews(self):
        result = review_gate.classify(
            {
                "id": "approved",
                "comment": "Nr.3 passt gut unter Make up und enthält 30ml.",
                "lang": "de",
            }
        )

        self.assertEqual(result["status"], "Freigegeben")
        self.assertEqual(
            result["corrected_comment"],
            "Nr. 3 passt gut unter Make-up und enthält 30 ml.",
        )

    def test_formal_correction_is_not_added_to_rejected_reviews(self):
        result = review_gate.classify(
            {
                "id": "rejected",
                "comment": "Die Lieferung mit 30ml Produkt hat ewig gedauert.",
                "lang": "de",
            }
        )

        self.assertEqual(result, {"status": "Abgelehnt", "reason": "Service-Mangel"})


if __name__ == "__main__":
    unittest.main()
