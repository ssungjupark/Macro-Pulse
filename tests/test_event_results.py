import os
import sys
import unittest
from datetime import date


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.event_results import (
    _format_result_block,
    _match_expectations,
    insert_event_result_section,
)
from macro_pulse.events import EconomicEvent


class EventResultTests(unittest.TestCase):
    def test_insert_result_before_upcoming_events(self):
        analysis = (
            "[시장 해석]\n내용\n\n"
            "[주요 일정]\n- 09/18 BOJ 통화정책 결정\n\n"
            "[체크 포인트]\n내용"
        )
        result_section = (
            "[발표 결과]\n"
            "FOMC 금리 결정\n"
            "• 정책금리: 실제 4.25% / 예상 4.25% / 이전 4.50%"
        )

        result = insert_event_result_section(analysis, result_section)

        self.assertLess(result.index("[발표 결과]"), result.index("[주요 일정]"))
        self.assertIn("실제 4.25% / 예상 4.25% / 이전 4.50%", result)

    def test_match_expectations_uses_event_date_and_country(self):
        event = EconomicEvent(
            date(2026, 9, 11),
            "미국 CPI",
            "U.S. BLS",
            "https://www.bls.gov/",
        )
        spec = {
            "country": "USD",
            "metrics": (
                ("헤드라인 CPI MoM", "CPI m/m"),
                ("근원 CPI MoM", "Core CPI m/m"),
            ),
        }
        entries = [
            {
                "country": "USD",
                "title": "CPI m/m",
                "date": "2026-09-11T08:30:00-04:00",
                "forecast": "0.4%",
                "previous": "0.1%",
            },
            {
                "country": "USD",
                "title": "Core CPI m/m",
                "date": "2026-09-11T08:30:00-04:00",
                "forecast": "0.2%",
                "previous": "0.2%",
            },
        ]

        rows = _match_expectations(event, spec, entries)

        self.assertEqual(rows[0]["forecast"], "0.4%")
        self.assertEqual(rows[0]["previous"], "0.1%")
        self.assertEqual(rows[1]["forecast"], "0.2%")

    def test_format_result_block_outputs_actual_forecast_previous(self):
        event = EconomicEvent(
            date(2026, 9, 11),
            "미국 CPI",
            "U.S. BLS",
            "https://www.bls.gov/",
        )
        spec = {"display": "8월 미국 CPI"}
        result = {
            "title": "8월 미국 CPI",
            "metrics": [
                {
                    "label": "헤드라인 CPI MoM",
                    "actual": "+0.4%",
                    "forecast": "+0.4%",
                    "previous": "+0.1%",
                },
                {
                    "label": "근원 CPI MoM",
                    "actual": "+0.3%",
                    "forecast": "+0.2%",
                    "previous": "+0.2%",
                },
            ],
            "summary": "근원 CPI가 예상치를 상회해 금리 민감 자산에 부담 요인입니다.",
            "sources": ["Reuters", "U.S. Bureau of Labor Statistics"],
        }

        rendered = _format_result_block(event, spec, result)

        self.assertIn("8월 미국 CPI", rendered)
        self.assertIn("실제 +0.4% / 예상 +0.4% / 이전 +0.1%", rendered)
        self.assertIn("실제 +0.3% / 예상 +0.2% / 이전 +0.2%", rendered)
        self.assertIn("Reuters", rendered)


if __name__ == "__main__":
    unittest.main()
