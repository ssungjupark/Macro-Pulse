import os
import sys
import unittest


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.app.cli import compose_telegram_report
from macro_pulse.config.report_formats import load_report_format_config
from macro_pulse.events import EconomicEvent
from macro_pulse.reporting.generator import generate_telegram_summary

from datetime import date


class OutputStructureTests(unittest.TestCase):
    def test_kr_summary_section_order(self):
        summary = generate_telegram_summary({}, "KR", load_report_format_config())
        headings = [
            "[국내 증시]",
            "[해외 증시]",
            "[변동성]",
            "[채권]",
            "[환율]",
            "[수급 및 시장 체력]",
        ]
        positions = [summary.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))

    def test_complete_kr_telegram_section_order(self):
        summary = generate_telegram_summary({}, "KR", load_report_format_config())
        report = compose_telegram_report(
            summary,
            [],
            ("[시장 해석]\n내용\n\n[핵심 이슈]\n내용\n\n[체크 포인트]\n내용"),
            [
                EconomicEvent(
                    date(2026, 9, 4),
                    "미국 고용보고서(NFP)",
                    "U.S. BLS",
                    "https://www.bls.gov",
                )
            ],
        )
        headings = [
            "[국내 증시]",
            "[해외 증시]",
            "[변동성]",
            "[채권]",
            "[환율]",
            "[수급 및 시장 체력]",
            "[주요 변동 신호]",
            "[시장 해석]",
            "[핵심 이슈]",
            "[주요 일정]",
            "[체크 포인트]",
        ]

        self.assertEqual(
            [report.index(heading) for heading in headings],
            sorted(report.index(heading) for heading in headings),
        )

    def test_us_summary_section_order(self):
        summary = generate_telegram_summary({}, "US", load_report_format_config())
        headings = [
            "[해외 증시]",
            "[변동성]",
            "[미국 국채]",
            "[원자재]",
            "[달러 및 환율]",
            "[암호화폐]",
        ]
        positions = [summary.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))

    def test_complete_us_telegram_section_order(self):
        summary = generate_telegram_summary({}, "US", load_report_format_config())
        report = compose_telegram_report(
            summary,
            [],
            None,
            [],
        )
        headings = [
            "[해외 증시]",
            "[변동성]",
            "[미국 국채]",
            "[원자재]",
            "[달러 및 환율]",
            "[암호화폐]",
            "[주요 변동 신호]",
            "[시장 해석]",
            "[핵심 이슈]",
            "[주요 일정]",
            "[체크 포인트]",
        ]

        self.assertEqual(
            [report.index(heading) for heading in headings],
            sorted(report.index(heading) for heading in headings),
        )


if __name__ == "__main__":
    unittest.main()
