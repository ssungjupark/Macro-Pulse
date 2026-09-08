"""Resolve a report's market and session date before starting the runtime."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def resolve_delivery_context(
    config: dict,
    event: str,
    trigger_cron: str = "",
    manual_market: str = "AUTO",
    now: datetime | None = None,
) -> dict[str, str]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    market = manual_market.upper()
    session = current
    if event == "schedule":
        for mode, mode_config in config["modes"].items():
            schedule = mode_config.get("workflow_schedule", {})
            crons = [schedule.get("cron")]
            crons.extend(item["cron"] for item in schedule.get("backups", []))
            if trigger_cron not in crons:
                continue
            market = mode
            minute, hour, day, month, weekdays = schedule["cron"].split()
            if (day, month, weekdays) != ("*", "*", "1-5"):
                raise ValueError("Delivery dates currently require weekday schedules")
            session = current.replace(
                hour=int(hour), minute=int(minute), second=0, microsecond=0
            )
            while session > current or session.weekday() >= 5:
                session -= timedelta(days=1)
            break
        else:
            raise ValueError(f"Unknown scheduled cron: {trigger_cron}")
    if market not in {"KR", "US", "AUTO"}:
        raise ValueError(f"Unknown market: {market}")
    report_date = session.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
    return {
        "market": market,
        "report_date": report_date,
        "cache_key": f"macro-pulse-sent-v1-{market}-{report_date}",
    }


def main() -> None:
    config = json.loads(
        Path(
            os.environ.get("REPORT_FORMAT_CONFIG", "config/report_formats.json")
        ).read_text(encoding="utf-8")
    )
    context = resolve_delivery_context(
        config,
        os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch"),
        os.environ.get("TRIGGER_CRON", ""),
        os.environ.get("MANUAL_MARKET", "AUTO"),
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for key, value in context.items():
            output.write(f"{key}={value}\n")
    print(f"Report market={context['market']}, session={context['report_date']}")


if __name__ == "__main__":
    main()
