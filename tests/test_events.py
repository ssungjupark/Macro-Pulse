import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.events import (
    EconomicEvent,
    get_upcoming_events,
    insert_event_section,
    parse_bls_ics,
)


class EventTests(unittest.TestCase):
    def test_parse_bls_calendar_keeps_only_target_releases(self):
        content = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260904T083000
SUMMARY:Employment Situation for August 2026
END:VEVENT
BEGIN:VEVENT
DTSTART:20260911T083000
SUMMARY:Consumer Price Index for August 2026
END:VEVENT
BEGIN:VEVENT
DTSTART:20260912T083000
SUMMARY:Unrelated release
END:VEVENT
END:VCALENDAR"""

        events = parse_bls_ics(content)

        self.assertEqual(
            [item.title for item in events], ["미국 고용보고서(NFP)", "미국 CPI"]
        )

    @patch("macro_pulse.events._fetch_bls_events", return_value=[])
    def test_upcoming_events_require_valid_dates_and_source_urls(self, _mock_bls):
        payload = {
            "events": [
                {
                    "date": "2026-09-16",
                    "title": "FOMC 금리 결정",
                    "source": "Federal Reserve",
                    "source_url": "https://www.federalreserve.gov/test",
                },
                {
                    "date": "invalid",
                    "title": "잘못된 일정",
                    "source": "unknown",
                    "source_url": "https://example.com",
                },
                {
                    "date": "2026-09-17",
                    "title": "검증되지 않은 일정",
                    "source": "unknown",
                    "source_url": "https://example.com/calendar",
                },
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            events = get_upcoming_events(date(2026, 9, 2), config_path=path, limit=3)

        self.assertEqual(events[0].title, "FOMC 금리 결정")
        self.assertNotIn("검증되지 않은 일정", [item.title for item in events])
        self.assertLessEqual(len(events), 3)

    def test_event_section_is_inserted_before_check_points(self):
        analysis = "[시장 해석]\n내용\n\n[체크 포인트]\n내용"
        events = [
            EconomicEvent(
                date(2026, 9, 4), "미국 고용보고서(NFP)", "U.S. BLS", "https://bls.gov"
            )
        ]

        result = insert_event_section(analysis, events)

        self.assertLess(result.index("[주요 일정]"), result.index("[체크 포인트]"))


if __name__ == "__main__":
    unittest.main()
