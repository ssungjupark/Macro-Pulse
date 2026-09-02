import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.app import cli as app_main
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
                patch("macro_pulse.app.cli.fetch_all_data", return_value=data),
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
                    return_value="[시장 해석]\n없음\n\n[체크 포인트]\n없음",
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
            self.assertTrue(output_path.exists())
            self.assertEqual(
                output_path.read_text(encoding="utf-8"), "<html>report</html>"
            )
            html_report.assert_called_once_with(data)
            telegram_summary.assert_called_once_with(data, "US", config)
            telegram.assert_not_awaited()
