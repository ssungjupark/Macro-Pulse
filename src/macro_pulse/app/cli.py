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
from ..reporting.generator import (
    generate_html_report,
    generate_telegram_summary,
)
from ..reporting.screenshots import capture_screenshots
from ..signals import detect_signals


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
    parser = argparse.ArgumentParser(
        description="Macro Pulse Bot"
    )

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

    telegram_summary = generate_telegram_summary(
        data,
        mode,
        report_format_config,
    )

    signals = detect_signals(data)

    if signals:
        signal_lines = [
            "",
            "[주요 변동 신호]",
        ]

        for signal in signals[:5]:
            signal_lines.append(
                f"{signal['name']}: "
                f"{signal['move']} "
                f"({signal['direction']})"
            )

        telegram_summary += "\n".join(signal_lines)

    logger.info(
        "Telegram Summary (%s):\n%s\n",
        mode,
        telegram_summary,
    )

    output_path = Path(
        "macro_pulse_report.html"
    )

    output_path.write_text(
        html_report,
        encoding="utf-8",
    )

    logger.info(
        "Report saved to %s",
        output_path,
    )

    if args.dry_run:
        logger.info(
            "Dry run complete. No notifications sent."
        )
        return 0

    screenshot_paths = capture_screenshots(
        get_screenshot_targets(
            mode,
            report_format_config,
        )
    )

    try:
        telegram_token = os.environ.get(
            "TELEGRAM_BOT_TOKEN"
        )

        telegram_chat_id = os.environ.get(
            "TELEGRAM_CHAT_ID"
        )

        if telegram_token and telegram_chat_id:
            await send_telegram_report(
                telegram_token,
                telegram_chat_id,
                telegram_summary,
                image_paths=screenshot_paths,
            )

    finally:
        cleanup_files(
            screenshot_paths
        )

    return 0
