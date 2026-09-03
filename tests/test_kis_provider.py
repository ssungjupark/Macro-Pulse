import os
import sys
import unittest
from datetime import date
from unittest.mock import patch


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.data.providers.kis import (
    INDEX_PATH,
    INVESTOR_PATH,
    PROGRAM_PATH,
    SECTOR_PATH,
    _fetch_access_token,
    fetch_kis_market_state,
    million_won_to_100m,
    unavailable_kis_market_state,
)
from macro_pulse.reporting.generator import generate_telegram_summary


class KisProviderTests(unittest.TestCase):
    def test_million_won_to_100m_preserves_sign_and_unit(self):
        self.assertEqual(million_won_to_100m("-1,250,000"), -12500.0)
        self.assertEqual(million_won_to_100m("350"), 3.5)

    @patch.dict(
        os.environ,
        {"KIS_APP_KEY": "test-key", "KIS_APP_SECRET": "test-secret"},
        clear=True,
    )
    @patch("macro_pulse.data.providers.kis._fetch_access_token", return_value="token")
    @patch("macro_pulse.data.providers.kis._kis_get")
    def test_fetch_market_state_maps_official_quote_fields(
        self,
        mock_get,
        _mock_token,
    ):
        def response(path, _tr_id, params, *_credentials):
            if path == INVESTOR_PATH:
                if params["FID_INPUT_ISCD"] == "0001":
                    return {
                        "rt_cd": "0",
                        "output": [
                            {
                                "stck_bsop_date": "20260902",
                                "frgn_ntby_tr_pbmn": "150000",
                                "orgn_ntby_tr_pbmn": "-25000",
                            }
                        ],
                    }
                return {
                    "rt_cd": "0",
                    "output": [
                        {
                            "stck_bsop_date": "20260902",
                            "frgn_ntby_tr_pbmn": "-20000",
                            "orgn_ntby_tr_pbmn": "12500",
                        }
                    ],
                }
            if path == INDEX_PATH:
                turnover = (
                    "12345600"
                    if params["FID_INPUT_ISCD"] == "0001"
                    else "2345600"
                )
                return {
                    "rt_cd": "0",
                    "output": {
                        "ascn_issu_cnt": "615",
                        "down_issu_cnt": "244",
                        "acml_tr_pbmn": turnover,
                    },
                }
            if path == SECTOR_PATH:
                market = "KOSPI" if params["FID_MRKT_CLS_CODE"] == "K" else "KOSDAQ"
                rates = (
                    [("전기전자", "3.0"), ("화학", "0.5"), ("철강", "-2.0")]
                    if market == "KOSPI"
                    else [("반도체", "1.2"), ("제약", "-1.1"), ("오락문화", "-3.2")]
                )
                return {
                    "rt_cd": "0",
                    "output2": [
                        {
                            "hts_kor_isnm": name,
                            "bstp_nmix_prdy_ctrt": rate,
                        }
                        for name, rate in rates
                    ],
                }
            if path == PROGRAM_PATH:
                return {
                    "rt_cd": "0",
                    "output": [
                        {
                            "stck_bsop_date": "20260902",
                            "arbt_smtn_ntby_tr_pbmn": "1000",
                            "nabt_smtn_ntby_tr_pbmn": "-2500",
                        }
                    ],
                }
            self.fail(f"Unexpected KIS path: {path}")

        mock_get.side_effect = response

        state = fetch_kis_market_state(date(2026, 9, 2))
        flow = {item.name: item for item in state["domestic_flow"]}
        breadth = {item.name: item for item in state["market_breadth"]}

        self.assertEqual(flow["외국인 KOSPI 현물"].price, 1500.0)
        self.assertEqual(flow["기관 KOSPI 현물"].price, -250.0)
        self.assertEqual(flow["외국인 KOSDAQ 현물"].price, -200.0)
        self.assertEqual(flow["기관 KOSDAQ 현물"].price, 125.0)
        self.assertEqual(flow["프로그램 차익"].price, 10.0)
        self.assertEqual(flow["프로그램 비차익"].price, -25.0)
        self.assertEqual(breadth["KOSPI 상승 종목"].price, 615)
        self.assertEqual(breadth["KOSPI 하락 종목"].price, 244)
        self.assertEqual(breadth["KOSPI 거래대금"].price, 123456.0)
        self.assertEqual(len(state["sector_performance"]), 6)
        self.assertEqual(
            state["sector_performance"][0].name,
            "업종 상위 1: KOSPI 전기전자",
        )
        self.assertEqual(
            state["sector_performance"][3].name,
            "업종 하위 1: KOSDAQ 오락문화",
        )
        self.assertTrue(
            all(
                item.source == "KIS"
                for items in state.values()
                for item in items
            )
        )
        self.assertEqual(mock_get.call_count, 7)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_credentials_returns_one_compact_failure_item(self):
        state = fetch_kis_market_state(date(2026, 9, 2))

        self.assertEqual(len(state["domestic_flow"]), 1)
        self.assertEqual(state["market_breadth"], [])
        self.assertEqual(state["sector_performance"], [])
        self.assertEqual(
            state["domestic_flow"][0].name,
            "국내 수급 및 시장 체력",
        )

    def test_compact_failure_renders_as_one_na_line(self):
        state = unavailable_kis_market_state("한투 시세 수집 실패")
        state["domestic_state"] = state["domestic_flow"]

        summary = generate_telegram_summary(state, "KR")
        section = summary.split("[수급 및 시장 체력]\n", 1)[1]
        section = section.split("\n\n", 1)[0]

        self.assertEqual(section.count("N/A"), 1)
        self.assertIn("국내 수급 및 시장 체력: N/A", section)

    @patch("macro_pulse.data.providers.kis._request_json")
    def test_token_request_uses_client_credentials_without_account(self, mock_request):
        mock_request.return_value = {"access_token": "access-token"}

        token = _fetch_access_token("app-key", "app-secret")

        self.assertEqual(token, "access-token")
        request = mock_request.call_args.args[0]
        payload = request.data.decode("utf-8")
        self.assertIn('"grant_type": "client_credentials"', payload)
        self.assertNotIn("account", payload.lower())
        self.assertNotIn("cano", payload.lower())


if __name__ == "__main__":
    unittest.main()
