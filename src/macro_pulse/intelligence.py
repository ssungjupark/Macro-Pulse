from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core.logging import get_logger


logger = get_logger(__name__)

MODEL = "gemini-3.6-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
)
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"

TRUSTED_MEDIA = (
    "Reuters",
    "Bloomberg",
    "Associated Press",
    "The Associated Press",
    "AP",
    "AP News",
    "CNBC",
    "Financial Times",
    "The Wall Street Journal",
)

OFFICIAL_SOURCES = (
    "Federal Reserve",
    "Federal Reserve Board",
    "Board of Governors of the Federal Reserve System",
    "U.S. Department of the Treasury",
    "U.S. Treasury",
    "Bureau of Labor Statistics",
    "U.S. Bureau of Labor Statistics",
    "Bureau of Economic Analysis",
    "U.S. Bureau of Economic Analysis",
    "Energy Information Administration",
    "U.S. Energy Information Administration",
    "European Central Bank",
    "Bank of Japan",
    "Bank of Korea",
    "한국은행",
    "Korea Exchange",
    "한국거래소",
    "SEC.gov",
    "U.S. Securities and Exchange Commission",
)

KR_SUPPLEMENTAL_SOURCES = ("연합뉴스", "Yonhap News Agency")

SOURCE_ALIASES = {
    "Reuters": ("Reuters", "Reuters.com", "로이터"),
    "Bloomberg": ("Bloomberg", "Bloomberg.com", "블룸버그"),
    "Financial Times": (
        "Financial Times",
        "FT",
        "FT.com",
        "파이낸셜타임스",
    ),
    "The Wall Street Journal": (
        "The Wall Street Journal",
        "Wall Street Journal",
        "WSJ",
        "WSJ.com",
    ),
    "CNBC": ("CNBC", "CNBC.com"),
    "Associated Press": (
        "Associated Press",
        "The Associated Press",
        "AP",
        "AP News",
        "APNews.com",
    ),
    "Yonhap News Agency": ("Yonhap News Agency", "연합뉴스"),
}

TOPIC_ALIASES = {
    "oil": ("oil", "crude", "wti", "유가", "원유"),
    "middle_east": (
        "middle east",
        "iran",
        "israel",
        "중동",
        "이란",
        "이스라엘",
    ),
    "inflation": ("inflation", "price pressure", "물가", "인플레이션"),
    "rates": (
        "treasury yield",
        "bond yield",
        "interest rate",
        "국채금리",
        "국채 금리",
        "금리",
    ),
    "fed": ("federal reserve", "fed", "fomc", "연준"),
    "boj": ("bank of japan", "boj", "일본은행"),
    "korea": ("korea", "kospi", "한국", "코스피"),
    "japan": ("japan", "nikkei", "일본", "닛케이"),
    "semiconductor": (
        "semiconductor",
        "chip",
        "nvidia",
        "broadcom",
        "반도체",
        "엔비디아",
        "브로드컴",
    ),
    "earnings": ("earnings", "results", "실적"),
    "currency": ("dollar", "yen", "won", "달러", "엔화", "원화", "환율"),
}

BLOCKED_SOURCE_TOKENS = (
    "네이트",
    "블로그",
    "blog",
    "머니투데이방송",
    "mtn",
    "유튜브",
    "youtube",
    "커뮤니티",
)

TITLE_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "as",
    "at",
    "from",
    "with",
    "after",
    "before",
    "market",
    "markets",
    "stocks",
    "stock",
    "today",
    "says",
    "코스피",
    "증시",
    "시장",
    "관련",
    "대한",
    "따른",
}


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
                "global markets oil Treasury yields Asia stocks when:1d",
                "en-US",
                "US",
                "US:en",
            ),
            (
                "Middle East oil inflation stocks Reuters Bloomberg when:1d",
                "en-US",
                "US",
                "US:en",
            ),
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

    url = f"{GOOGLE_NEWS_URL}?{urlencode(params)}"

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macro-Pulse/1.0)",
            "Accept": ("application/rss+xml, application/xml, text/xml"),
        },
    )

    try:
        with urlopen(
            request,
            timeout=20,
        ) as response:
            root = ET.fromstring(response.read())

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

    for item in root.findall(".//item")[:8]:
        title = (item.findtext("title") or "").strip()

        source = (item.findtext("source") or "").strip()

        published = (item.findtext("pubDate") or "").strip()

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

    specs.extend(_query_spec(signal["name"]) for signal in signals[:4])

    articles = []

    for spec in specs:
        for article in _fetch_rss(spec):
            if not is_allowed_source(article.get("source", ""), mode):
                continue
            articles.append(article)

    articles = verify_and_deduplicate_articles(articles, mode)
    articles.sort(
        key=lambda article: (
            is_official_source(article["source"]),
            _published_timestamp(article.get("published", "")),
        ),
        reverse=True,
    )

    logger.info(
        "Collected %s verified Google News headlines",
        len(articles),
    )

    return articles[:20]


def is_allowed_source(source: str, mode: str = "US") -> bool:
    normalized = _normalize_source(source)
    if not normalized:
        return False
    if any(_normalize_source(token) in normalized for token in BLOCKED_SOURCE_TOKENS):
        return False
    if _is_company_ir(normalized):
        return True
    allowed = [*TRUSTED_MEDIA, *OFFICIAL_SOURCES]
    if mode == "KR":
        allowed.extend(KR_SUPPLEMENTAL_SOURCES)
    allowed_canonical = {_canonical_source(name) for name in allowed}
    return _canonical_source(source) in allowed_canonical


def is_official_source(source: str) -> bool:
    normalized = _normalize_source(source)
    return _is_company_ir(normalized) or _canonical_source(source) in {
        _canonical_source(name) for name in OFFICIAL_SOURCES
    }


def verify_and_deduplicate_articles(
    articles: list[dict],
    mode: str,
) -> list[dict]:
    unique = []
    for article in articles:
        if not is_allowed_source(article.get("source", ""), mode):
            continue
        if any(
            _canonical_source(article.get("source", ""))
            == _canonical_source(item.get("source", ""))
            and _same_story(article["title"], item["title"])
            for item in unique
        ):
            continue
        unique.append(dict(article))

    groups: list[list[dict]] = []
    for article in unique:
        group = next(
            (
                candidate
                for candidate in groups
                if _same_topic(article["title"], candidate[0]["title"])
            ),
            None,
        )
        if group is None:
            groups.append([article])
        else:
            group.append(article)

    verified = []
    for group in groups:
        sources = {
            _canonical_source(article["source"]): article["source"].strip()
            for article in group
        }
        official = any(is_official_source(source) for source in sources.values())
        if not official and len(sources) < 2:
            continue
        representative = max(
            group,
            key=lambda article: (
                is_official_source(article["source"]),
                _published_timestamp(article.get("published", "")),
            ),
        )
        representative = dict(representative)
        representative["verified_by"] = sorted(sources.values())
        verified.append(representative)
    return verified


def _normalize_source(source: str) -> str:
    return re.sub(r"\s+", " ", source.strip()).casefold().rstrip(".")


def _canonical_source(source: str) -> str:
    normalized = _normalize_source(source)
    for canonical, aliases in SOURCE_ALIASES.items():
        if normalized in {_normalize_source(alias) for alias in aliases}:
            return _normalize_source(canonical)
    return normalized


def _is_company_ir(normalized_source: str) -> bool:
    return "investor relations" in normalized_source or normalized_source.endswith(
        " ir"
    )


def _published_timestamp(value: str) -> float:
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _same_story(left: str, right: str) -> bool:
    left_normalized = _normalize_title(left)
    right_normalized = _normalize_title(right)
    return SequenceMatcher(None, left_normalized, right_normalized).ratio() >= 0.88


def _same_topic(left: str, right: str) -> bool:
    left_tokens = _title_tokens(left)
    right_tokens = _title_tokens(right)
    if left_tokens and right_tokens:
        overlap = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        if overlap >= 2 and overlap / union >= 0.2:
            return True

    shared_topics = _topic_tags(left) & _topic_tags(right)
    return len(shared_topics) >= 2


def _topic_tags(title: str) -> set[str]:
    normalized = _normalize_title(title)
    return {
        topic
        for topic, aliases in TOPIC_ALIASES.items()
        if any(_normalize_title(alias) in normalized for alias in aliases)
    }


def _normalize_title(title: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", " ", title.lower()).strip()


def _title_tokens(title: str) -> set[str]:
    return {
        token
        for token in _normalize_title(title).split()
        if len(token) > 1 and token not in TITLE_STOPWORDS
    }


def _news_text(
    news: list[dict],
) -> str:
    if not news:
        return "최근 뉴스 헤드라인을 수집하지 못했습니다."

    return "\n".join(
        f"{index}. "
        f"{article['title']} | "
        f"{article['source'] or '출처 미상'} | "
        f"{article['published']} | "
        f"검증: {', '.join(article.get('verified_by', []))}"
        for index, article in enumerate(
            news,
            start=1,
        )
    )


def _fallback(
    signals: list[dict],
    news: list[dict],
    mode: str = "US",
    data=None,
) -> str:
    lines = ["[시장 해석]", *_rule_based_interpretation(signals, mode, data)]

    lines.extend(["", "[핵심 이슈]"])
    if news:
        for index, article in enumerate(news[:3], 1):
            verified_by = article.get("verified_by") or [article["source"]]
            lines.append(f"{index}. {article['title']} ({', '.join(verified_by)})")
    else:
        observed = _observed_issue_lines(signals, mode, data)
        lines.extend(observed or ["검증된 뉴스 원인을 확보하지 못했습니다."])

    lines.extend(["", "[체크 포인트]"])
    lines.extend(_rule_based_checkpoints(signals, mode, news))

    return "\n".join(lines)


def _rule_based_interpretation(signals: list[dict], mode: str, data) -> list[str]:
    if signals:
        equity_names = (
            {"KOSPI", "KOSDAQ", "Nikkei 225", "Hang Seng", "Shanghai Composite"}
            if mode == "KR"
            else {"S&P 500", "Nasdaq", "SOX", "Russell 2000", "Euro Stoxx 50"}
        )
        equity = [signal for signal in signals if signal["name"] in equity_names]
        macro = [signal for signal in signals if signal not in equity]
        lines = []
        if equity:
            lines.append(
                "주식시장은 "
                + ", ".join(
                    f"{signal['name']} {signal['move']}" for signal in equity[:4]
                )
                + "의 변동 신호가 나타났습니다."
            )
        if macro:
            lines.append(
                "금리, 달러 및 원자재 관련 신호는 "
                + ", ".join(
                    f"{signal['name']} {signal['move']}" for signal in macro[:3]
                )
                + "로 집계됐습니다."
            )
    else:
        lines = ["기준치 이상의 특이 가격 변동은 확인되지 않았습니다."]

    if mode == "KR":
        flow = _domestic_flow_sentence(data)
        if flow:
            lines.append(flow)

    if len(lines) == 1:
        lines.append("직접 수집한 가격 기준으로 다음 거래의 연속성을 확인해야 합니다.")
    return lines[:3]


def _domestic_flow_sentence(data) -> str:
    values = []
    for name in (
        "외국인 KOSPI 현물",
        "기관 KOSPI 현물",
        "외국인 KOSDAQ 현물",
        "기관 KOSDAQ 현물",
    ):
        value = _snapshot_price(data, name)
        if value is not None:
            values.append(f"{name} {value:+,.0f}억원")
    if not values:
        return ""
    return "국내 현물 수급은 " + ", ".join(values) + "으로 집계됐습니다."


def _snapshot_price(data, name: str) -> float | None:
    if not data:
        return None
    for items in data.values():
        for item in items:
            item_name = getattr(item, "name", None)
            price = getattr(item, "price", None)
            if isinstance(item, dict):
                item_name = item.get("name")
                price = item.get("price")
            if item_name == name and price is not None:
                try:
                    return float(price)
                except (TypeError, ValueError):
                    return None
    return None


def _observed_issue_lines(signals: list[dict], mode: str, data) -> list[str]:
    lines = []
    if signals:
        market_label = "국내외 시장" if mode == "KR" else "글로벌 시장"
        summary = ", ".join(
            f"{signal['name']} {signal['move']}" for signal in signals[:3]
        )
        lines.append(
            f"1. {market_label}에서 {summary} 변동 관측, 뉴스 원인은 추가 교차확인 필요 "
            "(프로그램 직접 수집)"
        )
    flow = _domestic_flow_sentence(data) if mode == "KR" else ""
    if flow:
        lines.append(f"{len(lines) + 1}. {flow} (한국투자 Open API)")
    return lines


def _rule_based_checkpoints(
    signals: list[dict],
    mode: str,
    news: list[dict],
) -> list[str]:
    names = {signal["name"] for signal in signals}
    points = []
    if mode == "KR":
        points.append("- 외국인 및 기관 현물 수급의 연속성 확인")
    if names & {"WTI", "DXY", "US 2Y Treasury", "US 10Y Treasury", "US 30Y Treasury"}:
        points.append("- 금리, 달러 및 유가 신호가 주식시장에 이어지는지 확인")
    else:
        points.append("- 주요 가격 신호의 다음 거래 연속성 확인")
    if not news:
        points.append("- 글로벌 원인 뉴스의 추가 교차확인")
    return points[:3]


def _build_prompt(
    signals: list[dict],
    mode: str,
    news: list[dict],
    data=None,
) -> str:
    market = "한국 및 아시아 증시" if mode == "KR" else "미국 및 글로벌 증시"

    return f"""
당신은 증권사 리서치센터의 데일리 시황 담당자입니다.

분석 대상: {market}

[자동 탐지 시장 신호]
{_signal_text(signals)}

[프로그램 직접 수집 시장 수치]
{_market_data_text(data)}

[최근 24시간 뉴스 헤드라인]
{_news_text(news)}

위 데이터만 근거로 오늘 시장의 핵심 원인과 이슈를 정리하세요.

작성 원칙:
- 뉴스에 명시된 사실을 우선 사용하세요.
- 여러 기사에서 반복되는 원인을 가장 중요한 원인으로 판단하세요.
- 직접 근거가 있는데도 '원인 확인되지 않음'이라고 쓰지 마세요.
- 뉴스에 없는 사실은 만들지 마세요.
- 헤드라인만으로 인과관계를 확정하거나 기사에 없는 숫자를 추가하지 마세요.
- 숫자는 [프로그램 직접 수집 시장 수치]를 우선하고 뉴스 숫자로 덮어쓰지 마세요.
- 공식 자료 한 곳 또는 서로 다른 허용 매체 두 곳으로 검증된 기사만 제공되었습니다.
- 직접 근거가 약한 항목에만 '추가 확인 필요'라고 표시하세요.
- 특이 변동 신호가 없어도 중요한 정책, 실적, 금리, 환율 이슈는 포함하세요.
- 한국 시장은 외국인 수급, 삼성전자·SK하이닉스, 반도체, 한국은행, 중국 증시, 환율을 우선 연결하세요.
- 한국 시장은 반드시 '해외 허용 매체가 확인한 글로벌 원인 → 프로그램이 직접 수집한 국내 가격·수급 반응' 순서로 서술하세요.
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


def _market_data_text(data) -> str:
    if not data:
        return "- 제공되지 않음"
    lines = []
    seen = set()
    for items in data.values():
        for item in items:
            if item.price is None or item.name in seen:
                continue
            seen.add(item.name)
            move = (
                f", 전일 {item.change_pct:+.2f}%" if item.change_pct is not None else ""
            )
            lines.append(f"- {item.name}: {item.price:,.3f}{move}")
    return "\n".join(lines[:30]) or "- 제공되지 않음"


def _has_required_analysis_sections(analysis: str) -> bool:
    headings = ("[시장 해석]", "[핵심 이슈]", "[체크 포인트]")
    positions = [analysis.find(heading) for heading in headings]
    return all(position >= 0 for position in positions) and positions == sorted(
        positions
    )


def _analysis_uses_only_supported_numbers(
    analysis: str,
    signals: list[dict],
    news: list[dict],
    data=None,
) -> bool:
    support_text = "\n".join(
        [
            _signal_text(signals),
            _market_data_text(data),
            *(article.get("title", "") for article in news),
        ]
    )
    supported = _number_tokens(support_text)
    without_list_numbers = re.sub(r"(?m)^\s*\d+\.\s*", "", analysis)
    used = _number_tokens(without_list_numbers)
    return used <= supported


def _number_tokens(text: str) -> set[str]:
    tokens = set()
    for match in re.findall(r"(?<![\w])[-+]?\d[\d,]*(?:\.\d+)?", text):
        normalized = match.replace(",", "").lstrip("+")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        if normalized in {"-0", ""}:
            normalized = "0"
        tokens.add(normalized)
        tokens.add(normalized.lstrip("-"))
    return tokens


def _call_gemini(
    api_key: str,
    prompt: str,
    attempts: int = 2,
) -> str | None:
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 4096,
        },
    }

    result = None
    for attempt in range(1, max(1, attempts) + 1):
        request = Request(
            GEMINI_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=35) as response:
                result = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code == 429 or 500 <= exc.code < 600
            logger.warning(
                "Gemini HTTP error %s (attempt %s/%s): %s",
                exc.code,
                attempt,
                attempts,
                error_body[:1000],
            )
            if not retryable or attempt >= attempts:
                return None
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning(
                "Gemini request failed (attempt %s/%s): %s",
                attempt,
                attempts,
                exc,
            )
            if attempt >= attempts:
                return None
        time.sleep(1)

    if result is None:
        return None

    candidates = result.get(
        "candidates",
        [],
    )

    if not candidates:
        logger.warning("Gemini returned no candidates")
        return None

    candidate = candidates[0]

    finish_reason = candidate.get(
        "finishReason",
        "",
    )

    parts = candidate.get("content", {}).get("parts", [])

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

    if finish_reason and finish_reason != "STOP":
        logger.warning(
            "Gemini finish reason: %s",
            finish_reason,
        )

    return text or None


def analyze_market(
    signals: list[dict],
    mode: str,
    data=None,
) -> str | None:
    news = _fetch_news(
        signals,
        mode,
    )

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        logger.warning("GEMINI_API_KEY missing")

        return _fallback(
            signals,
            news,
            mode,
            data,
        )

    prompt = _build_prompt(
        signals,
        mode,
        news,
        data,
    )

    analysis = _call_gemini(
        api_key,
        prompt,
    )

    if (
        analysis
        and _has_required_analysis_sections(analysis)
        and _analysis_uses_only_supported_numbers(analysis, signals, news, data)
    ):
        return analysis

    if analysis:
        logger.warning("Gemini response failed section or numeric evidence validation")

    return _fallback(
        signals,
        news,
        mode,
        data,
    )
