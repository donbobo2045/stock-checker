from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


def get_default_event_id(
    events: pd.DataFrame,
    *,
    now: datetime | None = None,
    timezone_name: str = "Asia/Tokyo",
    tour_id: str | None = None,
) -> str | None:
    """
    初期表示に使う公演を返す。

    - 今日以降の公演がある場合:
      最も近い公演日のうち、開始時刻が最も早い公演
    - 全公演終了後:
      最終公演日のうち、開始時刻が最も早い公演
      （同日1部/2部は在庫セッション共有を想定）

    日付基準なので、当日は終演後でもその日の公演を初期表示する。
    """
    if events.empty:
        return None

    work = events.fillna("").copy()

    required = {"event_id", "date"}
    missing = required - set(work.columns)
    if missing:
        raise ValueError(
            "events.csv に必要な列がありません: "
            + ", ".join(sorted(missing))
        )

    if tour_id is not None:
        if "tour_id" not in work.columns:
            raise ValueError("events.csv に tour_id 列がありません")
        work = work[work["tour_id"] == tour_id].copy()

    if work.empty:
        return None

    work["_event_date"] = pd.to_datetime(
        work["date"],
        format="%Y-%m-%d",
        errors="coerce",
    )

    work = work[work["_event_date"].notna()].copy()
    if work.empty:
        return None

    tz = ZoneInfo(timezone_name)

    if now is None:
        current = datetime.now(tz)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=tz)
    else:
        current = now.astimezone(tz)

    today = current.date()

    future_or_today = work[
        work["_event_date"].dt.date >= today
    ].copy()

    if not future_or_today.empty:
        target_date = future_or_today["_event_date"].min()
    else:
        target_date = work["_event_date"].max()

    target = work[
        work["_event_date"] == target_date
    ].copy()

    # 同日に複数公演がある場合は早い公演を選ぶ。
    # start_time がない/不正でも安定して選べるよう文字列で補助ソート。
    if "start_time" not in target.columns:
        target["start_time"] = ""

    target = target.sort_values(
        ["start_time", "event_id"],
        kind="stable",
    )

    return str(target.iloc[0]["event_id"])


def get_tour_id_for_event(
    events: pd.DataFrame,
    event_id: str | None,
) -> str | None:
    if not event_id:
        return None

    matches = events[
        events["event_id"] == event_id
    ]

    if matches.empty:
        return None

    return str(matches.iloc[0]["tour_id"])
