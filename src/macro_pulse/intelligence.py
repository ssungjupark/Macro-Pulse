from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core.logging import get_logger


logger = get_logger(__name__)

MODEL = "gemini-3.6-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:generateContent"
)
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"

TRUSTED_SOURCES = (
    "Reuters",
    "Bloomberg",
    "Associated Press",
    "AP News",
    "CNBC",
    "Financial Times",
    "The Wall Street Journal",
    "연합뉴스",
    "한국경제",
    "매일경제",
)


def _signal_text(signals: list[dict]) -> str:
    if not signals:
        return "- 기준치 이상의 특이 변동 신호 없음"

    return "\n".join(
        f"- {signal['name']}: {signal['move']} ({signal['direction']})"
        for signal in signals[:5]
    )


def _query_spec(name: str) -> tuple[str, str, str, str]:
    mapping = {
        "S&P 500": (
            "S&P 500 stocks Fed Nvidia earnings when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "Nasdaq": (
            "Nasdaq Nvidia semiconductor technology stocks when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "Euro Stoxx 50": (
            "Euro Stoxx 50 European stocks ECB when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "VIX": (
            "VIX volatility US stocks Fed when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "VKOSPI": (
            "코스피 변동성 외국인 투자심리 when:1d",
            "ko",
            "KR",
            "KR:ko",
        ),
        "US 10Y Treasury": (
            "US Treasury yields Fed inflation bonds when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "Korea 10Y Treasury": (
            "국고채 10년 금리 한국은행 채권 when:1d",
            "ko",
            "KR",
            "KR:ko",
        ),
        "Japan 10Y Treasury": (
            "Japan bond yields BOJ yen when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "Gold": (
            "gold price dollar Treasury yields when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "Silver": (
            "silver price precious metals dollar yields when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "Copper": (
            "copper price China demand supply metals when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "USD/KRW": (
            "원달러 환율 달러 외국인 한국은행 when:1d",
            "ko",
            "KR",
            "KR:ko",
        ),
        "JPY/KRW": (
            "엔원 환율 엔화 일본은행 when:1d",
            "ko",
            "KR",
            "KR:ko",
        ),
        "Bitcoin": (
            "Bitcoin crypto market price when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "Ethereum": (
            "Ethereum crypto market price when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "KOSPI": (
            "코스피 반도체 외국인 삼성전자 SK하이닉스 한국은행 when:1d",
            "ko",
            "KR",
            "KR:ko",
        ),
        "KOSDAQ": (
            "코스닥 외국인 기관 반도체 바이오 when:1d",
            "ko",
            "KR",
            "KR:ko",
        ),
        "Shanghai Composite": (
            "Shanghai Composite China stocks stimulus economy when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "Hang Seng": (
            "Hang Seng China Hong Kong stocks when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        "Nikkei 225": (
            "Nikkei Japan stocks yen BOJ when:1d",
            "en-US",
            "US",
            "US:en",
        ),
    }

    return mapping.get(
        name,
        (
            f'"{name}" market when:1d',
            "en-US",
            "US",
            "US:en",
        ),
    )


def _broad_specs(
    mode: str,
) -> list[tuple[str, str, str, str]]:
    if mode == "KR":
        return [
            (
                "코스피 증시 반도체 외국인 삼성전자 SK하이닉스 when:1d",
                "ko",
                "KR",
                "KR:ko",
            ),
            (
                "한국은행 원달러 환율 국고채 한국 증시 when:1d",
                "ko",
                "KR",
                "KR:ko",
            ),
            (
                "중국 증시 상하이 경기부양 한국 증시 when:1d",
                "ko",
                "KR",
                "KR:ko",
            ),
        ]

    return [
        (
            "US stock market Nasdaq S&P 500 Nvidia earnings when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        (
            "Federal Reserve Treasury yields dollar stocks when:1d",
            "en-US",
            "US",
            "US:en",
        ),
        (
            "AI semiconductor Nvidia AMD Broadcom stocks when:1d",
            "en-US",
            "US",
            "US:en",
        ),
    ]


def _fetch_rss(
    spec: tuple[str, str, str, str],
) -> list[dict]:
    query, hl, gl, ceid = spec

    params = {
        "q": query,
        "hl": hl,
        "gl": gl,
        "ceid": ceid,
    }

    url = (
        f"{GOOGLE_NEWS_URL}?"
        f"{urlencode(params)}"
    )

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macro-Pulse/1.0)",
            "Accept": (
                "application/rss+xml, "
                "application/xml, "
                "text/xml"
            ),
        },
    )

    try:
        with urlopen(
            request,
            timeout=20,
        ) as response:
            root = ET.fromstring(
                response.read()
            )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ET.ParseError,
    ) as exc:
        logger.warning(
            "Google News RSS failed for %s: %s",
            query,
            exc,
        )
        return []

    articles = []

    for item in root.findall(
        ".//item"
    )[:8]:
        title = (
            item.findtext("title")
            or ""
        ).strip()

        source = (
            item.findtext("source")
            or ""
        ).strip()

        published = (
            item.findtext("pubDate")
            or ""
        ).strip()

        if title:
            articles.append(
                {
                    "title": title,
                    "source": source,
                    "published": published,
                }
            )

    return articles


def _fetch_news(
    signals: list[dict],
    mode: str,
) -> list[dict]:
    specs = _broad_specs(mode)

    specs.extend(
        _query_spec(signal["name"])
        for signal in signals[:4]
    )

    articles = []
    seen_titles = set()

    for spec in specs:
        for article in _fetch_rss(
            spec
        ):
            key = article[
                "title"
            ].lower()

            if key in seen_titles:
                continue

            seen_titles.add(key)
            articles.append(article)

    def rank(
        article: dict,
    ) -> tuple[int, str]:
        trusted = int(
            article["source"]
            in TRUSTED_SOURCES
        )

        return (
            trusted,
            article["published"],
        )

    articles.sort(
        key=rank,
        reverse=True,
    )

    logger.info(
        "Collected %s Google News headlines",
        len(articles),
    )

    return articles[:20]


def _news_text(
    news: list[dict],
) -> str:
    if not news:
        return (
            "최근 뉴스 헤드라인을 "
            "수집하지 못했습니다."
        )

    return "\n".join(
        f"{index}. "
        f"{article['title']} | "
        f"{article['source'] or '출처 미상'} | "
        f"{article['published']}"
        for index, article
        in enumerate(
            news,
            start=1,
        )
    )


def _fallback(
    signals: list[dict],
    news: list[dict],
) -> str:
    lines = [
        "[시장 해석]"
    ]

    if signals:
        signal_summary = ", ".join(
            f"{signal['name']} "
            f"{signal['move']}"
            for signal
            in signals[:4]
        )

        lines.append(
            f"주요 변동 신호는 "
            f"{signal_summary}입니다. "
            "AI 분석 호출이 실패해 "
            "자동 해석을 생략합니다."
        )

    else:
        lines.append(
            "특이 변동 신호는 없으며 "
            "AI 분석 호출이 실패했습니다."
        )

    if news:
        lines.extend(
            [
                "",
                "[참고 뉴스]",
            ]
        )

        for article in news[:4]:
            lines.append(
                f"- {article['title']} "
                f"({article['source'] or '출처 미상'})"
            )

    return "\n".join(lines)


def _build_prompt(
    signals: list[dict],
    mode: str,
    news: list[dict],
) -> str:
    market = (
        "한국 및 아시아 증시"
        if mode == "KR"
        else "미국 및 글로벌 증시"
    )

    return f"""
당신은 증권사 리서치센터의 데일리 시황 담당자입니다.

분석 대상: {market}

[자동 탐지 시장 신호]
{_signal_text(signals)}

[최근 24시간 뉴스 헤드라인]
{_news_text(news)}

위 데이터만 근거로 오늘 시장의 핵심 원인과 이슈를 정리하세요.

작성 원칙:
- 뉴스에 명시된 사실을 우선 사용하세요.
- 여러 기사에서 반복되는 원인을 가장 중요한 원인으로 판단하세요.
- 직접 근거가 있는데도 '원인 확인되지 않음'이라고 쓰지 마세요.
- 뉴스에 없는 사실은 만들지 마세요.
- 직접 근거가 약한 항목에만 '추가 확인 필요'라고 표시하세요.
- 특이 변동 신호가 없어도 중요한 정책, 실적, 금리, 환율 이슈는 포함하세요.
- 한국 시장은 외국인 수급, 삼성전자·SK하이닉스, 반도체, 한국은행, 중국 증시, 환율을 우선 연결하세요.
- 미국 시장은 Nvidia 등 빅테크 실적, 반도체, Fed, 국채금리, 달러를 우선 연결하세요.
- 각 핵심 이슈 끝에 실제 뉴스 출처명을 괄호로 표시하세요.
- 투자 추천과 목표주가는 쓰지 마세요.
- 전체 답변은 700자 이내로 작성하세요.

반드시 아래 형식만 사용하세요.

[시장 해석]
2~3문장

[핵심 이슈]
1. 원인 → 시장 영향 (출처)
2. 원인 → 시장 영향 (출처)
3. 필요한 경우 추가 이슈 (출처)

[체크 포인트]
다음 거래에서 확인할 변수 2~3개
""".strip()


def _call_gemini(
    api_key: str,
    prompt: str,
) -> str | None:
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt
                    }
                ],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 4096,
        },
    }

    request = Request(
        GEMINI_URL,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": (
                "application/json"
            ),
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=45,
        ) as response:
            result = json.loads(
                response
                .read()
                .decode("utf-8")
            )

    except HTTPError as exc:
        error_body = (
            exc.read()
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        logger.warning(
            "Gemini HTTP error %s: %s",
            exc.code,
            error_body[:1000],
        )

        return None

    except (
        URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning(
            "Gemini request failed: %s",
            exc,
        )

        return None

    candidates = result.get(
        "candidates",
        [],
    )

    if not candidates:
        logger.warning(
            "Gemini returned no candidates"
        )
        return None

    candidate = candidates[0]

    finish_reason = candidate.get(
        "finishReason",
        "",
    )

    parts = (
        candidate
        .get("content", {})
        .get("parts", [])
    )

    text = "\n".join(
        part.get(
            "text",
            "",
        )
        for part in parts
        if (
            part.get("text")
            and not part.get(
                "thought",
                False,
            )
        )
    ).strip()

    if (
        finish_reason
        and finish_reason != "STOP"
    ):
        logger.warning(
            "Gemini finish reason: %s",
            finish_reason,
        )

    return text or None


def analyze_market(
    signals: list[dict],
    mode: str,
) -> str | None:
    news = _fetch_news(
        signals,
        mode,
    )

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:
        logger.warning(
            "GEMINI_API_KEY missing"
        )

        return _fallback(
            signals,
            news,
        )

    prompt = _build_prompt(
        signals,
        mode,
        news,
    )

    analysis = _call_gemini(
        api_key,
        prompt,
    )

    if analysis:
        return analysis

    return _fallback(
        signals,
        news,
    )
