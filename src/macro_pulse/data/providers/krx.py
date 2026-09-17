from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ...core.logging import get_logger
from ...domain.models import ValueFormat
from ..quality import is_stale_as_of, utc_now_iso
from ..snapshots import build_snapshot


logger = get_logger(__name__)

KRX_JSON_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
KRX_REFERER = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
REQUEST_TIMEOUT_SECONDS = 4
MAX_WORKERS = 3

MARKET_NAMES = {"STK": "KOSPI", "KSQ": "KOSDAQ"}
INDEX_MARKETS = {"02": "KOSPI", "03": "KOSDAQ"}
INSTITUTION_NAMES = (
    "금융투자",
    "보험",
    "투신",
    "사모",
    "은행",
    "기타금융",
    "연기금",
)
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
SECTOR_EXCLUDE_KEYWORDS = (
    "레버리지",
    "인버스",
    "커버드콜",
    "선물",
    "ETF",
    "ETN",
    "F-",
)


def won_to_100m(value: float | int | str | None) -> float | None:
    parsed = _number(value)
    return parsed / 100_000_000 if parsed is not None else None


def fetch_krx_market_state(today: date | None = None) -> dict[str, list]:
    """Fetch KRX cash-market flow/breadth without broker authentication.

    On normal weekdays we only accept the requested day's data so a delayed KRX
    update can never silently turn into yesterday's flow. Weekend manual runs
    may fall back to the most recent weekday.
    """
    target = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    candidates = _candidate_dates(target)

    for trading_date in candidates:
        state = _fetch_for_date(trading_date, expected_date=target)
        if state is not None:
            return state

    logger.warning("KRX official market data unavailable for %s", target)
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


def _candidate_dates(target: date) -> list[date]:
    if target.weekday() < 5:
        return [target]

    candidates = []
    for offset in range(1, 8):
        candidate = target - timedelta(days=offset)
        if candidate.weekday() < 5:
            candidates.append(candidate)
            if len(candidates) >= 2:
                break
    return candidates


def _fetch_for_date(
    trading_date: date,
    expected_date: date | None = None,
) -> dict[str, list] | None:
    as_of = trading_date.isoformat()
    fetched_at = utc_now_iso()
    stale = is_stale_as_of(as_of) or (
        expected_date is not None
        and expected_date.weekday() < 5
        and trading_date != expected_date
    )
    ymd = trading_date.strftime("%Y%m%d")

    request_specs: dict[str, tuple[str, dict]] = {
        "market_STK": (
            "dbms/MDC/STAT/standard/MDCSTAT01501",
            {"mktId": "STK", "trdDd": ymd},
        ),
        "market_KSQ": (
            "dbms/MDC/STAT/standard/MDCSTAT01501",
            {"mktId": "KSQ", "trdDd": ymd},
        ),
        "investor_STK": (
            "dbms/MDC/STAT/standard/MDCSTAT02201",
            {
                "strtDd": ymd,
                "endDd": ymd,
                "mktId": "STK",
                "etf": "",
                "etn": "",
                "elw": "",
            },
        ),
        "investor_KSQ": (
            "dbms/MDC/STAT/standard/MDCSTAT02201",
            {
                "strtDd": ymd,
                "endDd": ymd,
                "mktId": "KSQ",
                "etf": "",
                "etn": "",
                "elw": "",
            },
        ),
        "program": (
            "dbms/MDC/STAT/standard/MDCSTAT02601",
            {"strtDd": ymd, "endDd": ymd, "mktId": "STK"},
        ),
        "sector_02": (
            "dbms/MDC/STAT/standard/MDCSTAT00101",
            {"trdDd": ymd, "idxIndMidclssCd": "02"},
        ),
        "sector_03": (
            "dbms/MDC/STAT/standard/MDCSTAT00101",
            {"trdDd": ymd, "idxIndMidclssCd": "03"},
        ),
    }

    fetched: dict[str, list[dict] | None] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_key = {
            executor.submit(_post_krx, bld, **params): key
            for key, (bld, params) in request_specs.items()
        }
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                fetched[key] = future.result()
            except Exception as exc:  # defensive: one source must not stop the report
                logger.warning("KRX request task failed for %s: %s", key, exc)
                fetched[key] = None

    raw_rows = [rows for rows in fetched.values() if rows]
    if not raw_rows:
        return None

    flow = []
    breadth = []
    sector_rows = []

    for market_id, market_name in MARKET_NAMES.items():
        market_rows = fetched.get(f"market_{market_id}") or []
        investor_rows = fetched.get(f"investor_{market_id}") or []
        breadth.extend(
            _build_breadth(market_name, market_rows, as_of, fetched_at, stale)
        )
        flow.extend(
            _build_investor_flow(market_name, investor_rows, as_of, fetched_at, stale)
        )

    program_rows = fetched.get("program") or []
    flow.extend(_build_program_flow(program_rows, as_of, fetched_at, stale))

    for index_market, market_name in INDEX_MARKETS.items():
        rows = fetched.get(f"sector_{index_market}") or []
        sector_rows.extend((market_name, row) for row in rows)

    sectors = _build_sector_leaders(sector_rows, as_of, fetched_at, stale)
    if not sectors:
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
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            ),
            "Referer": KRX_REFERER,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("KRX request failed for %s: %s", bld, exc)
        return None

    for key in ("OutBlock_1", "output", "result"):
        rows = result.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _build_investor_flow(market, rows, as_of, fetched_at, stale=False):
    by_name = {
        str(row.get("INVST_TP_NM", "")).replace(" ", ""): row for row in rows
    }

    foreign_value = _row_value(by_name, ("외국인", "외국인합계"))
    individual_value = _row_value(by_name, ("개인",))
    pension_value = _row_value(by_name, ("연기금", "연기금등"))

    institution_value = _row_value(by_name, ("기관합계", "기관"))
    if institution_value is None:
        institution_parts = [
            _row_value(by_name, (name,)) for name in INSTITUTION_NAMES
        ]
        available_parts = [value for value in institution_parts if value is not None]
        if available_parts:
            institution_value = sum(available_parts)

    values = (
        ("외국인", foreign_value),
        ("기관", institution_value),
        ("개인", individual_value),
        ("연기금", pension_value),
    )
    snapshots = []
    for label, value in values:
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


def _row_value(by_name: dict, aliases: tuple[str, ...]) -> float | None:
    for alias in aliases:
        row = by_name.get(alias.replace(" ", ""))
        if not row:
            continue
        value = won_to_100m(row.get("NETBID_TRDVAL"))
        if value is not None:
            return value
    return None


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
    by_name = {
        str(row.get("ITM_TP_NM", "")).replace(" ", ""): row for row in rows
    }
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
        if any(keyword in index_name for keyword in SECTOR_EXCLUDE_KEYWORDS):
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
            "개인 KOSPI 현물",
            "연기금 KOSPI 현물",
            "외국인 KOSDAQ 현물",
            "기관 KOSDAQ 현물",
            "개인 KOSDAQ 현물",
            "연기금 KOSDAQ 현물",
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
