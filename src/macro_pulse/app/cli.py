from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
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
from ..events import get_upcoming_events, insert_event_section
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
        "[시장 해석]\n검증된 자동 해석 없음\n\n"
        "[핵심 이슈]\n검증 조건을 충족한 핵심 이슈 없음\n\n"
        "[체크 포인트]\n공식 일정과 데이터 정상화 여부 확인"
    )
    normalized_analysis = insert_event_section(normalized_analysis, events)
    signal_section = "\n".join(signal_lines)
    return f"{base_summary}\n\n{signal_section}\n\n{normalized_analysis}"


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

    data = fetch_all_data()

    html_report = generate_html_report(data)

    base_summary = generate_telegram_summary(
        data,
        mode,
        report_format_config,
    )

    signals = select_representative_signals(detect_signals(data))

    analysis = analyze_market(signals, mode, data)
    telegram_summary = compose_telegram_report(
        base_summary,
        signals,
        analysis,
        get_upcoming_events(),
    )

    logger.info(
        "Telegram Summary (%s):\n%s\n",
        mode,
        telegram_summary,
    )

    output_path = Path("macro_pulse_report.html")

    output_path.write_text(
        html_report,
        encoding="utf-8",
    )

    logger.info(
        "Report saved to %s",
        output_path,
    )

    if args.dry_run:
        logger.info("Dry run complete. No notifications sent.")
        return 0

    screenshot_paths = capture_screenshots(
        get_screenshot_targets(
            mode,
            report_format_config,
        )
    )

    try:
        telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")

        telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

        if telegram_token and telegram_chat_id:
            await send_telegram_report(
                telegram_token,
                telegram_chat_id,
                telegram_summary,
                image_paths=screenshot_paths,
            )

    finally:
        cleanup_files(screenshot_paths)

    return 0
