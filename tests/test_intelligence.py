import os
import sys
import unittest


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.intelligence import (
    _analysis_uses_only_supported_numbers,
    _fallback,
    _has_required_analysis_sections,
    is_allowed_source,
    verify_and_deduplicate_articles,
)
from macro_pulse.domain.models import AssetSnapshot


class IntelligenceSourceTests(unittest.TestCase):
    def test_source_allowlist_blocks_low_quality_sources(self):
        self.assertTrue(is_allowed_source("Reuters", "KR"))
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

    def test_fallback_always_keeps_required_output_sections(self):
        result = _fallback([], [])

        self.assertTrue(_has_required_analysis_sections(result))
        self.assertIn("검증 조건을 충족한 핵심 이슈 없음", result)

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
