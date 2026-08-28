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
NEWS_URL = "https://news.google.com/rss/search"


def _signal_text(signals: list[dict]) -> str:
    return "\n".join(
        f"- {s['name']}: {s['move']} ({s['direction']})"
        for s in signals[:5]
    )


def _query_for(name: str) -> tuple[str, str, str, str]:
    mapping = {
        "Nasdaq": (
            "Nasdaq Nvidia earnings technology stocks when:1d",
            "en-US", "US", "US:en"
        ),
        "S&P 500": (
            '"S&P 500" Nvidia earnings Fed stocks when:1d',
            "en-US", "US", "US:en"
        ),
        "VIX": (
            "VIX stock market volatility Fed when:1d",
            "en-US", "US", "US:en"
        ),
        "US 10Y Treasury": (
            '"Treasury yields" Fed inflation bonds when:1d',
            "en-US", "US", "US:en"
        ),
        "Gold": (
            "gold price dollar yields Jackson Hole when:1d",
            "en-US", "US", "US:en"
        ),
        "Silver": (
            "silver price gold dollar yields metals when:1d",
            "en-US", "US", "US:en"
        ),
        "Copper": (
            "copper price China demand supply when:1d",
            "en-US", "US", "US:en"
        ),
        "Bitcoin": (
            "Bitcoin price crypto market when:1d",
            "en-US", "US", "US:en"
        ),
        "Ethereum": (
            "Ethereum price crypto market when:1d",
            "en-US", "US", "US:en"
        ),
        "KOSPI": (
            "코스피 엔비디아 반도체 외국인 한국은행 when:1d",
            "ko", "KR", "KR:ko"
        ),
        "KOSDAQ": (
            "코스닥 외국인 기관 반도체 바이오 when:1d",
            "ko", "KR", "KR:ko"
        ),
        "VKOSPI": (
            "코스피 변동성 증시 투자심리 when:1d",
            "ko", "KR", "KR:ko"
        ),
        "USD/KRW": (
            "원달러 환율 외국인 달러 한국은행 when:1d",
            "ko", "KR", "KR:ko"
        ),
        "Korea 10Y Treasury": (
            "국고채 10년 금리 한국은행 채권 when:1d",
            "ko", "KR", "KR:ko"
        ),
        "Shanghai Composite": (
            "Shanghai Composite China stocks policy economy when:1d",
            "en-US", "US", "US:en"
        ),
        "Hang Seng": (
            "Hang Seng China Hong Kong stocks when:1d",
            "en-US", "US", "US:en"
        ),
        "Nikkei 225": (
            "Nikkei Japan stocks yen when:1d",
            "en-US", "US", "US:en"
        ),
        "Japan 10Y Treasury": (
            "Japan bond yields BOJ yen when:1d",
            "en-US", "US", "US:en"
        ),
        "JPY/KRW": (
            "엔원 환율 엔화 일본은행 when:1d",
            "ko", "KR", "KR:ko"
        ),
    }

    return mapping.get(
        name,
        (f'"{name}" market when:1d', "en-US", "US", "US:en"),
    )


def _broad_query(mode: str) -> tuple[str, str, str, str]:
    if mode == "KR":
        return (
            "코스피 반도체 외국인 한국은행 엔비디아 증시 when:1d",
            "ko", "KR", "KR:ko"
        )

    return (
        "US stock market Nasdaq Nvidia Fed Treasury yields when:1d",
        "en-US", "US", "US:en"
    )


def _fetch_rss(
    spec: tuple[str, str, str, str]
) -> list[dict]:
    query, hl, gl, ceid = spec

    params = {
        "q": query,
        "hl": hl,
        "gl": gl,
        "ceid": ceid,
    }

    url = f"{NEWS_URL}?{urlencode(params)}"

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Macro-Pulse/1.0"
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            root = ET.fromstring(response.read())

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ET.ParseError,
    ) as exc:
        logger.warning(
            "News RSS failed for %s: %s",
            query,
            exc,
        )
        return []

    items = []

    for item in root.findall(".//item")[:6]:
        title = (
            item.findtext("title")
            or ""
        ).strip()

        if not title:
            continue

        items.append(
            {
                "title": title,
                "source": (
                    item.findtext("source")
                    or ""
                ).strip(),
                "published": (
                    item.findtext("pubDate")
                    or ""
                ).strip(),
            }
        )

    return items


def _fetch_news(
    signals: list[dict],
    mode: str,
) -> list[dict]:
    specs = [_broad_query(mode)]

    for signal in signals[:4]:
        specs.append(
            _query_for(signal["name"])
        )

    articles = []
    seen = set()

    for spec in specs:
        for article in _fetch_rss(spec):
            key = article["title"].lower()

            if key in seen:
                continue

            seen.add(key)
            articles.append(article)

    logger.info(
        "Collected %s news headlines",
        len(articles),
    )

    return articles[:18]


def _news_text(
    news: list[dict],
) -> str:
    if not news:
        return "뉴스 수집 실패"

    return "\n".join(
        (
            f"{i}. {article['title']} | "
            f"{article['source'] or '출처 미상'} | "
            f"{article['published']}"
        )
        for i, article in enumerate(
            news,
            start=1,
        )
    )


def _fallback(
    signals: list[dict],
    news: list[dict],
) -> str:
    signal_summary = ", ".join(
        f"{signal['name']} {signal['move']}"
        for signal in signals[:4]
    )

    text = (
        "[시장 해석]\n"
        f"주요 변동 신호는 {signal_summary}입니다. "
        "AI 분석 호출이 실패해 자동 해석을 생략합니다."
    )

    if news:
        text += "\n\n[참고 뉴스]\n"

        for article in news[:4]:
            text += (
                f"- {article['title']} "
                f"({article['source'] or '출처 미상'})\n"
            )

    return text.rstrip()


def analyze_market(
    signals: list[dict],
    mode: str,
) -> str | None:
    if not signals:
        return None

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    news = _fetch_news(
        signals,
        mode,
    )

    if not api_key:
        logger.warning(
            "GEMINI_API_KEY missing"
        )

        return _fallback(
            signals,
            news,
        )

    market = (
        "한국 및 아시아 증시"
        if mode == "KR"
        else "미국 및 글로벌 증시"
    )

    prompt = f"""
당신은 증권사 리서치센터의 데일리 시황 담당자입니다.

분석 대상: {market}

[시장 변동]
{_signal_text(signals)}

[최근 뉴스 헤드라인]
{_news_text(news)}

뉴스 헤드라인에 근거해 시장 움직임의 원인을 분석하세요.

규칙:
- 기사 제목이 시장 상승·하락 원인을 직접 설명하면 그 원인을 분명히 적으세요.
- 직접 근거가 있는데도 '원인 확인되지 않음'이라고 쓰지 마세요.
- 여러 기사에서 반복되는 기업 실적, 정책, 금리, 수급 이슈를 우선하세요.
- 뉴스에 없는 사실은 만들지 마세요.
- 근거가 약한 항목에만 '추가 확인 필요'라고 쓰세요.
- 한국 시장은 외국인 수급, 삼성전자·SK하이닉스, 반도체, 한국은행을 우선 확인하세요.
- 미국 시장은 Nvidia 등 빅테크 실적, 반도체, Fed, 국채금리를 우선 확인하세요.
- 전체 10~12줄 이내로 작성하세요.
- 투자 추천과 목표주가는 쓰지 마세요.

형식:

[시장 해석]
2~3문장

[핵심 이슈]
1. 원인 → 시장 영향 (출처)
2. 원인 → 시장 영향 (출처)
3. 필요 시 추가 이슈 (출처)

[체크 포인트]
다음 거래에서 확인할 변수 2~3개
""".strip()

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
    "thinkingConfig": {
        "thinkingLevel": "minimal",
    },
},

    request = Request(
        GEMINI_URL,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
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
        body = (
            exc.read()
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        logger.warning(
            "Gemini HTTP error %s: %s",
            exc.code,
            body[:1000],
        )

        return _fallback(
            signals,
            news,
        )

    except (
        URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning(
            "Gemini request failed: %s",
            exc,
        )

        return _fallback(
            signals,
            news,
        )

    candidates = result.get(
        "candidates",
        [],
    )

    if not candidates:
        return _fallback(
            signals,
            news,
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    text = "\n".join(
        part.get("text", "")
        for part in parts
        if part.get("text")
    ).strip()

    return (
        text
        or _fallback(
            signals,
            news,
        )
    )
