import os
import sys
import unittest


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.data.providers.krx import (
    _aggregate_sector_net_buy,
    _build_breadth,
    _flow_sum,
    _flow_z_score,
    won_to_100m,
)


class KrxProviderTests(unittest.TestCase):
    def test_won_to_100m_preserves_sign_and_unit(self):
        self.assertEqual(won_to_100m("-1,250,000,000,000"), -12500.0)
        self.assertEqual(won_to_100m("350,000,000"), 3.5)

    def test_flow_windows_use_trading_session_values(self):
        values = list(range(1, 21))
        self.assertEqual(_flow_sum(values, 5), 90)
        self.assertEqual(_flow_sum(values, 20), 210)
        self.assertGreater(_flow_z_score(values), 1.8)

    def test_sector_net_buy_aggregates_tickers(self):
        rows = [
            {"ISU_SRT_CD": "000001", "NETBID_TRDVAL": "1,000,000,000"},
            {"ISU_SRT_CD": "000002", "NETBID_TRDVAL": "-250,000,000"},
            {"ISU_SRT_CD": "000003", "NETBID_TRDVAL": "500,000,000"},
        ]
        mapping = {
            "000001": "반도체",
            "000002": "반도체",
            "000003": "은행",
        }
        totals = _aggregate_sector_net_buy(rows, mapping)
        self.assertEqual(totals["반도체"], 750_000_000)
        self.assertEqual(totals["은행"], 500_000_000)

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


if __name__ == "__main__":
    unittest.main()
