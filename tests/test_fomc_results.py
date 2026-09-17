import os
import sys
import unittest
from datetime import date


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.fomc_results import parse_fomc_statement


class FomcResultTests(unittest.TestCase):
    def test_parse_rate_hike_statement(self):
        text = (
            "The Committee decided to raise the target range for the federal "
            "funds rate by 1/4 percentage point to 3-3/4 to 4 percent, in "
            "support of the Federal Reserve's dual mandate. The Committee "
            "approved the following statement for release by a 12 – 0 vote."
        )

        result = parse_fomc_statement(
            text,
            date(2026, 9, 16),
            "https://www.federalreserve.gov/test",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["lower"], 3.75)
        self.assertEqual(result["upper"], 4.00)
        self.assertEqual(result["previous_lower"], 3.50)
        self.assertEqual(result["previous_upper"], 3.75)
        self.assertEqual(result["change_bp"], 25)
        self.assertEqual(result["vote"], "12-0")


if __name__ == "__main__":
    unittest.main()
