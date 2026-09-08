from __future__ import annotations

from pathlib import Path

from ..config.report_formats import load_report_format_config
from ..domain.models import ReportFormatConfig, normalize_report_format_config


SCHEDULE_BLOCK_START = "    # BEGIN GENERATED SCHEDULES"
SCHEDULE_BLOCK_END = "    # END GENERATED SCHEDULES"
DEFAULT_DAILY_WORKFLOW_PATH = ".github/workflows/daily_report.yml"


def get_workflow_schedule_entries(
    format_config: ReportFormatConfig | dict | None = None,
) -> list[tuple[str, str, str, str, str, str]]:
    config = normalize_report_format_config(
        format_config or load_report_format_config()
    )
    entries: list[tuple[str, str, str, str, str, str]] = []

    for mode, mode_config in config.modes.items():
        schedule = mode_config.workflow_schedule
        if schedule is None:
            continue
        entries.append(
            (
                mode,
                schedule.cron,
                schedule.local_time,
                schedule.utc_time,
                schedule.weekdays,
                "primary",
            )
        )
        entries.extend(
            (
                mode,
                backup.cron,
                backup.local_time,
                backup.utc_time,
                schedule.weekdays,
                "backup",
            )
            for backup in schedule.backups
        )

    if not entries:
        raise ValueError("At least one workflow schedule must be defined in config.")

    return entries


def render_daily_workflow_schedule_block(
    format_config: ReportFormatConfig | dict | None = None,
) -> str:
    lines = [SCHEDULE_BLOCK_START]
    for (
        mode,
        cron,
        local_time,
        utc_time,
        weekdays,
        role,
    ) in get_workflow_schedule_entries(format_config):
        lines.append(f"    # {mode} {role} | {local_time} | {utc_time} | {weekdays}")
        lines.append(f"    - cron: '{cron}'")
    lines.append(SCHEDULE_BLOCK_END)
    return "\n".join(lines)


def update_generated_schedule_block(workflow_text: str, schedule_block: str) -> str:
    if (
        SCHEDULE_BLOCK_START not in workflow_text
        or SCHEDULE_BLOCK_END not in workflow_text
    ):
        raise ValueError("Workflow file is missing generated schedule block markers.")

    start = workflow_text.index(SCHEDULE_BLOCK_START)
    end = workflow_text.index(SCHEDULE_BLOCK_END) + len(SCHEDULE_BLOCK_END)
    return workflow_text[:start] + schedule_block + workflow_text[end:]


def sync_daily_workflow_from_config(
    workflow_path: str | Path = DEFAULT_DAILY_WORKFLOW_PATH,
    format_config: ReportFormatConfig | dict | None = None,
) -> str:
    path = Path(workflow_path)
    updated_text = update_generated_schedule_block(
        path.read_text(encoding="utf-8"),
        render_daily_workflow_schedule_block(format_config),
    )
    path.write_text(updated_text, encoding="utf-8")
    return updated_text


def workflow_matches_config(
    workflow_text: str,
    format_config: ReportFormatConfig | dict | None = None,
) -> bool:
    expected_block = render_daily_workflow_schedule_block(format_config)
    start = workflow_text.index(SCHEDULE_BLOCK_START)
    end = workflow_text.index(SCHEDULE_BLOCK_END) + len(SCHEDULE_BLOCK_END)
    return workflow_text[start:end] == expected_block


if __name__ == "__main__":
    sync_daily_workflow_from_config()
