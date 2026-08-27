from __future__ import annotations

import json
import os
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .core.logging import get_logger


logger = get_logger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)


def _build_prompt(signals: list[dict], mode: str) -> str:
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    signal_text = "\n".join(
        f"- {signal['name']}: {signal['move']} ({signal['direction']})"
        for signal in signals[:5]
    )

    market_name = "한국 및 아시아 시장" if mode == "KR" else "미국 및 글로벌 시장"

    return f"""
당신은 증권사 리서치센터의 데일리 시황 담당자입니다.

현재 시각은 한국시간 {now_kst:%Y-%m-%d %H:%M}입니다.
분석 대상은 {market_name}입니다.

다음은 시스템이 자동 탐지한 주요 시장 변동입니다.

{signal_text}

Google Search를 이용해 현재 시점에서 가장 최근 거래일의
시장 움직임 원인을 조사하세요.

작성 원칙:
1. 최근 기사와 공식 발표를 우선 확인하세요.
2. 제공된 시장 변동과 직접 관련 있는 이슈만 사용하세요.
3. 확인되지 않은 원인을 만들어내지 마세요.
4. 단순 상관관계를 인과관계로 단정하지 마세요.
5. 한국 시장 분석에서는 외국인 수급, 반도체, 중국 증시,
   환율, 금리를 우선 확인하세요.
6. 미국 시장 분석에서는 국채금리, Fed, 빅테크, 반도체,
   달러, 원자재를 우선 확인하세요.
7. 텔레그램에서 바로 읽을 수 있도록 짧고 명확하게 쓰세요.
8. 투자 추천이나 목표주가는 제시하지 마세요.

반드시 아래 형식으로 작성하세요.

[시장 해석]
오늘 시장의 방향과 가장 중요한 배경을 2~3문장으로 설명

[핵심 이슈]
1. 가장 중요한 원인과 시장 영향
2. 두 번째로 중요한 원인과 시장 영향
3. 필요한 경우 세 번째 원인

[오늘 체크]
앞으로 확인해야 할 변수 2~3개를 한 줄로 정리
""".strip()


def analyze_market(signals: list[dict], mode: str) -> str | None:
    if not signals:
        return None

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        logger.warning("GEMINI_API_KEY is missing. Skipping AI analysis.")
        return None

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": _build_prompt(signals, mode),
                    }
                ]
            }
        ],
        "tools": [
            {
                "google_search": {},
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1400,
        },
    }

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
        with urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.warning(
            "Gemini API HTTP error %s: %s",
            exc.code,
            error_body[:500],
        )
        return None

    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Gemini API request failed: %s", exc)
        return None

    candidates = result.get("candidates", [])

    if not candidates:
        logger.warning("Gemini returned no candidates.")
        return None

    parts = candidates[0].get("content", {}).get("parts", [])

    text_parts = [
        part.get("text", "")
        for part in parts
        if part.get("text")
    ]

    analysis = "\n".join(text_parts).strip()

    if not analysis:
        logger.warning("Gemini returned an empty analysis.")
        return None

    grounding = candidates[0].get("groundingMetadata", {})
    chunks = grounding.get("groundingChunks", [])

    source_titles = []

    for chunk in chunks:
        web = chunk.get("web", {})
        title = web.get("title")

        if title and title not in source_titles:
            source_titles.append(title)

    if source_titles:
        analysis += "\n\n출처: " + ", ".join(source_titles[:5])

    return analysisfrom __future__ import annotations

import json
import os
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .core.logging import get_logger


logger = get_logger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)


def _build_prompt(signals: list[dict], mode: str) -> str:
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    signal_text = "\n".join(
        f"- {signal['name']}: {signal['move']} ({signal['direction']})"
        for signal in signals[:5]
    )

    market_name = "한국 및 아시아 시장" if mode == "KR" else "미국 및 글로벌 시장"

    return f"""
당신은 증권사 리서치센터의 데일리 시황 담당자입니다.

현재 시각은 한국시간 {now_kst:%Y-%m-%d %H:%M}입니다.
분석 대상은 {market_name}입니다.

다음은 시스템이 자동 탐지한 주요 시장 변동입니다.

{signal_text}

Google Search를 이용해 현재 시점에서 가장 최근 거래일의
시장 움직임 원인을 조사하세요.

작성 원칙:
1. 최근 기사와 공식 발표를 우선 확인하세요.
2. 제공된 시장 변동과 직접 관련 있는 이슈만 사용하세요.
3. 확인되지 않은 원인을 만들어내지 마세요.
4. 단순 상관관계를 인과관계로 단정하지 마세요.
5. 한국 시장 분석에서는 외국인 수급, 반도체, 중국 증시,
   환율, 금리를 우선 확인하세요.
6. 미국 시장 분석에서는 국채금리, Fed, 빅테크, 반도체,
   달러, 원자재를 우선 확인하세요.
7. 텔레그램에서 바로 읽을 수 있도록 짧고 명확하게 쓰세요.
8. 투자 추천이나 목표주가는 제시하지 마세요.

반드시 아래 형식으로 작성하세요.

[시장 해석]
오늘 시장의 방향과 가장 중요한 배경을 2~3문장으로 설명

[핵심 이슈]
1. 가장 중요한 원인과 시장 영향
2. 두 번째로 중요한 원인과 시장 영향
3. 필요한 경우 세 번째 원인

[오늘 체크]
앞으로 확인해야 할 변수 2~3개를 한 줄로 정리
""".strip()


def analyze_market(signals: list[dict], mode: str) -> str | None:
    if not signals:
        return None

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        logger.warning("GEMINI_API_KEY is missing. Skipping AI analysis.")
        return None

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": _build_prompt(signals, mode),
                    }
                ]
            }
        ],
        "tools": [
            {
                "google_search": {},
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1400,
        },
    }

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
        with urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.warning(
            "Gemini API HTTP error %s: %s",
            exc.code,
            error_body[:500],
        )
        return None

    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Gemini API request failed: %s", exc)
        return None

    candidates = result.get("candidates", [])

    if not candidates:
        logger.warning("Gemini returned no candidates.")
        return None

    parts = candidates[0].get("content", {}).get("parts", [])

    text_parts = [
        part.get("text", "")
        for part in parts
        if part.get("text")
    ]

    analysis = "\n".join(text_parts).strip()

    if not analysis:
        logger.warning("Gemini returned an empty analysis.")
        return None

    grounding = candidates[0].get("groundingMetadata", {})
    chunks = grounding.get("groundingChunks", [])

    source_titles = []

    for chunk in chunks:
        web = chunk.get("web", {})
        title = web.get("title")

        if title and title not in source_titles:
            source_titles.append(title)

    if source_titles:
        analysis += "\n\n출처: " + ", ".join(source_titles[:5])

    return analysis
