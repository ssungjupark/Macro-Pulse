import os
import sys
import unittest
from unittest.mock import MagicMock, patch


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.data.providers import cnbc as cnbc_fetcher
from macro_pulse.domain.models import ExchangeRates


SAMPLE_QUOTE_HTML = """
<html>
  <body>
    <div class="QuoteStrip-lastPriceStripContainer">
      <span class="QuoteStrip-lastPrice">3.629%</span>
      <span class="QuoteStrip-changeDown">
        <img class="QuoteStrip-changeIcon" src="icon.svg" alt="quote price arrow down">
        <span>-0.112</span>
        <span>(-2.99%)</span>
      </span>
    </div>
  </body>
</html>
"""

SAMPLE_FX_QUOTE_HTML = """
<html>
  <body>
    <div class="QuoteStrip-lastPriceStripContainer">
      <span class="QuoteStrip-lastPrice">1,512.30</span>
      <span class="QuoteStrip-changeUp">
        <img class="QuoteStrip-changeIcon" src="icon.svg" alt="quote price arrow up">
        <span>+7.05</span>
        <span> (<!-- -->+0.4684%<!-- -->)</span>
      </span>
    </div>
  </body>
</html>
"""


class CnbcFetcherTests(unittest.TestCase):
    def test_parse_cnbc_quote_extracts_price_and_daily_change(self):
        quote = cnbc_fetcher.parse_cnbc_quote(SAMPLE_QUOTE_HTML)

        self.assertAlmostEqual(quote.price, 3.629)
        self.assertAlmostEqual(quote.change, -0.112)
        self.assertAlmostEqual(quote.change_pct, -2.99)

    def test_parse_cnbc_quote_extracts_fx_price_with_comments(self):
        quote = cnbc_fetcher.parse_cnbc_quote(SAMPLE_FX_QUOTE_HTML)

        self.assertAlmostEqual(quote.price, 1512.30)
        self.assertAlmostEqual(quote.change, 7.05)
        self.assertAlmostEqual(quote.change_pct, 0.4684)

    @patch("macro_pulse.data.providers.cnbc.urlopen")
    def test_fetch_cnbc_data_fetches_requested_symbols(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.read.return_value = SAMPLE_QUOTE_HTML.encode("utf-8")
        mock_urlopen.return_value = response

        quotes = cnbc_fetcher.fetch_cnbc_data(["KR10Y"])

        self.assertIn("KR10Y", quotes)
        self.assertAlmostEqual(quotes["KR10Y"].price, 3.629)
        self.assertAlmostEqual(quotes["KR10Y"].change, -0.112)
        self.assertEqual(quotes["KR10Y"].name, "Korea 10Y Treasury")

    def test_extract_cnbc_exchange_rates_maps_expected_currency_pairs(self):
        quotes = {
            "KRW=": {"price": 1330.0, "change": 2.0, "change_pct": 0.15},
            "JPY=": {"price": 150.0, "change": 1.0, "change_pct": 0.67},
            "CNY=": {"price": 7.2, "change": 0.1, "change_pct": 1.41},
            "EUR=": {"price": 1.08, "change": 0.01, "change_pct": 0.93},
        }

        self.assertEqual(
            cnbc_fetcher.extract_cnbc_exchange_rates(quotes),
            ExchangeRates(
                usd_krw=1330.0,
                usd_jpy=150.0,
                usd_cny=7.2,
                eur_usd=1.08,
            ),
        )

    def test_us_treasury_symbols_use_cnbc_quote_pages(self):
        for symbol in ("US2Y", "US10Y", "US30Y"):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, cnbc_fetcher.CNBC_MARKET_SYMBOLS)
                self.assertEqual(
                    cnbc_fetcher.CNBC_QUOTES[symbol]["url"],
                    f"https://www.cnbc.com/quotes/{symbol}",
                )


if __name__ == "__main__":
    unittest.main()
