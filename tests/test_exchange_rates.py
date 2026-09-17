import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.data import market_data
from macro_pulse.domain.models import CnbcQuote


def make_history(values):
    return pd.DataFrame({"Close": values})


def assert_float_list_almost_equal(test_case, actual, expected):
    test_case.assertEqual(len(actual), len(expected))
    for actual_value, expected_value in zip(actual, expected):
        test_case.assertAlmostEqual(actual_value, expected_value)


def print_exchange_snapshot(exchange):
    print("\nCalculated exchange rates from mocked CNBC test data:")
    print(f"USD/KRW: {exchange['USD/KRW'].price:.2f}")
    print(f"JPY/KRW (100 JPY): {exchange['JPY/KRW'].price:.2f}")
    print(f"EUR/KRW: {exchange['EUR/KRW'].price:.2f}")
    print(f"CNY/KRW: {exchange['CNY/KRW'].price:.2f}")


class ExchangeRateCalculationTests(unittest.TestCase):
    @patch(
        "macro_pulse.data.market_data.fetch_treasury_histories",
        return_value={},
    )
    @patch(
        "macro_pulse.data.market_data.fetch_krx_market_state",
        return_value={"domestic_flow": [], "market_breadth": []},
    )
    @patch.dict(market_data.YF_TICKERS, {}, clear=True)
    @patch.dict(
        market_data.YF_RATES_HISTORY,
        {
            "USD/KRW": "KRW=X",
            "JPY/KRW": "JPYKRW=X",
            "EUR/KRW": "EURKRW=X",
        },
        clear=True,
    )
    @patch(
        "macro_pulse.data.market_data.fetch_cnbc_data",
        return_value={
            "KRW=": CnbcQuote(
                name="USD/KRW",
                price=1330.0,
                change=2.0,
                change_pct=(2.0 / 1328.0) * 100,
            ),
            "JPY=": CnbcQuote(
                name="USD/JPY",
                price=150.0,
                change=1.0,
                change_pct=(1.0 / 149.0) * 100,
            ),
            "EUR=": CnbcQuote(
                name="EUR/USD",
                price=1.08,
                change=0.01,
                change_pct=(0.01 / 1.07) * 100,
            ),
            "CNY=": CnbcQuote(
                name="USD/CNY",
                price=7.2,
                change=0.1,
                change_pct=(0.1 / 7.1) * 100,
            ),
        },
    )
    @patch("macro_pulse.data.market_data.yf.Ticker")
    def test_fetch_all_data_builds_expected_exchange_results(
        self,
        mock_ticker,
        _mock_cnbc,
        _mock_krx,
        _mock_fred,
    ):
        history_by_ticker = {
            "KRW=X": make_history(
                [1310.0, 1315.0, 1320.0, 1322.0, 1324.0, 1328.0, 1329.0]
            ),
            "JPYKRW=X": make_history([9.0, 9.05, 9.1, 9.15, 9.2, 9.25, 9.3]),
            "EURKRW=X": make_history(
                [1420.0, 1425.0, 1428.0, 1430.0, 1432.0, 1434.0, 1435.0]
            ),
        }

        def ticker_side_effect(symbol):
            ticker = MagicMock()
            ticker.history.return_value = history_by_ticker.get(symbol, pd.DataFrame())
            return ticker

        mock_ticker.side_effect = ticker_side_effect

        results = market_data.fetch_all_data()

        exchange = {item.name: item for item in results["exchange"]}
        usd_krw = exchange["USD/KRW"]
        jpy_krw = exchange["JPY/KRW"]
        eur_krw = exchange["EUR/KRW"]
        cny_krw = exchange["CNY/KRW"]

        self.assertAlmostEqual(usd_krw.price, 1330.0)
        self.assertAlmostEqual(usd_krw.change, 2.0)
        self.assertAlmostEqual(usd_krw.change_pct, (2.0 / 1328.0) * 100)
        assert_float_list_almost_equal(
            self,
            usd_krw.history,
            [1310.0, 1315.0, 1320.0, 1322.0, 1324.0, 1328.0, 1329.0, 1330.0],
        )

        expected_jpy_krw = (1330.0 / 150.0) * 100
        previous_jpy_krw = (1328.0 / 149.0) * 100
        self.assertAlmostEqual(jpy_krw.price, expected_jpy_krw)
        self.assertAlmostEqual(jpy_krw.change, expected_jpy_krw - previous_jpy_krw)
        self.assertAlmostEqual(
            jpy_krw.change_pct,
            ((expected_jpy_krw - previous_jpy_krw) / previous_jpy_krw) * 100,
        )
        assert_float_list_almost_equal(
            self,
            jpy_krw.history,
            [
                900.0,
                905.0,
                910.0,
                915.0,
                920.0,
                925.0,
                930.0,
                expected_jpy_krw,
            ],
        )

        expected_eur_krw = 1330.0 * 1.08
        previous_eur_krw = 1328.0 * 1.07
        self.assertAlmostEqual(eur_krw.price, expected_eur_krw)
        self.assertAlmostEqual(eur_krw.change, expected_eur_krw - previous_eur_krw)
        self.assertAlmostEqual(
            eur_krw.change_pct,
            ((expected_eur_krw - previous_eur_krw) / previous_eur_krw) * 100,
        )
        assert_float_list_almost_equal(
            self,
            eur_krw.history,
            [
                1420.0,
                1425.0,
                1428.0,
                1430.0,
                1432.0,
                1434.0,
                1435.0,
                expected_eur_krw,
            ],
        )

        expected_cny_krw = 1330.0 / 7.2
        previous_cny_krw = 1328.0 / 7.1
        self.assertAlmostEqual(cny_krw.price, expected_cny_krw)
        self.assertAlmostEqual(cny_krw.change, expected_cny_krw - previous_cny_krw)
        self.assertAlmostEqual(
            cny_krw.change_pct,
            ((expected_cny_krw - previous_cny_krw) / previous_cny_krw) * 100,
        )
        self.assertEqual(cny_krw.history, [expected_cny_krw])

        print_exchange_snapshot(exchange)

    @patch(
        "macro_pulse.data.market_data.fetch_treasury_histories",
        return_value={},
    )
    @patch(
        "macro_pulse.data.market_data.fetch_krx_market_state",
        return_value={"domestic_flow": [], "market_breadth": []},
    )
    @patch.dict(market_data.YF_TICKERS, {}, clear=True)
    @patch.dict(market_data.YF_RATES_HISTORY, {}, clear=True)
    @patch(
        "macro_pulse.data.market_data.fetch_cnbc_data",
        return_value={
            ".KSVKOSPI": CnbcQuote(
                name="VKOSPI",
                price=66.61,
                change=-5.21,
                change_pct=-7.254246728,
            ),
            "JP10Y": CnbcQuote(
                name="Japan 10Y Treasury",
                price=2.184,
                change=-0.001,
                change_pct=-0.04576659,
            ),
            "KR10Y": CnbcQuote(
                name="Korea 10Y Treasury",
                price=3.629,
                change=-0.112,
                change_pct=-2.993851911,
            ),
        },
    )
    def test_fetch_all_data_keeps_cnbc_daily_change_values(
        self,
        _mock_cnbc,
        _mock_krx,
        _mock_fred,
    ):
        results = market_data.fetch_all_data()

        volatility = {item.name: item for item in results["volatility"]}
        bonds = {item.name: item for item in results["treasuries"]}

        self.assertAlmostEqual(volatility["VKOSPI"].price, 66.61)
        self.assertAlmostEqual(volatility["VKOSPI"].change, -5.21)
        self.assertAlmostEqual(volatility["VKOSPI"].change_pct, -7.254246728)

        self.assertAlmostEqual(bonds["Japan 10Y Treasury"].price, 2.184)
        self.assertAlmostEqual(bonds["Japan 10Y Treasury"].change, -0.001)
        self.assertAlmostEqual(
            bonds["Japan 10Y Treasury"].change_pct,
            -0.04576659,
        )

        self.assertAlmostEqual(bonds["Korea 10Y Treasury"].price, 3.629)
        self.assertAlmostEqual(bonds["Korea 10Y Treasury"].change, -0.112)
        self.assertAlmostEqual(
            bonds["Korea 10Y Treasury"].change_pct,
            -2.993851911,
        )


if __name__ == "__main__":
    unittest.main()
