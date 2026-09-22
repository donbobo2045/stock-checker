from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from x_sync_logic import (
    build_event_day_search_plan,
    get_tour_event_dates,
    is_full_event_day_recent_search_eligible,
    newest_post_id,
)


def test_get_tour_event_dates_deduplicates_same_day_parts():
    events = pd.DataFrame(
        [
            {"tour_id": "T1", "date": "2026-09-19"},
            {"tour_id": "T1", "date": "2026-09-19"},
            {"tour_id": "T1", "date": "2026-09-23"},
            {"tour_id": "OTHER", "date": "2026-09-20"},
        ]
    )

    assert get_tour_event_dates(events, "T1") == [
        "2026-09-19",
        "2026-09-23",
    ]


def test_initial_plan_uses_event_midnight_and_cutoff():
    cutoff = datetime(
        2026,
        9,
        19,
        15,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )

    plan = build_event_day_search_plan(
        "2026-09-19",
        cutoff,
    )

    assert plan.mode == "initial"
    assert plan.start_time == "2026-09-18T15:00:00Z"
    assert plan.end_time == "2026-09-19T06:00:00Z"
    assert plan.since_id is None


def test_incremental_plan_uses_since_id_instead_of_start_time():
    cutoff = datetime(
        2026,
        9,
        19,
        18,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )

    plan = build_event_day_search_plan(
        "2026-09-19",
        cutoff,
        since_id="123456789",
    )

    assert plan.mode == "incremental"
    assert plan.start_time is None
    assert plan.end_time is None
    assert plan.since_id == "123456789"


def test_cutoff_after_event_day_is_capped_at_next_midnight():
    cutoff = datetime(
        2026,
        9,
        20,
        12,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )

    plan = build_event_day_search_plan(
        "2026-09-19",
        cutoff,
    )

    assert plan.end_time == "2026-09-19T15:00:00Z"


def test_cutoff_before_event_day_is_rejected():
    cutoff = datetime(
        2026,
        9,
        18,
        23,
        59,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )

    with pytest.raises(ValueError):
        build_event_day_search_plan(
            "2026-09-19",
            cutoff,
        )


def test_recent_search_eligibility_uses_full_event_day_start():
    now = datetime(
        2026,
        9,
        22,
        20,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )

    assert is_full_event_day_recent_search_eligible(
        "2026-09-19",
        now,
    )
    assert not is_full_event_day_recent_search_eligible(
        "2026-09-14",
        now,
    )
    assert not is_full_event_day_recent_search_eligible(
        "2026-09-23",
        now,
    )


def test_newest_post_id_uses_numeric_order():
    assert newest_post_id(
        ["99", "100", "9"]
    ) == "100"
    assert newest_post_id([]) is None
