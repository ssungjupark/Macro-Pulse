import json
import os
import sys
import tempfile
import unittest


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.config.report_formats import (
    get_screenshot_targets,
    load_report_format_config,
)
from macro_pulse.reporting.generator import generate_telegram_summary


class ReportFormatConfigTests(unittest.TestCase):
    def test_default_config_defines_expected_screenshot_targets(self):
        config = load_report_format_config()

        self.assertEqual(get_screenshot_targets("KR", config), ["kospi", "kosdaq"])
        self.assertEqual(get_screenshot_targets("US", config), ["finviz"])

    def test_generate_telegram_summary_uses_external_config_order(self):
        custom_config = {
            "modes": {
                "US": {
                    "summary_sections": [
                        {
                            "title": "암호화폐 우선",
                            "category": "crypto",
                            "items": ["Ethereum", "Bitcoin"],
                        },
                        {
                            "title": "유럽 증시",
                            "category": "indices_overseas",
                            "items": ["Euro Stoxx 50"],
                        },
                    ],
                    "screenshot_targets": ["finviz"],
                }
            }
        }

        data = {
            "crypto": [
                {"name": "Bitcoin", "price": 71554.51, "change_pct": 4.61},
                {"name": "Ethereum", "price": 2082.61, "change_pct": 4.50},
            ],
            "indices_overseas": [
                {"name": "Euro Stoxx 50", "price": 5833.45, "change_pct": 2.61}
            ],
        }

        summary = generate_telegram_summary(data, "US", custom_config)

        self.assertEqual(
            summary,
            "\n".join(
                [
                    "[암호화폐 우선]",
                    "Ethereum: 2,082.61 (+4.50%)",
                    "Bitcoin: 71,554.51 (+4.61%)",
                    "",
                    "[유럽 증시]",
                    "Euro Stoxx 50: 5,833.45 (+2.61%)",
                ]
            ),
        )

    def test_load_report_format_config_accepts_explicit_path(self):
        custom_config = {
            "modes": {
                "KR": {
                    "summary_sections": [],
                    "screenshot_targets": ["kospi"],
                }
            }
        }

        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(custom_config, handle)
            config_path = handle.name

        try:
            loaded_config = load_report_format_config(config_path)
            self.assertEqual(get_screenshot_targets("KR", loaded_config), ["kospi"])
        finally:
            os.remove(config_path)


if __name__ == "__main__":
    unittest.main()
