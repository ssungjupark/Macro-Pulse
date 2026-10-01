import os
import sys
import unittest
from datetime import datetime, timezone


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.workflows.delivery_context import resolve_delivery_context


class DeliveryContextTests(unittest.TestCase):
    def test_kr_primary_and_backups_share_cache_key(self):
        now = datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc)
        contexts = [
            resolve_delivery_context("schedule", cron, now=now)
            for cron in (
                "30 07 * * 1-5",
                "45 07 * * 1-5",
                "00 08 * * 1-5",
            )
        ]
        self.assertEqual({item["market"] for item in contexts}, {"KR"})
        self.assertEqual(len({item["cache_key"] for item in contexts}), 1)
        self.assertEqual(contexts[0]["report_date"], "2026-09-30")

    def test_us_primary_and_backups_share_cache_key(self):
        now = datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
        contexts = [
            resolve_delivery_context("schedule", cron, now=now)
            for cron in (
                "30 21 * * 1-5",
                "45 21 * * 1-5",
                "00 22 * * 1-5",
            )
        ]
        self.assertEqual({item["market"] for item in contexts}, {"US"})
        self.assertEqual(len({item["cache_key"] for item in contexts}), 1)
        self.assertEqual(contexts[0]["report_date"], "2026-10-01")

    def test_kr_delay_past_korean_midnight_keeps_original_session_date(self):
        context = resolve_delivery_context(
            "schedule",
            "00 08 * * 1-5",
            now=datetime(2026, 9, 30, 21, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(context["market"], "KR")
        self.assertEqual(context["report_date"], "2026-09-30")

    def test_us_friday_session_delayed_to_saturday_keeps_saturday_report_date(self):
        context = resolve_delivery_context(
            "schedule",
            "00 22 * * 1-5",
            now=datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(context["market"], "US")
        self.assertEqual(context["report_date"], "2026-10-03")

    def test_external_dispatch_uses_current_kst_date(self):
        context = resolve_delivery_context(
            "workflow_dispatch",
            manual_market="KR",
            now=datetime(2026, 10, 1, 7, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(context["report_date"], "2026-10-01")
        self.assertEqual(context["cache_key"], "macro-pulse-sent-v2-KR-2026-10-01")

    def test_unknown_schedule_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown scheduled cron"):
            resolve_delivery_context(
                "schedule",
                "10 10 * * 1-5",
                now=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
