from __future__ import annotations

import json
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ...core.logging import get_logger
from ...domain.models import ValueFormat
from ..quality import is_stale_as_of, utc_now_iso
from ..snapshots import build_snapshot


logger = get_logger(__name__)

KRX_JSON_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
MARKET_NAMES = {"STK": "KOSPI", "KSQ": "KOSDAQ"}
INDEX_MARKETS = {"02": "KOSPI", "03": "KOSDAQ"}
SECTOR_KEYWORDS = (
    "음식료",
    "담배",
    "섬유",
    "의류",
    "종이",
    "목재",
    "화학",
    "제약",
    "비금속",
    "금속",
    "기계",
    "장비",
    "전기",
    "전자",
    "의료",
    "정밀",
    "운송",
    "자동차",
    "유통",
    "가스",
    "건설",
    "창고",
    "통신",
    "금융",
    "증권",
    "보험",
    "서비스",
    "제조",
    "소프트웨어",
    "하드웨어",
    "반도체",
    "방송",
    "오락",
    "문화",
)


def won_to_100m(value: float | int | str | None) -> float | None:
    parsed = _number(value)
    return parsed / 100_000_000 if parsed is not None else None


def fetch_krx_market_state(today: date | None = None) -> dict[str, list]:
    target = today or date.today()
    for offset in range(5):
        trading_date = target - timedelta(days=offset)
        if trading_date.weekday() >= 5:
            continue
        state = _fetch_for_date(trading_date)
        if state is None:
            break
        if any(state.values()):
            return state

    logger.warning("KRX official market data unavailable")
    return unavailable_krx_market_state("KRX 수집 실패")


def unavailable_krx_market_state(reason: str) -> dict[str, list]:
    return {
        "domestic_flow": _unavailable_flow_snapshots(reason),
        "market_breadth": _unavailable_breadth_snapshots(reason),
        "sector_performance": [
            build_snapshot(
                "업종 수익률",
                None,
                value_format=ValueFormat.PERCENT_2,
                source="KRX",
                warning=reason,
            )
        ],
    }


def _fetch_for_date(trading_date: date) -> dict[str, list] | None:
    as_of = trading_date.isoformat()
    fetched_at = utc_now_iso()
    stale = is_stale_as_of(as_of)
    flow = []
    breadth = []
    sector_rows = []
    found = False
    transport_failed = False

    for market_id, market_name in MARKET_NAMES.items():
        market_rows = _post_krx(
            "dbms/MDC/STAT/standard/MDCSTAT01501",
            mktId=market_id,
            trdDd=trading_date.strftime("%Y%m%d"),
        )
        if market_rows is None:
            transport_failed = True
            market_rows = []
        investor_rows = _post_krx(
            "dbms/MDC/STAT/standard/MDCSTAT02201",
            strtDd=trading_date.strftime("%Y%m%d"),
            endDd=trading_date.strftime("%Y%m%d"),
            mktId=market_id,
            etf="",
            etn="",
            elw="",
        )
        if investor_rows is None:
            transport_failed = True
            logger.warning("KRX investor data unavailable for %s", market_name)
            investor_rows = []
        if market_rows or investor_rows:
            found = True

        breadth.extend(
            _build_breadth(market_name, market_rows, as_of, fetched_at, stale)
        )
        flow.extend(
            _build_investor_flow(market_name, investor_rows, as_of, fetched_at, stale)
        )

    program_rows = _post_krx(
        "dbms/MDC/STAT/standard/MDCSTAT02601",
        strtDd=trading_date.strftime("%Y%m%d"),
        endDd=trading_date.strftime("%Y%m%d"),
        mktId="STK",
    )
    if program_rows is None:
        transport_failed = True
        program_rows = []
    if program_rows:
        found = True
    flow.extend(_build_program_flow(program_rows, as_of, fetched_at, stale))
    flow.append(
        build_snapshot(
            "외국인 KOSPI200 선물",
            None,
            value_format=ValueFormat.KRW_100M,
            as_of=as_of,
            fetched_at=fetched_at,
            source="KRX",
            warning="안정적인 공식 무료 응답 형식 미확보",
        )
    )
    logger.info("KRX KOSPI200 futures flow omitted: response format not verified")

    for index_market, market_name in INDEX_MARKETS.items():
        rows = _post_krx(
            "dbms/MDC/STAT/standard/MDCSTAT00101",
            trdDd=trading_date.strftime("%Y%m%d"),
            idxIndMidclssCd=index_market,
        )
        if rows is None:
            transport_failed = True
            continue
        if rows:
            found = True
            sector_rows.extend((market_name, row) for row in rows)

    if not found:
        if transport_failed:
            return None
        return {"domestic_flow": [], "market_breadth": []}

    sectors = _build_sector_leaders(
        sector_rows,
        as_of,
        fetched_at,
        stale,
    )
    if not sectors:
        logger.warning("KRX sector returns unavailable for %s", as_of)
        sectors = [
            build_snapshot(
                "업종 수익률",
                None,
                value_format=ValueFormat.PERCENT_2,
                as_of=as_of,
                fetched_at=fetched_at,
                source="KRX",
                warning="KRX 업종 항목 누락",
            )
        ]
    logger.info(
        "KRX 52-week highs/lows omitted: no stable bulk official field verified"
    )
    return {
        "domestic_flow": flow,
        "market_breadth": breadth,
        "sector_performance": sectors,
    }


def _post_krx(
    bld: str,
    **params,
) -> list[dict] | None:
    payload = {
        "bld": bld,
        "locale": "ko_KR",
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
        **params,
    }
    request = Request(
        KRX_JSON_URL,
        data=urlencode(payload).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0 (Macro-Pulse/1.0)",
            "Referer": "https://data.krx.co.kr/",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("KRX request failed for %s: %s", bld, exc)
        return None

    for key in ("OutBlock_1", "output", "result"):
        rows = result.get(key)
        if isinstance(rows, list):
            return rows
    return []


def _build_investor_flow(market, rows, as_of, fetched_at, stale=False):
    by_name = {str(row.get("INVST_TP_NM", "")).replace(" ", ""): row for row in rows}
    snapshots = []
    for label, aliases in (
        ("외국인", ("외국인", "외국인합계")),
        ("기관", ("기관합계", "기관")),
    ):
        row = next(
            (by_name.get(alias) for alias in aliases if by_name.get(alias)), None
        )
        raw_value = row.get("NETBID_TRDVAL") if row else None
        value = won_to_100m(raw_value)
        if stale:
            value = None
        snapshots.append(
            build_snapshot(
                f"{label} {market} 현물",
                value,
                value_format=ValueFormat.KRW_100M,
                as_of=as_of,
                fetched_at=fetched_at,
                source="KRX",
                is_stale=stale,
                warning=(
                    f"오래된 KRX 데이터: {as_of}"
                    if stale
                    else None
                    if value is not None
                    else "KRX 항목 누락"
                ),
            )
        )
    return snapshots


def _build_breadth(market, rows, as_of, fetched_at, stale=False):
    changes = [_number(row.get("CMPPREVDD_PRC")) for row in rows]
    advances = sum(change > 0 for change in changes if change is not None)
    declines = sum(change < 0 for change in changes if change is not None)
    turnover_won = sum(
        value
        for value in (_number(row.get("ACC_TRDVAL")) for row in rows)
        if value is not None
    )
    if not rows:
        return [
            build_snapshot(
                f"{market} {label}",
                None,
                value_format=value_format,
                as_of=as_of,
                fetched_at=fetched_at,
                source="KRX",
                warning="KRX 항목 누락",
            )
            for label, value_format in (
                ("상승 종목", ValueFormat.INTEGER),
                ("하락 종목", ValueFormat.INTEGER),
                ("거래대금", ValueFormat.KRW_100M),
            )
        ]
    return [
        build_snapshot(
            f"{market} 상승 종목",
            None if stale else advances,
            value_format=ValueFormat.INTEGER,
            as_of=as_of,
            fetched_at=fetched_at,
            source="KRX",
            is_stale=stale,
            warning=f"오래된 KRX 데이터: {as_of}" if stale else None,
        ),
        build_snapshot(
            f"{market} 하락 종목",
            None if stale else declines,
            value_format=ValueFormat.INTEGER,
            as_of=as_of,
            fetched_at=fetched_at,
            source="KRX",
            is_stale=stale,
            warning=f"오래된 KRX 데이터: {as_of}" if stale else None,
        ),
        build_snapshot(
            f"{market} 거래대금",
            None if stale else won_to_100m(turnover_won),
            value_format=ValueFormat.KRW_100M,
            as_of=as_of,
            fetched_at=fetched_at,
            source="KRX",
            is_stale=stale,
            warning=f"오래된 KRX 데이터: {as_of}" if stale else None,
        ),
    ]


def _build_program_flow(rows, as_of, fetched_at, stale=False):
    by_name = {str(row.get("ITM_TP_NM", "")).replace(" ", ""): row for row in rows}
    snapshots = []
    for item_name in ("차익", "비차익"):
        row = by_name.get(item_name)
        value = won_to_100m(row.get("NETBID_TRDVAL")) if row else None
        if stale:
            value = None
        snapshots.append(
            build_snapshot(
                f"프로그램 {item_name}",
                value,
                value_format=ValueFormat.KRW_100M,
                as_of=as_of,
                fetched_at=fetched_at,
                source="KRX",
                is_stale=stale,
                warning=(
                    f"오래된 KRX 데이터: {as_of}"
                    if stale
                    else None
                    if value is not None
                    else "KRX 항목 누락"
                ),
            )
        )
    return snapshots


def _build_sector_leaders(rows, as_of, fetched_at, stale=False):
    sectors = {}
    for market_name, row in rows:
        index_name = str(row.get("IDX_NM", "")).strip()
        normalized = index_name.replace(" ", "")
        if not index_name or any(character.isdigit() for character in index_name):
            continue
        if not any(keyword in normalized for keyword in SECTOR_KEYWORDS):
            continue
        rate = _number(row.get("FLUC_RT") or row.get("UPDN_RATE"))
        if rate is None:
            continue
        label = (
            index_name if market_name in index_name else f"{market_name} {index_name}"
        )
        sectors[label] = rate

    ranked = sorted(sectors.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return []
    selected = [
        *(("상위", rank, item) for rank, item in enumerate(ranked[:3], 1)),
        *(("하위", rank, item) for rank, item in enumerate(reversed(ranked[-3:]), 1)),
    ]
    snapshots = []
    seen = set()
    for direction, rank, (label, rate) in selected:
        if label in seen:
            continue
        seen.add(label)
        snapshots.append(
            build_snapshot(
                f"업종 {direction} {rank}: {label}",
                None if stale else rate,
                value_format=ValueFormat.PERCENT_2,
                as_of=as_of,
                fetched_at=fetched_at,
                source="KRX",
                is_stale=stale,
                warning=f"오래된 KRX 데이터: {as_of}" if stale else None,
            )
        )
    return snapshots


def _unavailable_flow_snapshots(reason="KRX 수집 실패"):
    return [
        build_snapshot(
            name,
            None,
            value_format=ValueFormat.KRW_100M,
            source="KRX",
            warning=reason,
        )
        for name in (
            "외국인 KOSPI 현물",
            "기관 KOSPI 현물",
            "외국인 KOSDAQ 현물",
            "기관 KOSDAQ 현물",
            "외국인 KOSPI200 선물",
            "프로그램 차익",
            "프로그램 비차익",
        )
    ]


def _unavailable_breadth_snapshots(reason="KRX 수집 실패"):
    snapshots = []
    for market in ("KOSPI", "KOSDAQ"):
        for label, value_format in (
            ("상승 종목", ValueFormat.INTEGER),
            ("하락 종목", ValueFormat.INTEGER),
            ("거래대금", ValueFormat.KRW_100M),
        ):
            snapshots.append(
                build_snapshot(
                    f"{market} {label}",
                    None,
                    value_format=value_format,
                    source="KRX",
                    warning=reason,
                )
            )
    return snapshots


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None
