from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from ..config.report_formats import (
    get_screenshot_targets,
    load_report_format_config,
)
from ..core.artifacts import cleanup_files
from ..core.logging import configure_logging, get_logger
from ..data.market_data import fetch_all_data
from ..delivery.notifier import send_telegram_report
from ..event_results import (
    build_recent_event_result_section,
    insert_event_result_section,
)
from ..events import get_upcoming_events, insert_event_section
from ..fomc_results import build_recent_fomc_result_section
from ..intelligence import analyze_market
from ..reporting.generator import (
    generate_html_report,
    generate_telegram_summary,
)
from ..reporting.screenshots import capture_screenshots
from ..signals import (
    detect_signals,
    format_signal_context,
    select_representative_signals,
)


load_dotenv()
configure_logging()
logger = get_logger(__name__)


def resolve_mode(
    market_arg: str | None,
    now_utc: datetime | None = None,
) -> str:
    normalized = (market_arg or "").strip().upper()

    if normalized in {"KR", "US"}:
        return normalized

    current_time = now_utc or datetime.now(timezone.utc)

    return "KR" if 7 <= current_time.hour < 20 else "US"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Macro Pulse Bot")

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate report but do not send",
    )

    parser.add_argument(
        "--market",
        type=str,
        default="Global",
        help="Market context override (KR/US).",
    )

    return parser


def compose_telegram_report(
    base_summary: str,
    signals: list[dict],
    analysis: str | None,
    events,
    event_results: str = "",
) -> str:
    signal_lines = ["[주요 변동 신호]"]
    if signals:
        for signal in signals[:5]:
            context = format_signal_context(signal)
            context_suffix = f" | {context}" if context else ""
            signal_lines.append(
                f"{signal['name']}: {signal['move']} "
                f"({signal['direction']}){context_suffix}"
            )
    else:
        signal_lines.append("기준치 이상의 특이 변동 신호 없음")

    normalized_analysis = analysis or (
        "[오늘의 핵심 이슈]\n검증 기준을 충족한 주요 뉴스를 수집하지 못했습니다."
    )
    normalized_analysis = insert_event_result_section(
        normalized_analysis,
        event_results,
    )
    normalized_analysis = insert_event_section(normalized_analysis, events)
    signal_section = "\n".join(signal_lines)
    return f"{base_summary}\n\n{signal_section}\n\n{normalized_analysis}"


def build_event_results(events) -> str:
    sections = []

    fomc_section = build_recent_fomc_result_section(events)
    if fomc_section:
        sections.append(fomc_section.removeprefix("[발표 결과]\n"))

    non_fomc_events = [event for event in events if "FOMC" not in event.title]
    generic_section = build_recent_event_result_section(non_fomc_events)
    if generic_section:
        sections.append(generic_section.removeprefix("[발표 결과]\n"))

    if not sections:
        return ""

    return "[발표 결과]\n" + "\n\n".join(sections)


async def main(
    argv: list[str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)

    mode = resolve_mode(args.market)
    report_format_config = load_report_format_config()

    logger.info(
        "Starting Macro Pulse Bot (mode=%s)",
        mode,
    )

    data = fetch_all_data(mode)

    base_summary = generate_telegram_summary(
        data,
        mode,
        report_format_config,
    )
    if mode == "KR":
        base_summary = (
            "[KRX 정규장 마감 | 15:30 기준]\n\n"
            f"{base_summary}"
        )

    signals = select_representative_signals(detect_signals(data))

    analysis = analyze_market(signals, mode, data)
    today = datetime.now(timezone.utc).date()
    recent_start = today - timedelta(days=2)
    recent_events = [
        event
        for event in get_upcoming_events(recent_start, limit=20)
        if recent_start <= event.event_date <= today
    ]
    event_results = build_event_results(recent_events)
    telegram_summary = compose_telegram_report(
        base_summary,
        signals,
        analysis,
        get_upcoming_events(),
        event_results,
    )

    logger.info(
        "Telegram Summary (%s):\n%s\n",
        mode,
        telegram_summary,
    )

    output_path = Path("macro_pulse_report.html")

    if args.dry_run:
        output_path.write_text(generate_html_report(data), encoding="utf-8")
        logger.info("Report saved to %s", output_path)
        logger.info("Dry run complete. No notifications sent.")
        return 0

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not telegram_token or not telegram_chat_id:
        raise RuntimeError("Telegram credentials missing; report was not delivered")

    delivery_receipt_path = os.environ.get("DELIVERY_RECEIPT_PATH")

    # Send the text as soon as the report body is ready. Screenshots are optional
    # follow-up media and must not delay the market-close message.
    delivered = await send_telegram_report(
        telegram_token,
        telegram_chat_id,
        telegram_summary,
        delivery_receipt_path=delivery_receipt_path,
    )
    if not delivered:
        raise RuntimeError("Telegram report delivery failed")

    # HTML is an auxiliary artifact. Do it only after the time-sensitive
    # Telegram text has already been delivered.
    try:
        output_path.write_text(generate_html_report(data), encoding="utf-8")
        logger.info("Report saved to %s", output_path)
    except Exception as exc:
        logger.warning("Optional HTML report generation failed: %s", exc)

    screenshot_paths = []
    try:
        screenshot_paths = capture_screenshots(
            get_screenshot_targets(
                mode,
                report_format_config,
            )
        )
        if screenshot_paths:
            photos_delivered = await send_telegram_report(
                telegram_token,
                telegram_chat_id,
                image_paths=screenshot_paths,
                attempts=1,
                send_text=False,
            )
            if not photos_delivered:
                logger.warning(
                    "Telegram text was delivered, but one or more screenshots failed"
                )
    except Exception as exc:
        logger.exception(
            "Telegram text was delivered, but screenshot follow-up failed: %s",
            exc,
        )
    finally:
        cleanup_files(screenshot_paths)

    return 0
