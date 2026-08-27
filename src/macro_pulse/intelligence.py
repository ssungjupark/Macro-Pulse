from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core.logging import get_logger


logger = get_logger(__name__)

MODEL = "gemini-2.5-flash"
API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:generateContent"
)


def analyze_market(signals: list[dict], mode: str) -> str | None:
    if not signals:
        return None

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        logger.warning("GEMINI_API_KEY missing")
        return None

    signal_text = "\n".join(
        f"- {x['name']}: {x['move']} ({x['direction']})"
        for x in signals[:5]
    )

    market = (
        "한국 및 아시아 증시"
        if mode == "KR"
        else "미국 및 글로벌 증시"
    )

    prompt = f"""
당신은 증권사 리서치센터의 데일리 시황 담당자입니다.

분석 대상: {market}

오늘 탐지된 주요 시장 움직임:
{signal_text}

Google Search를 사용해 가장 최근 거래일의 뉴스를 조사하고
위 움직임의 원인을 분석하세요.

원칙:
- 최신 기사와 공식 자료를 우선 사용
- 숫자와 직접 관련된 이슈만 사용
- 확인되지 않은 원인은 추측하지 않기
- 시장에 중요한 내용만 짧게 작성
- 투자 추천이나 목표주가 작성 금지

한국 시장이면 외국인 수급, 반도체, 중국 증시,
환율, 금리를 우선 확인하세요.

미국 시장이면 국채금리, Fed, 빅테크,
반도체, 달러를 우선 확인하세요.

아래 형식으로 작성하세요.

[시장 해석]
2~3문장

[핵심 이슈]
1. 핵심 원인
2. 핵심 원인
3. 필요한 경우 추가 원인

[체크 포인트]
앞으로 볼 변수 2~3개
""".strip()

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "tools": [
            {
                "google_search": {}
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1200,
        },
    }

    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=45) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        logger.warning(
            "Gemini HTTP error %s: %s",
            exc.code,
            error_body,
        )
        return None

    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning(
            "Gemini request failed: %s",
            exc,
        )
        return None
