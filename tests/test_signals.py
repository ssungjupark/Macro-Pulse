import os
import sys
import unittest


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.domain.models import AssetSnapshot, ValueFormat
from macro_pulse.signals import detect_signals, select_representative_signals


class SignalTests(unittest.TestCase):
    def test_treasury_move_at_five_bp_emits_signal(self):
        data = {
            "treasuries": [
                AssetSnapshot(
                    name="US 2Y Treasury",
                    price=4.2,
                    change=0.05,
                    value_format=ValueFormat.YIELD_3,
                )
            ]
        }

        signals = detect_signals(data)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["move"], "+5.0bp")

    def test_treasury_move_below_five_bp_does_not_emit_signal(self):
        data = {
            "treasuries": [
                AssetSnapshot(
                    name="US 30Y Treasury",
                    price=4.8,
                    change=-0.049,
                    value_format=ValueFormat.YIELD_3,
                )
            ]
        }

        self.assertEqual(detect_signals(data), [])

    def test_representative_signals_limit_correlated_groups(self):
        signals = [
            {"name": "Nasdaq", "score": 5.0},
            {"name": "SOX", "score": 4.0},
            {"name": "S&P 500", "score": 3.0},
            {"name": "EUR/KRW", "score": 2.0},
            {"name": "CNY/KRW", "score": 1.9},
            {"name": "WTI", "score": 1.8},
        ]

        selected = select_representative_signals(signals)
        names = [item["name"] for item in selected]

        self.assertEqual(names[:2], ["Nasdaq", "SOX"])
        self.assertNotIn("S&P 500", names)
        self.assertIn("EUR/KRW", names)
        self.assertNotIn("CNY/KRW", names)
        self.assertIn("WTI", names)


if __name__ == "__main__":
    unittest.main()
