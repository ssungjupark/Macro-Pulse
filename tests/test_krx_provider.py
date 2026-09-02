import os
import sys
import unittest


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.data.providers.krx import (
    _build_breadth,
    _build_investor_flow,
    _build_program_flow,
    _build_sector_leaders,
    won_to_100m,
)


class KrxProviderTests(unittest.TestCase):
    def test_won_to_100m_preserves_sign_and_unit(self):
        self.assertEqual(won_to_100m("-1,250,000,000,000"), -12500.0)
        self.assertEqual(won_to_100m("350,000,000"), 3.5)

    def test_investor_flow_uses_krx_net_buy_value(self):
        rows = [
            {"INVST_TP_NM": "외국인", "NETBID_TRDVAL": "-1,000,000,000"},
            {"INVST_TP_NM": "기관합계", "NETBID_TRDVAL": "2,000,000,000"},
        ]

        snapshots = _build_investor_flow(
            "KOSPI", rows, "2026-09-02", "2026-09-02T08:00:00+00:00"
        )

        by_name = {item.name: item.price for item in snapshots}
        self.assertEqual(by_name["외국인 KOSPI 현물"], -10.0)
        self.assertEqual(by_name["기관 KOSPI 현물"], 20.0)

    def test_market_breadth_counts_direction_and_turnover(self):
        rows = [
            {"CMPPREVDD_PRC": "100", "ACC_TRDVAL": "200,000,000"},
            {"CMPPREVDD_PRC": "-20", "ACC_TRDVAL": "300,000,000"},
            {"CMPPREVDD_PRC": "0", "ACC_TRDVAL": "100,000,000"},
        ]

        snapshots = _build_breadth(
            "KOSPI", rows, "2026-09-02", "2026-09-02T08:00:00+00:00"
        )
        by_name = {item.name: item.price for item in snapshots}

        self.assertEqual(by_name["KOSPI 상승 종목"], 1)
        self.assertEqual(by_name["KOSPI 하락 종목"], 1)
        self.assertEqual(by_name["KOSPI 거래대금"], 6.0)

    def test_program_flow_uses_won_to_100m_conversion(self):
        rows = [
            {"ITM_TP_NM": "차익", "NETBID_TRDVAL": "-300,000,000"},
            {"ITM_TP_NM": "비차익", "NETBID_TRDVAL": "2,500,000,000"},
        ]

        snapshots = _build_program_flow(rows, "2026-09-02", "2026-09-02T08:00:00+00:00")
        by_name = {item.name: item.price for item in snapshots}

        self.assertEqual(by_name["프로그램 차익"], -3.0)
        self.assertEqual(by_name["프로그램 비차익"], 25.0)

    def test_sector_leaders_select_top_and_bottom_three(self):
        rows = [
            ("KOSPI", {"IDX_NM": "음식료품", "FLUC_RT": "1.2"}),
            ("KOSPI", {"IDX_NM": "전기전자", "FLUC_RT": "3.0"}),
            ("KOSPI", {"IDX_NM": "화학", "FLUC_RT": "0.5"}),
            ("KOSDAQ", {"IDX_NM": "반도체", "FLUC_RT": "-1.1"}),
            ("KOSDAQ", {"IDX_NM": "제약", "FLUC_RT": "-2.0"}),
            ("KOSDAQ", {"IDX_NM": "오락문화", "FLUC_RT": "-3.2"}),
            ("KOSPI", {"IDX_NM": "KOSPI 200", "FLUC_RT": "4.5"}),
        ]

        snapshots = _build_sector_leaders(
            rows, "2026-09-02", "2026-09-02T08:00:00+00:00"
        )

        self.assertEqual(len(snapshots), 6)
        self.assertIn("KOSPI 전기전자", snapshots[0].name)
        self.assertIn("KOSDAQ 오락문화", snapshots[3].name)


if __name__ == "__main__":
    unittest.main()
