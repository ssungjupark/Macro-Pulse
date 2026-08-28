from __future__ import annotations

import json
import os
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

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


TRUSTED_DOMAINS = (
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "wsj.com",
    "ft.com",
    "apnews.com",
    "finance.yahoo.com",
    "marketwatch.com",
    "yna.co.kr",
    "en.yna.co.kr",
    "hankyung.com",
    "mk.co.kr",
    "businesskorea.co.kr",
)


def _signal_text(signals: list[dict]) -> str:
    return "\n".join(
        f"- {signal['name']}: "
        f"{signal['move']} "
        f"({signal['direction']})"
        for signal in signals[:5]
    )


def _news_query(
    signals: list[dict],
    mode: str,
) -> str:
    if mode == "KR":
        terms = [
            "KOSPI",
            "KOSDAQ",
            '"South Korea stocks"',
            '"Korean won"',
            '"Bank of Korea"',
            '"Samsung Electronics"',
            '"SK Hynix"',
            '"Shanghai Composite"',
            '"China stocks"',
        ]

    else:
        terms = [
            '"S&P 500"',
            "Nasdaq",
            '"Federal Reserve"',
            '"US Treasury"',
            "Nvidia",
            "semiconductor",
            '"US dollar"',
            "VIX",
        ]

    signal_map = {
        "Gold": '"gold price"',
        "Silver": '"silver price"',
        "Copper": '"copper price"',
        "Bitcoin": "Bitcoin",
        "Ethereum": "Ethereum",
        "USD/KRW": '"Korean won"',
        "JPY/KRW": '"Japanese yen"',
        "US 10Y Treasury": '"US Treasury"',
        "Korea 10Y Treasury": '"South Korea bond"',
        "Japan 10Y Treasury": '"Japan bond"',
        "Shanghai Composite": '"Shanghai Composite"',
        "Hang Seng": '"Hang Seng"',
        "Nikkei 225": "Nikkei",
    }

    for signal in signals[:5]:
        mapped = signal_map.get(signal["name"])

        if mapped and mapped not in terms:
            terms.append(mapped)

    return "(" + " OR ".join(terms) + ")"


def _fetch_news(
    signals: list[dict],
    mode: str,
) -> list[dict]:
    params = {
        "query": _news_query(signals, mode),
        "mode": "artlist",
        "format": "json",
        "maxrecords": "20",
        "timespan": "24h",
        "sort": "datedesc",
    }

    url = (
        f"{GDELT_URL}?"
        f"{urlencode(params)}"
    )

    request = Request(
        url,
        headers={
            "User-Agent": "Macro-Pulse/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(
            request,
            timeout=20,
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning(
            "GDELT news request failed: %s",
            exc,
        )
        return []

    articles = []
    seen_titles = set()

    for article in data.get(
        "articles",
        [],
    ):
        title = (
            article.get("title")
            or ""
        ).strip()

        domain = (
            article.get("domain")
            or ""
        ).strip()

        article_url = (
            article.get("url")
            or ""
        ).strip()

        seen_date = (
            article.get("seendate")
            or ""
        ).strip()

        if not title:
            continue

        if title in seen_titles:
            continue

        seen_titles.add(title)

        articles.append(
            {
                "title": title,
                "domain": domain,
                "url": article_url,
                "seen_date": seen_date,
            }
        )

    def rank(
        article: dict,
    ) -> tuple[int, str]:
        domain = (
            article["domain"]
            .lower()
        )

        trusted = any(
            domain == trusted_domain
            or domain.endswith(
                "." + trusted_domain
            )
            for trusted_domain
            in TRUSTED_DOMAINS
        )

        return (
            1 if trusted else 0,
            article["seen_date"],
        )

    articles.sort(
        key=rank,
        reverse=True,
    )

    return articles[:12]


def _news_text(
    news: list[dict],
) -> str:
    if not news:
        return (
            "- 최근 24시간 뉴스 데이터를 "
            "가져오지 못했습니다."
        )

    lines = []

    for index, article in enumerate(
        news,
        start=1,
    ):
        source = (
            article["domain"]
            or "unknown"
        )

        lines.append(
            f"{index}. "
            f"{article['title']} "
            f"| {source} "
            f"| {article['seen_date']}"
        )

    return "\n".join(lines)


def _fallback(
    signals: list[dict],
    news: list[dict],
) -> str:
    signal_summary = ", ".join(
        f"{signal['name']} "
        f"{signal['move']}"
        for signal in signals[:4]
    )

    text = (
        "[시장 해석]\n"
        f"주요 변동 신호는 "
        f"{signal_summary}입니다. "
        "AI 분석 호출이 실패해 "
        "원인을 임의로 단정하지 않습니다."
    )

    if news:
        text += "\n\n[참고 뉴스]\n"

        for article in news[:3]:
            source = (
                article["domain"]
                or "출처 미상"
            )

            text += (
                f"- {article['title']} "
                f"({source})\n"
            )

        text = text.rstrip()

    return text


def analyze_market(
    signals: list[dict],
    mode: str,
) -> str | None:
    if not signals:
        return None

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:
        logger.warning(
            "GEMINI_API_KEY missing"
        )

        return _fallback(
            signals,
            [],
        )

    news = _fetch_news(
        signals,
        mode,
    )

    market = (
        "한국 및 아시아 증시"
        if mode == "KR"
        else "미국 및 글로벌 증시"
    )

    prompt = f"""
당신은 증권사 리서치센터의 데일리 시황 담당자입니다.

분석 대상: {market}

[자동 탐지 시장 신호]
{_signal_text(signals)}

[최근 24시간 뉴스 헤드라인]
{_news_text(news)}

위 시장 신호와 뉴스 헤드라인만 근거로 시장을 해석하세요.

작성 원칙:
- 뉴스에 없는 사실을 새로 만들어내지 마세요.
- 여러 뉴스가 공통으로 지지하는 원인을 우선하세요.
- 단순 동시 발생을 인과관계로 단정하지 마세요.
- 직접 원인이 충분히 확인되지 않으면
  "직접 원인은 확인되지 않음"이라고 쓰세요.
- 한국 시장은 외국인 수급, 반도체, 중국 증시,
  환율, 금리를 우선 연결하세요.
- 미국 시장은 국채금리, Fed, 빅테크,
  반도체, 달러를 우선 연결하세요.
- 투자 추천, 목표주가, 과도한 전망은 쓰지 마세요.
- 텔레그램용이므로 전체 8~12줄 이내로 작성하세요.

반드시 아래 형식만 사용하세요.

[시장 해석]
2~3문장

[핵심 이슈]
1. 핵심 원인과 시장 영향
2. 핵심 원인과 시장 영향
3. 필요한 경우 추가 원인

[체크 포인트]
앞으로 확인할 변수 2~3개를 한 줄로 작성
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
            "maxOutputTokens": 1800,
            "thinkingConfig": {
                "thinkingLevel": "low",
            },
        },
    }

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
        logger.warning(
            "Gemini returned no candidates"
        )

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
        part.get(
            "text",
            "",
        )
        for part in parts
        if part.get("text")
    ).strip()

    if not text:
        logger.warning(
            "Gemini returned empty text"
        )

        return _fallback(
            signals,
            news,
        )

    return text
