"""Resolve market/date context for scheduled and externally dispatched reports."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")

PRIMARY_CRONS = {
    "KR": "30 07 * * 1-5",
    "US": "30 21 * * 1-5",
}

SCHEDULE_MARKETS = {
    "30 07 * * 1-5": "KR",
    "45 07 * * 1-5": "KR",
    "00 08 * * 1-5": "KR",
    "30 21 * * 1-5": "US",
    "45 21 * * 1-5": "US",
    "00 22 * * 1-5": "US",
}


def _scheduled_session_utc(
    market: str,
    current: datetime,
) -> datetime:
    minute, hour, day, month, weekdays = PRIMARY_CRONS[market].split()
    if (day, month, weekdays) != ("*", "*", "1-5"):
        raise ValueError("Only weekday schedules are supported")

    session = current.replace(
        hour=int(hour),
        minute=int(minute),
        second=0,
        microsecond=0,
    )

    while session > current or session.weekday() >= 5:
        session -= timedelta(days=1)

    return session


def resolve_delivery_context(
    event: str,
    trigger_cron: str = "",
    manual_market: str = "AUTO",
    now: datetime | None = None,
) -> dict[str, str]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    if event == "schedule":
        market = SCHEDULE_MARKETS.get(trigger_cron)
        if market is None:
            raise ValueError(f"Unknown scheduled cron: {trigger_cron}")
        session = _scheduled_session_utc(market, current)
    else:
        market = manual_market.strip().upper()
        if market not in {"KR", "US"}:
            raise ValueError(f"Unknown market: {manual_market}")
        session = current

    report_date = session.astimezone(KST).date().isoformat()

    return {
        "market": market,
        "report_date": report_date,
        "cache_key": f"macro-pulse-sent-v2-{market}-{report_date}",
    }


def main() -> None:
    context = resolve_delivery_context(
        event=os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch"),
        trigger_cron=os.environ.get("TRIGGER_CRON", ""),
        manual_market=os.environ.get("MANUAL_MARKET", "AUTO"),
    )

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            for key, value in context.items():
                output.write(f"{key}={value}\n")

    print(
        f"Report market={context['market']}, "
        f"session={context['report_date']}, "
        f"cache={context['cache_key']}"
    )


if __name__ == "__main__":
    main()
