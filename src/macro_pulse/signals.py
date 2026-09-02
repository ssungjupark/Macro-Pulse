from __future__ import annotations

from .domain.models import ReportDataset, ValueFormat


# 자산별 "눈여겨볼 만한 하루 움직임" 기준
PCT_THRESHOLDS = {
    "indices_domestic": 1.0,      # 주가지수 ±1.0%
    "indices_overseas": 1.0,      # 주가지수 ±1.0%
    "volatility": 5.0,            # VIX, VKOSPI ±5.0%
    "commodities": 1.5,           # 금, 은, 구리 ±1.5%
    "treasuries": 1.0,            # 실제 판정은 아래 bp 기준 사용
    "exchange": 0.5,              # 환율 ±0.5%
    "crypto": 3.0,                # 비트코인, 이더리움 ±3.0%
}

# 국채금리는 하루 5bp 이상 움직이면 신호로 판단
YIELD_BP_THRESHOLD = 5.0


def detect_signals(data: ReportDataset) -> list[dict]:
    signals = []

    for category, items in data.items():
        threshold = PCT_THRESHOLDS.get(category, 1.0)

        for item in items:
            if item.price is None:
                continue

            if item.value_format == ValueFormat.BASIS_POINTS_1:
                if item.change is None:
                    continue
                if abs(item.change) >= YIELD_BP_THRESHOLD:
                    signals.append(
                        {
                            "name": item.name,
                            "category": category,
                            "direction": "확대" if item.change > 0 else "축소",
                            "move": f"{item.change:+.1f}bp",
                            "score": abs(item.change) / YIELD_BP_THRESHOLD,
                        }
                    )
                continue

            # 금리는 % 등락률이 아니라 bp 변화로 판단
            if item.value_format == ValueFormat.YIELD_3:
                if item.change is None:
                    continue

                change_bp = item.change * 100

                if abs(change_bp) >= YIELD_BP_THRESHOLD:
                    signals.append(
                        {
                            "name": item.name,
                            "category": category,
                            "direction": "상승" if change_bp > 0 else "하락",
                            "move": f"{change_bp:+.1f}bp",
                            "score": abs(change_bp) / YIELD_BP_THRESHOLD,
                        }
                    )

                continue

            # 나머지 자산은 하루 등락률 기준
            if item.change_pct is None:
                continue

            if abs(item.change_pct) >= threshold:
                signals.append(
                    {
                        "name": item.name,
                        "category": category,
                        "direction": "상승" if item.change_pct > 0 else "하락",
                        "move": f"{item.change_pct:+.2f}%",
                        "score": abs(item.change_pct) / threshold,
                    }
                )

    # 평소 기준보다 크게 움직인 순서대로 정렬
    signals.sort(
        key=lambda signal: signal["score"],
        reverse=True,
    )

    return signals
