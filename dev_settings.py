from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo


def build_virtual_now(
    selected_date: date,
    selected_time: time,
    timezone_name: str,
) -> datetime:
    return datetime.combine(
        selected_date,
        selected_time,
    ).replace(
        tzinfo=ZoneInfo(timezone_name)
    )
