import json
import os
import sys
import tempfile
import unittest


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.config.report_formats import (
    get_screenshot_targets,
    get_workflow_schedule,
    load_report_format_config,
)
from macro_pulse.reporting.generator import generate_telegram_summary
from macro_pulse.workflows.schedule_sync import (
    render_daily_workflow_schedule_block,
    workflow_matches_config,
)


class ReportFormatConfigTests(unittest.TestCase):
    def test_default_config_defines_expected_screenshot_targets(self):
        config = load_report_format_config()

        self.assertEqual(get_screenshot_targets("KR", config), ["kospi", "kosdaq"])
        self.assertEqual(get_screenshot_targets("US", config), ["finviz"])

    def test_default_config_defines_expected_workflow_schedules(self):
        config = load_report_format_config()

        kr_schedule = get_workflow_schedule("KR", config)
        us_schedule = get_workflow_schedule("US", config)

        self.assertEqual(kr_schedule.cron, "30 07 * * 1-5")
        self.assertEqual(kr_schedule.local_time, "16:30 KST")
        self.assertEqual(kr_schedule.weekdays, "Mon-Fri")

        self.assertEqual(us_schedule.cron, "30 21 * * 1-5")
        self.assertEqual(us_schedule.local_time, "06:30 KST")
        self.assertEqual(us_schedule.weekdays, "Tue-Sat KST")

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
                    "workflow_schedule": {
                        "cron": "30 21 * * 1-5",
                        "local_time": "06:30 KST",
                        "utc_time": "21:30 UTC",
                        "weekdays": "Tue-Sat KST",
                    },
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
                    "workflow_schedule": {
                        "cron": "00 08 * * 1-5",
                        "local_time": "17:00 KST",
                        "utc_time": "08:00 UTC",
                        "weekdays": "Mon-Fri",
                    },
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

    def test_daily_report_workflow_schedule_block_matches_config(self):
        config = load_report_format_config()
        workflow_path = os.path.join(
            os.path.dirname(__file__), "../.github/workflows/daily_report.yml"
        )

        with open(workflow_path, "r", encoding="utf-8") as handle:
            workflow_text = handle.read()

        self.assertTrue(workflow_matches_config(workflow_text, config))
        self.assertIn("# KR | 16:30 KST | 07:30 UTC | Mon-Fri", workflow_text)
        self.assertEqual(
            render_daily_workflow_schedule_block(config),
            "\n".join(
                [
                    "    # BEGIN GENERATED SCHEDULES",
                    "    # KR | 16:30 KST | 07:30 UTC | Mon-Fri",
                    "    - cron: '30 07 * * 1-5'",
                    "    # US | 06:30 KST | 21:30 UTC | Tue-Sat KST",
                    "    - cron: '30 21 * * 1-5'",
                    "    # END GENERATED SCHEDULES",
                ]
            ),
        )
        self.assertIn("Report market mode", workflow_text)
        self.assertIn("- AUTO", workflow_text)
        self.assertIn("- KR", workflow_text)
        self.assertIn("- US", workflow_text)


if __name__ == "__main__":
    unittest.main()
