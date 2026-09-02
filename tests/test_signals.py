import os
import sys
import unittest


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.domain.models import AssetSnapshot, ValueFormat
from macro_pulse.signals import detect_signals


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


if __name__ == "__main__":
    unittest.main()
