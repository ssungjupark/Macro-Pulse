import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.data import market_data
from macro_pulse.data.market_data import YF_TICKERS
from macro_pulse.domain.models import TickerDefinition


class MacroIndicatorTests(unittest.TestCase):
    def test_required_free_market_indicators_are_configured(self):
        definitions = {
            definition.name: definition.symbol
            for items in YF_TICKERS.values()
            for definition in items
        }

        self.assertEqual(definitions["DXY"], "DX-Y.NYB")
        self.assertEqual(definitions["WTI"], "CL=F")
        self.assertEqual(definitions["SOX"], "^SOX")
        self.assertEqual(definitions["Russell 2000"], "^RUT")
        self.assertEqual(definitions["MOVE"], "^MOVE")

    @patch("macro_pulse.data.market_data.is_stale_as_of", return_value=False)
    @patch("macro_pulse.data.market_data.yf.Ticker")
    def test_required_indicators_build_snapshots_from_free_history(
        self,
        mock_ticker,
        _mock_stale,
    ):
        dates = pd.date_range("2026-08-03", periods=22, freq="B")
        history = pd.DataFrame(
            {"Close": [100.0 + index for index in range(22)]},
            index=dates,
        )
        ticker = MagicMock()
        ticker.history.return_value = history
        mock_ticker.return_value = ticker
        required = {
            "indices_overseas": (
                TickerDefinition("SOX", "^SOX"),
                TickerDefinition("Russell 2000", "^RUT"),
            ),
            "commodities": (TickerDefinition("WTI", "CL=F"),),
            "volatility": (TickerDefinition("MOVE", "^MOVE"),),
            "macro": (TickerDefinition("DXY", "DX-Y.NYB"),),
        }
        results = market_data._empty_report_dataset()

        with patch.object(market_data, "YF_TICKERS", required):
            market_data._append_yahoo_snapshots(results)

        snapshots = {
            item.name: item for category in required for item in results[category]
        }
        self.assertEqual(
            set(snapshots),
            {"DXY", "WTI", "SOX", "Russell 2000", "MOVE"},
        )
        self.assertTrue(all(item.price == 121.0 for item in snapshots.values()))
        self.assertTrue(
            all(item.source == "Yahoo Finance" for item in snapshots.values())
        )
        self.assertTrue(all(item.change_5d is not None for item in snapshots.values()))
        self.assertTrue(all(item.change_20d is not None for item in snapshots.values()))


if __name__ == "__main__":
    unittest.main()
