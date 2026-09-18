import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.workflows.delivery_context import resolve_delivery_context


class DeliveryContextTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(
            (Path(__file__).parents[1] / "config/report_formats.json").read_text()
        )

    def test_primary_and_backups_share_market_and_session_key(self):
        for mode, hour in (("KR", 12), ("US", 23)):
            schedule = self.config["modes"][mode]["workflow_schedule"]
            crons = [schedule["cron"], *(b["cron"] for b in schedule["backups"])]
            contexts = [
                resolve_delivery_context(
                    self.config,
                    "schedule",
                    cron,
                    now=datetime(2026, 9, 7, hour, tzinfo=timezone.utc),
                )
                for cron in crons
            ]
            self.assertEqual({item["market"] for item in contexts}, {mode})
            self.assertEqual(len({item["cache_key"] for item in contexts}), 1)

    def test_kr_delay_past_korean_midnight_does_not_change_date_or_market(self):
        timely = resolve_delivery_context(
            self.config,
            "schedule",
            "40 06 * * 1-5",
            now=datetime(2026, 9, 7, 7, tzinfo=timezone.utc),
        )
        delayed = resolve_delivery_context(
            self.config,
            "schedule",
            "10 07 * * 1-5",
            now=datetime(2026, 9, 7, 21, tzinfo=timezone.utc),
        )
        self.assertEqual(timely, delayed)
        self.assertEqual(delayed["report_date"], "2026-09-07")

    def test_us_friday_session_delayed_to_saturday_keeps_saturday_report_date(self):
        context = resolve_delivery_context(
            self.config,
            "schedule",
            "00 22 * * 1-5",
            now=datetime(2026, 9, 5, 10, tzinfo=timezone.utc),
        )
        self.assertEqual(context["market"], "US")
        self.assertEqual(context["report_date"], "2026-09-05")

    def test_unknown_scheduled_cron_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown scheduled cron"):
            resolve_delivery_context(self.config, "schedule", "unknown")

    def test_manual_market_override_is_preserved(self):
        context = resolve_delivery_context(
            self.config,
            "workflow_dispatch",
            manual_market="KR",
            now=datetime(2026, 9, 8, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(context["market"], "KR")
