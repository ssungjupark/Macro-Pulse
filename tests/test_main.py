import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.app import cli as app_main
from macro_pulse.events import EconomicEvent
from macro_pulse.domain.models import (
    AssetSnapshot,
    ModeFormatConfig,
    ReportFormatConfig,
    SummarySectionConfig,
)


class MainTests(unittest.IsolatedAsyncioTestCase):
    def test_resolve_mode_uses_explicit_override(self):
        self.assertEqual(app_main.resolve_mode("kr"), "KR")
        self.assertEqual(app_main.resolve_mode("US"), "US")

    def test_resolve_mode_uses_time_window_for_auto_mode(self):
        kr_time = datetime(2026, 3, 21, 8, tzinfo=timezone.utc)
        us_time = datetime(2026, 3, 21, 2, tzinfo=timezone.utc)

        self.assertEqual(app_main.resolve_mode("global", now_utc=kr_time), "KR")
        self.assertEqual(app_main.resolve_mode(None, now_utc=us_time), "US")

    def test_event_results_prefer_newest_release_over_older_fomc(self):
        events = [
            EconomicEvent(
                date(2026, 9, 16),
                "FOMC 금리 결정",
                "Federal Reserve",
                "https://www.federalreserve.gov/",
                100,
            ),
            EconomicEvent(
                date(2026, 9, 18),
                "BOJ 통화정책 결정",
                "Bank of Japan",
                "https://www.boj.or.jp/",
                90,
            ),
        ]

        with (
            patch(
                "macro_pulse.app.cli.build_recent_event_result_section",
                return_value="[발표 결과]\nBOJ 1.25%",
            ) as generic,
            patch(
                "macro_pulse.app.cli.build_recent_fomc_result_section",
                return_value="[발표 결과]\nFOMC",
            ) as fomc,
        ):
            result = app_main.build_event_results(events)

        self.assertIn("BOJ 1.25%", result)
        self.assertNotIn("FOMC", result)
        generic.assert_called_once()
        fomc.assert_not_called()

    def test_event_results_use_fomc_parser_when_fomc_is_newest(self):
        events = [
            EconomicEvent(
                date(2026, 9, 16),
                "FOMC 금리 결정",
                "Federal Reserve",
                "https://www.federalreserve.gov/",
                100,
            )
        ]

        with patch(
            "macro_pulse.app.cli.build_recent_fomc_result_section",
            return_value="[발표 결과]\nFOMC 3.75~4.00%",
        ) as fomc:
            result = app_main.build_event_results(events)

        self.assertIn("FOMC 3.75~4.00%", result)
        fomc.assert_called_once()

    async def test_main_dry_run_generates_report_without_notifications(self):
        data = {
            "indices_overseas": [
                AssetSnapshot(name="S&P 500", price=5100.25, change_pct=0.42)
            ]
        }
        config = ReportFormatConfig(
            modes={
                "US": ModeFormatConfig(
                    summary_sections=[
                        SummarySectionConfig(
                            title="해외 증시",
                            category="indices_overseas",
                            items=["S&P 500"],
                        )
                    ],
                    screenshot_targets=["finviz"],
                )
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "macro_pulse_report.html"
            with (
                patch(
                    "macro_pulse.app.cli.fetch_all_data", return_value=data
                ) as fetch_data,
                patch(
                    "macro_pulse.app.cli.load_report_format_config",
                    return_value=config,
                ),
                patch(
                    "macro_pulse.app.cli.generate_html_report",
                    return_value="<html>report</html>",
                ) as html_report,
                patch(
                    "macro_pulse.app.cli.generate_telegram_summary",
                    return_value="summary",
                ) as telegram_summary,
                patch(
                    "macro_pulse.app.cli.analyze_market",
                    return_value="[오늘의 핵심 이슈]\n없음",
                ),
                patch("macro_pulse.app.cli.get_upcoming_events", return_value=[]),
                patch(
                    "macro_pulse.app.cli.send_telegram_report",
                    new_callable=AsyncMock,
                ) as telegram,
            ):
                previous_cwd = os.getcwd()
                os.chdir(temp_dir)
                try:
                    exit_code = await app_main.main(["--dry-run", "--market", "US"])
                finally:
                    os.chdir(previous_cwd)

            self.assertEqual(exit_code, 0)
            fetch_data.assert_called_once_with("US")
            self.assertTrue(output_path.exists())
            self.assertEqual(
                output_path.read_text(encoding="utf-8"), "<html>report</html>"
            )
            html_report.assert_called_once_with(data)
            telegram_summary.assert_called_once_with(data, "US", config)
            telegram.assert_not_awaited()

    async def test_main_fails_when_telegram_delivery_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("macro_pulse.app.cli.fetch_all_data", return_value={}),
                patch("macro_pulse.app.cli.generate_html_report", return_value="html"),
                patch(
                    "macro_pulse.app.cli.generate_telegram_summary",
                    return_value="summary",
                ),
                patch(
                    "macro_pulse.app.cli.analyze_market",
                    return_value="[오늘의 핵심 이슈]\n없음",
                ),
                patch("macro_pulse.app.cli.get_upcoming_events", return_value=[]),
                patch("macro_pulse.app.cli.capture_screenshots", return_value=[]),
                patch(
                    "macro_pulse.app.cli.send_telegram_report",
                    new_callable=AsyncMock,
                    return_value=False,
                ),
                patch.dict(
                    os.environ,
                    {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
                ),
            ):
                previous_cwd = os.getcwd()
                os.chdir(temp_dir)
                try:
                    with self.assertRaisesRegex(RuntimeError, "delivery failed"):
                        await app_main.main(["--market", "US"])
                finally:
                    os.chdir(previous_cwd)
