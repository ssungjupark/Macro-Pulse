import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.intelligence import (
    _analysis_uses_only_supported_numbers,
    _broad_specs,
    _build_prompt,
    _call_gemini,
    _fallback,
    _fetch_news,
    _has_required_analysis_sections,
    is_allowed_source,
    verify_and_deduplicate_articles,
    analyze_market,
)


class IntelligenceSourceTests(unittest.TestCase):
    def test_prompt_only_contains_news_evidence(self):
        prompt = _build_prompt(
            [{"name": "KOSPI", "move": "-3.99%", "direction": "하락"}],
            "KR",
            [],
            {"example": "market data"},
        )
        self.assertIn("[오늘의 핵심 이슈]", prompt)
        self.assertNotIn("-3.99%", prompt)
        self.assertNotIn("[시장 해석]", prompt)

    @patch("macro_pulse.intelligence._call_gemini")
    @patch("macro_pulse.intelligence._fetch_news", return_value=[])
    def test_no_news_skips_ai_instead_of_inventing_issues(self, _fetch, call_ai):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}):
            result = analyze_market([], "KR")
        call_ai.assert_not_called()
        self.assertIn("수집하지 못했습니다", result)

    @patch("macro_pulse.intelligence._fetch_rss")
    def test_stale_or_future_articles_cannot_corroborate_current_news(self, fetch):
        from datetime import datetime, timedelta, timezone
        from email.utils import format_datetime

        now = datetime.now(timezone.utc)
        fetch.return_value = [
            {
                "title": "Oil jumps on supply disruption",
                "source": source,
                "published": format_datetime(published),
            }
            for source, published in (
                ("Reuters", now - timedelta(hours=1)),
                ("Bloomberg", now - timedelta(days=3)),
                ("CNBC", now + timedelta(days=3)),
            )
        ]
        self.assertEqual(_fetch_news([], "US"), [])

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

    def test_single_media_is_excluded_but_official_story_is_kept(self):
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
        by_source = {article["source"]: article for article in verified}
        self.assertNotIn("Reuters", by_source)
        self.assertEqual(
            by_source["U.S. Bureau of Labor Statistics"]["verification"],
            "official",
        )

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

    def test_fallback_only_keeps_key_issue_section(self):
        result = _fallback([], [])

        self.assertTrue(_has_required_analysis_sections(result))
        self.assertIn("검증 기준을 충족한 주요 뉴스를 수집하지 못했습니다", result)
        self.assertNotIn("시장 해석", result)
        self.assertNotIn("체크 포인트", result)

    def test_fallback_lists_verified_headlines_without_indicator_interpretation(self):
        news = [
            {
                "title": "Oil rises as supply risks return",
                "source": "Reuters",
                "verified_by": ["Reuters", "Bloomberg"],
            }
        ]

        result = _fallback([], news, "KR", {})

        self.assertIn("[오늘의 핵심 이슈]", result)
        self.assertIn("Oil rises as supply risks return", result)
        self.assertIn("(Reuters)", result)
        self.assertNotIn("KOSPI", result)

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

    def test_generated_numbers_must_exist_in_headlines(self):
        news = [
            {
                "title": "Oil rises 4.2% as supply risks return",
                "source": "Reuters",
            }
        ]
        supported = "[오늘의 핵심 이슈]\n1. 국제유가 4.2% 상승 (Reuters)"
        hallucinated = supported.replace("4.2%", "9.9%")

        self.assertTrue(_analysis_uses_only_supported_numbers(supported, [], news, {}))
        self.assertFalse(
            _analysis_uses_only_supported_numbers(hallucinated, [], news, {})
        )


if __name__ == "__main__":
    unittest.main()
