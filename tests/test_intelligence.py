import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.intelligence import (
    _analysis_uses_only_supported_numbers,
    _broad_specs,
    _call_gemini,
    _fallback,
    _has_required_analysis_sections,
    is_allowed_source,
    verify_and_deduplicate_articles,
)
from macro_pulse.domain.models import AssetSnapshot


class IntelligenceSourceTests(unittest.TestCase):
    def test_source_allowlist_blocks_low_quality_sources(self):
        self.assertTrue(is_allowed_source("Reuters", "KR"))
        self.assertTrue(is_allowed_source("Reuters.com", "KR"))
        self.assertTrue(is_allowed_source("로이터", "KR"))
        self.assertTrue(is_allowed_source("Bloomberg.com", "US"))
        self.assertTrue(is_allowed_source("WSJ", "US"))
        self.assertTrue(is_allowed_source("U.S. Bureau of Labor Statistics", "US"))
        self.assertTrue(is_allowed_source("연합뉴스", "KR"))
        self.assertFalse(is_allowed_source("네이트 뉴스", "KR"))
        self.assertFalse(is_allowed_source("경제 블로그", "KR"))
        self.assertFalse(is_allowed_source("연합뉴스", "US"))
        self.assertFalse(is_allowed_source("Not Reuters", "US"))

    def test_media_story_requires_two_distinct_sources(self):
        articles = [
            {
                "title": "Oil rises as Middle East conflict lifts inflation fears",
                "source": "Reuters",
                "published": "today",
            },
            {
                "title": "Oil jumps as Middle East conflict raises inflation risks",
                "source": "Bloomberg",
                "published": "today",
            },
        ]

        verified = verify_and_deduplicate_articles(articles, "US")

        self.assertEqual(len(verified), 1)
        self.assertEqual(set(verified[0]["verified_by"]), {"Reuters", "Bloomberg"})

    def test_single_media_story_is_excluded_but_official_story_is_kept(self):
        articles = [
            {
                "title": "Stocks rise before inflation data",
                "source": "Reuters",
                "published": "today",
            },
            {
                "title": "Consumer Price Index release schedule",
                "source": "U.S. Bureau of Labor Statistics",
                "published": "today",
            },
        ]

        verified = verify_and_deduplicate_articles(articles, "US")

        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["source"], "U.S. Bureau of Labor Statistics")

    def test_korean_and_english_headlines_can_cross_verify_same_topic(self):
        articles = [
            {
                "title": "중동 충돌로 국제유가 급등, 물가 우려 확대",
                "source": "로이터",
                "published": "today",
            },
            {
                "title": "Oil jumps as Middle East conflict raises inflation risks",
                "source": "Bloomberg.com",
                "published": "today",
            },
        ]

        verified = verify_and_deduplicate_articles(articles, "KR")

        self.assertEqual(len(verified), 1)
        self.assertEqual(set(verified[0]["verified_by"]), {"로이터", "Bloomberg.com"})

    def test_kr_news_specs_include_english_global_searches(self):
        specs = _broad_specs("KR")

        self.assertTrue(any(spec[1] == "en-US" for spec in specs))
        self.assertTrue(any(spec[1] == "ko" for spec in specs))

    def test_fallback_always_keeps_required_output_sections(self):
        result = _fallback([], [])

        self.assertTrue(_has_required_analysis_sections(result))
        self.assertIn("검증된 뉴스 원인을 확보하지 못했습니다", result)
        self.assertNotIn("자동 해석을 생략", result)

    def test_fallback_uses_market_signals_and_domestic_flow(self):
        signals = [
            {"name": "KOSPI", "move": "-3.99%", "direction": "하락"},
            {"name": "WTI", "move": "+4.20%", "direction": "상승"},
        ]
        data = {
            "domestic_flow": [
                AssetSnapshot(name="외국인 KOSPI 현물", price=-12500),
                AssetSnapshot(name="기관 KOSPI 현물", price=3200),
            ]
        }

        result = _fallback(signals, [], "KR", data)

        self.assertIn("주식시장은 KOSPI -3.99%", result)
        self.assertIn("WTI +4.20%", result)
        self.assertIn("외국인 KOSPI 현물 -12,500억원", result)
        self.assertIn("프로그램 직접 수집", result)
        self.assertNotIn("AI 분석 호출이 실패", result)

    @patch("macro_pulse.intelligence.time.sleep")
    @patch("macro_pulse.intelligence.urlopen")
    def test_gemini_retries_once_after_timeout(self, mock_urlopen, _mock_sleep):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "분석 성공"}]},
                    }
                ]
            }
        ).encode("utf-8")
        mock_urlopen.side_effect = [TimeoutError("timed out"), response]

        result = _call_gemini("key", "prompt")

        self.assertEqual(result, "분석 성공")
        self.assertEqual(mock_urlopen.call_count, 2)

    def test_generated_numbers_must_exist_in_market_data_or_headlines(self):
        data = {
            "indices_domestic": [
                AssetSnapshot(name="KOSPI", price=6562.72, change_pct=-3.99)
            ]
        }
        supported = (
            "[시장 해석]\nKOSPI는 6,562.72로 -3.99% 하락했습니다.\n\n"
            "[핵심 이슈]\n1. 검증된 이슈\n\n[체크 포인트]\n확인"
        )
        hallucinated = supported.replace("-3.99%", "-9.99%")

        self.assertTrue(_analysis_uses_only_supported_numbers(supported, [], [], data))
        self.assertFalse(
            _analysis_uses_only_supported_numbers(hallucinated, [], [], data)
        )


if __name__ == "__main__":
    unittest.main()
