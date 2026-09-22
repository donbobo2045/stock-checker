from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd


@dataclass(frozen=True)
class EventDaySearchPlan:
    event_date: str
    start_time: str | None
    end_time: str | None
    since_id: str | None
    mode: str


def get_tour_event_dates(
    events: pd.DataFrame,
    tour_id: str,
) -> list[str]:
    """Return unique ISO event dates for one tour, in chronological order."""
    if "tour_id" not in events.columns or "date" not in events.columns:
        raise ValueError("events.csv に tour_id / date 列が必要です。")

    dates = (
        events.loc[events["tour_id"] == tour_id, "date"]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    return dates


def build_event_day_search_plan(
    event_date: str | date,
    cutoff: datetime,
    *,
    since_id: str | None = None,
    timezone_name: str = "Asia/Tokyo",
) -> EventDaySearchPlan:
    """
    Build a Recent Search window for one event day.

    Initial fetch:
      start_time = event-day 00:00 local
      end_time   = cutoff
    Incremental fetch:
      since_id   = previous newest Post ID
      end_time   = cutoff

    X Recent Search does not allow start_time and since_id together.

    For incremental reads we intentionally omit end_time as well. In live
    operation, since_id alone naturally reads through the current Recent
    Search upper bound. Rehearsal mode can apply its virtual cutoff locally.
    """
    event_day = _coerce_date(event_date)
    tz = ZoneInfo(timezone_name)

    if cutoff.tzinfo is None:
        cutoff_local = cutoff.replace(tzinfo=tz)
    else:
        cutoff_local = cutoff.astimezone(tz)

    event_start = datetime.combine(
        event_day,
        time.min,
        tzinfo=tz,
    )
    event_end = event_start + timedelta(days=1)

    if cutoff_local <= event_start:
        raise ValueError(
            "取得終了時刻は対象イベント日の0:00より後にしてください。"
        )

    effective_end = min(cutoff_local, event_end)

    normalized_since_id = str(since_id or "").strip() or None
    start_time = (
        None
        if normalized_since_id
        else _to_utc_rfc3339(event_start)
    )

    return EventDaySearchPlan(
        event_date=event_day.isoformat(),
        start_time=start_time,
        end_time=(
            None
            if normalized_since_id
            else _to_utc_rfc3339(effective_end)
        ),
        since_id=normalized_since_id,
        mode=(
            "incremental"
            if normalized_since_id
            else "initial"
        ),
    )


def is_full_event_day_recent_search_eligible(
    event_date: str | date,
    now: datetime,
    *,
    timezone_name: str = "Asia/Tokyo",
) -> bool:
    """
    True when the event-day 00:00 start_time is still inside X Recent Search's
    rolling 7-day window.
    """
    event_day = _coerce_date(event_date)
    tz = ZoneInfo(timezone_name)

    if now.tzinfo is None:
        now_local = now.replace(tzinfo=tz)
    else:
        now_local = now.astimezone(tz)

    event_start = datetime.combine(
        event_day,
        time.min,
        tzinfo=tz,
    )

    return (
        event_start <= now_local
        and event_start.astimezone(timezone.utc)
        >= (
            now_local.astimezone(timezone.utc)
            - timedelta(days=7)
        )
    )


def newest_post_id(post_ids: list[str]) -> str | None:
    """Return the numerically newest X Post ID from a list."""
    normalized = [
        str(post_id).strip()
        for post_id in post_ids
        if str(post_id).strip().isdigit()
    ]
    if not normalized:
        return None
    return max(normalized, key=int)


def _coerce_date(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _to_utc_rfc3339(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
