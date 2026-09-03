from __future__ import annotations

import json
import os
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

KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_PATH = "/oauth2/tokenP"
INVESTOR_PATH = "/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market"
PROGRAM_PATH = "/uapi/domestic-stock/v1/quotations/comp-program-trade-daily"
INDEX_PATH = "/uapi/domestic-stock/v1/quotations/inquire-index-price"
SECTOR_PATH = "/uapi/domestic-stock/v1/quotations/inquire-index-category-price"

MARKETS = {
    "KOSPI": {"index": "0001", "market": "KSP", "class": "K"},
    "KOSDAQ": {"index": "1001", "market": "KSQ", "class": "Q"},
}


class KisApiError(RuntimeError):
    pass


def million_won_to_100m(value: float | int | str | None) -> float | None:
    """Convert KIS transaction-amount fields (KRW millions) to KRW 100 millions."""
    parsed = _number(value)
    return parsed / 100 if parsed is not None else None


def fetch_kis_market_state(today: date | None = None) -> dict[str, list]:
    app_key = os.environ.get("KIS_APP_KEY", "").strip()
    app_secret = os.environ.get("KIS_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        logger.warning("KIS credentials missing; domestic market state omitted")
        return unavailable_kis_market_state("한투 API 키 미등록")

    target = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    fetched_at = utc_now_iso()

    try:
        token = _fetch_access_token(app_key, app_secret)
    except KisApiError as exc:
        logger.warning("KIS authentication failed: %s", exc)
        return unavailable_kis_market_state("한투 인증 실패")

    flow = []
    breadth = []
    sector_rows = []
    observed_dates: list[str] = []

    for market_name, market in MARKETS.items():
        try:
            payload = _kis_get(
                INVESTOR_PATH,
                "FHPTJ04040000",
                {
                    "FID_COND_MRKT_DIV_CODE": "U",
                    "FID_INPUT_ISCD": market["index"],
                    "FID_INPUT_DATE_1": target.strftime("%Y%m%d"),
                    "FID_INPUT_ISCD_1": market["market"],
                    "FID_INPUT_DATE_2": target.strftime("%Y%m%d"),
                    "FID_INPUT_ISCD_2": market["index"],
                },
                token,
                app_key,
                app_secret,
            )
            row = _latest_dated_row(_rows(payload, "output"), target)
            if row:
                as_of = _iso_date(row.get("stck_bsop_date"))
                if as_of:
                    observed_dates.append(as_of)
                flow.extend(
                    _build_investor_flow(
                        market_name,
                        row,
                        as_of,
                        fetched_at,
                        target,
                    )
                )
            else:
                logger.warning("KIS investor data missing for %s", market_name)
        except KisApiError as exc:
            logger.warning("KIS investor request failed for %s: %s", market_name, exc)

        try:
            payload = _kis_get(
                INDEX_PATH,
                "FHPUP02100000",
                {
                    "FID_COND_MRKT_DIV_CODE": "U",
                    "FID_INPUT_ISCD": market["index"],
                },
                token,
                app_key,
                app_secret,
            )
            rows = _rows(payload, "output")
            if rows:
                breadth.extend(
                    _build_market_breadth(
                        market_name,
                        rows[0],
                        None,
                        fetched_at,
                    )
                )
            else:
                logger.warning("KIS index data missing for %s", market_name)
        except KisApiError as exc:
            logger.warning("KIS index request failed for %s: %s", market_name, exc)

        try:
            payload = _kis_get(
                SECTOR_PATH,
                "FHPUP02140000",
                {
                    "FID_COND_MRKT_DIV_CODE": "U",
                    "FID_INPUT_ISCD": market["index"],
                    "FID_COND_SCR_DIV_CODE": "20214",
                    "FID_MRKT_CLS_CODE": market["class"],
                    "FID_BLNG_CLS_CODE": "0",
                },
                token,
                app_key,
                app_secret,
            )
            sector_rows.extend(
                (market_name, row) for row in _rows(payload, "output2")
            )
        except KisApiError as exc:
            logger.warning("KIS sector request failed for %s: %s", market_name, exc)

    try:
        start = target - timedelta(days=10)
        payload = _kis_get(
            PROGRAM_PATH,
            "FHPPG04600001",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_MRKT_CLS_CODE": "K",
                "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": target.strftime("%Y%m%d"),
            },
            token,
            app_key,
            app_secret,
        )
        row = _latest_dated_row(_rows(payload, "output"), target)
        if row:
            as_of = _iso_date(row.get("stck_bsop_date"))
            if as_of:
                observed_dates.append(as_of)
            flow.extend(_build_program_flow(row, as_of, fetched_at, target))
        else:
            logger.warning("KIS KOSPI program-trade data missing")
    except KisApiError as exc:
        logger.warning("KIS program-trade request failed: %s", exc)

    market_as_of = max(observed_dates) if observed_dates else target.isoformat()
    breadth = _apply_as_of(breadth, market_as_of, target)
    sectors = _build_sector_leaders(sector_rows, market_as_of, fetched_at, target)

    state = {
        "domestic_flow": flow,
        "market_breadth": breadth,
        "sector_performance": sectors,
    }
    if not any(state.values()):
        return unavailable_kis_market_state("한투 시세 수집 실패")

    logger.info("KIS KOSPI200 futures flow omitted: no verified quote-only endpoint")
    logger.info("KIS 52-week breadth omitted: no verified bulk market field")
    return state


def unavailable_kis_market_state(reason: str) -> dict[str, list]:
    return {
        "domestic_flow": [
            build_snapshot(
                "국내 수급 및 시장 체력",
                None,
                source="KIS",
                warning=reason,
            )
        ],
        "market_breadth": [],
        "sector_performance": [],
    }


def _fetch_access_token(app_key: str, app_secret: str) -> str:
    payload = json.dumps(
        {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        }
    ).encode("utf-8")
    request = Request(
        f"{KIS_BASE_URL}{TOKEN_PATH}",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    result = _request_json(request)
    token = str(result.get("access_token", "")).strip()
    if not token:
        raise KisApiError(str(result.get("error_description") or "token missing"))
    return token


def _kis_get(path, tr_id, params, token, app_key, app_secret) -> dict:
    request = Request(
        f"{KIS_BASE_URL}{path}?{urlencode(params)}",
        headers={
            "Authorization": f"Bearer {token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="GET",
    )
    result = _request_json(request)
    if str(result.get("rt_cd", "0")) != "0":
        code = result.get("msg_cd", "unknown")
        message = result.get("msg1", "request failed")
        raise KisApiError(f"{code}: {message}")
    return result


def _request_json(request: Request) -> dict:
    try:
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise KisApiError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise KisApiError("network error") from exc
    except json.JSONDecodeError as exc:
        raise KisApiError("invalid JSON response") from exc
    if not isinstance(result, dict):
        raise KisApiError("invalid response body")
    return result


def _rows(payload: dict, key: str) -> list[dict]:
    value = payload.get(key)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


def _latest_dated_row(rows: list[dict], target: date) -> dict | None:
    candidates = []
    for row in rows:
        parsed = _parse_date(row.get("stck_bsop_date"))
        if parsed and parsed <= target:
            candidates.append((parsed, row))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _build_investor_flow(market, row, as_of, fetched_at, today=None):
    stale = is_stale_as_of(as_of, today)
    snapshots = []
    for label, field in (
        ("외국인", "frgn_ntby_tr_pbmn"),
        ("기관", "orgn_ntby_tr_pbmn"),
    ):
        value = million_won_to_100m(row.get(field))
        if value is None:
            logger.warning("KIS %s %s field missing", market, field)
            continue
        if stale:
            logger.warning("KIS %s investor data stale as of %s", market, as_of)
            continue
        snapshots.append(
            build_snapshot(
                f"{label} {market} 현물",
                value,
                value_format=ValueFormat.KRW_100M,
                as_of=as_of,
                fetched_at=fetched_at,
                source="KIS",
            )
        )
    return snapshots


def _build_program_flow(row, as_of, fetched_at, today=None):
    stale = is_stale_as_of(as_of, today)
    snapshots = []
    for label, field in (
        ("차익", "arbt_smtn_ntby_tr_pbmn"),
        ("비차익", "nabt_smtn_ntby_tr_pbmn"),
    ):
        value = million_won_to_100m(row.get(field))
        if value is None:
            logger.warning("KIS program field missing: %s", field)
            continue
        if stale:
            logger.warning("KIS program data stale as of %s", as_of)
            continue
        snapshots.append(
            build_snapshot(
                f"프로그램 {label}",
                value,
                value_format=ValueFormat.KRW_100M,
                as_of=as_of,
                fetched_at=fetched_at,
                source="KIS",
            )
        )
    return snapshots


def _build_market_breadth(market, row, as_of, fetched_at):
    values = (
        ("상승 종목", row.get("ascn_issu_cnt"), ValueFormat.INTEGER),
        ("하락 종목", row.get("down_issu_cnt"), ValueFormat.INTEGER),
        (
            "거래대금",
            million_won_to_100m(row.get("acml_tr_pbmn")),
            ValueFormat.KRW_100M,
        ),
    )
    snapshots = []
    for label, raw_value, value_format in values:
        value = _number(raw_value)
        if value is None:
            logger.warning("KIS %s %s missing", market, label)
            continue
        snapshots.append(
            build_snapshot(
                f"{market} {label}",
                value,
                value_format=value_format,
                as_of=as_of,
                fetched_at=fetched_at,
                source="KIS",
            )
        )
    return snapshots


def _apply_as_of(snapshots, as_of, today=None):
    if is_stale_as_of(as_of, today):
        logger.warning("KIS index data stale as of %s", as_of)
        return []
    return [
        build_snapshot(
            item.name,
            item.price,
            value_format=item.value_format,
            as_of=as_of,
            fetched_at=item.fetched_at,
            source=item.source,
        )
        for item in snapshots
    ]


def _build_sector_leaders(rows, as_of, fetched_at, today=None):
    if is_stale_as_of(as_of, today):
        logger.warning("KIS sector data stale as of %s", as_of)
        return []

    sectors = {}
    for market, row in rows:
        name = str(row.get("hts_kor_isnm", "")).strip()
        rate = _number(row.get("bstp_nmix_prdy_ctrt"))
        if name.replace(" ", "").upper() in {"코스피", "코스닥", "KOSPI", "KOSDAQ"}:
            continue
        if not name or rate is None:
            continue
        label = name if market in name else f"{market} {name}"
        sectors[label] = rate

    ranked = sorted(sectors.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        logger.warning("KIS sector rows missing")
        return []

    selections = [
        *(("상위", rank, item) for rank, item in enumerate(ranked[:3], 1)),
        *(("하위", rank, item) for rank, item in enumerate(reversed(ranked[-3:]), 1)),
    ]
    snapshots = []
    seen = set()
    for direction, rank, (label, rate) in selections:
        if label in seen:
            continue
        seen.add(label)
        snapshots.append(
            build_snapshot(
                f"업종 {direction} {rank}: {label}",
                rate,
                value_format=ValueFormat.PERCENT_2,
                as_of=as_of,
                fetched_at=fetched_at,
                source="KIS",
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


def _parse_date(value) -> date | None:
    text = str(value or "").strip().replace("-", "")
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _iso_date(value) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None
