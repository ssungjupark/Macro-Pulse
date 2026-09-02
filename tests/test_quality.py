import os
import sys
import unittest
from datetime import date


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.data.quality import (
    calculate_period_change,
    calculate_return_z_score,
    is_stale_as_of,
    validate_value,
)
from macro_pulse.domain.models import ValueFormat


class DataQualityTests(unittest.TestCase):
    def test_period_change_uses_percent_for_assets_and_bp_for_yields(self):
        asset_values = [100, 101, 102, 103, 104, 110]
        yield_values = [4.0, 4.01, 4.02, 4.03, 4.04, 4.10]

        self.assertAlmostEqual(
            calculate_period_change(asset_values, 5, ValueFormat.STANDARD_2),
            10.0,
        )
        self.assertAlmostEqual(
            calculate_period_change(yield_values, 5, ValueFormat.YIELD_3),
            10.0,
        )

    def test_z_score_needs_twenty_completed_returns(self):
        self.assertIsNone(calculate_return_z_score(list(range(1, 21))))
        self.assertIsNotNone(calculate_return_z_score(list(range(1, 22))))

    def test_stale_and_abnormal_values_are_detected(self):
        self.assertTrue(is_stale_as_of("2026-08-20", today=date(2026, 9, 2)))
        self.assertFalse(is_stale_as_of("2026-09-01", today=date(2026, 9, 2)))
        self.assertIsNotNone(validate_value("DXY", 500.0))
        self.assertIsNone(validate_value("DXY", 102.3))


if __name__ == "__main__":
    unittest.main()
