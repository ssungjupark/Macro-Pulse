import copy
import os
import sys
import unittest


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.domain.models import (
    AssetSnapshot,
    ModeFormatConfig,
    ReportFormatConfig,
    SummarySectionConfig,
    ValueFormat,
)
from macro_pulse.reporting.generator import (
    generate_html_report,
    generate_telegram_summary,
)


class ReportGeneratorTests(unittest.TestCase):
    def test_generate_html_report_does_not_mutate_mapping_input(self):
        data = {
            "commodities_rates": [
                {
                    "name": "US 10Y Treasury",
                    "price": 4.321,
                    "change": -0.012,
                    "change_pct": -0.28,
                    "history": [4.28, 4.31, 4.30, 4.29, 4.32, 4.33, 4.321],
                }
            ]
        }
        original = copy.deepcopy(data)

        html = generate_html_report(data)

        self.assertIn("4.321", html)
        self.assertEqual(data, original)

    def test_generate_telegram_summary_uses_explicit_value_format(self):
        data = {
            "commodities_rates": [
                AssetSnapshot(
                    name="US 10Y Treasury",
                    price=4.321,
                    change=-0.012,
                    change_pct=-0.28,
                    value_format=ValueFormat.YIELD_3,
                )
            ]
        }
        config = ReportFormatConfig(
            modes={
                "US": ModeFormatConfig(
                    summary_sections=[
                        SummarySectionConfig(
                            title="채권",
                            category="commodities_rates",
                            items=["US 10Y Treasury"],
                        )
                    ]
                )
            }
        )

        summary = generate_telegram_summary(data, "US", config)

        self.assertEqual(summary, "[채권]\nUS 10Y Treasury: 4.321% (-1.2bp)")

    def test_us_treasury_section_includes_spread_and_curve_interpretation(self):
        data = {
            "treasuries": [
                AssetSnapshot(
                    name="US 2Y Treasury", price=4.20,
                    change=-0.08, value_format=ValueFormat.YIELD_3,
                ),
                AssetSnapshot(
                    name="US 10Y Treasury", price=4.50,
                    change=0.00, value_format=ValueFormat.YIELD_3,
                ),
                AssetSnapshot(
                    name="US 10Y-2Y Spread", price=30.0,
                    change=8.0, value_format=ValueFormat.BASIS_POINTS_1,
                ),
            ]
        }
        config = ReportFormatConfig(
            modes={
                "US": ModeFormatConfig(
                    summary_sections=[
                        SummarySectionConfig(
                            title="미국 국채",
                            category="treasuries",
                            items=[
                                "US 2Y Treasury",
                                "US 10Y Treasury",
                                "US 10Y-2Y Spread",
                            ],
                        )
                    ]
                )
            }
        )

        summary = generate_telegram_summary(data, "US", config)

        self.assertIn("US 10Y-2Y Spread: 30.0bp (+8.0bp)", summary)
        self.assertIn("금리 커브: 정상 우상향", summary)
        self.assertIn("전일보다 가팔라짐", summary)
