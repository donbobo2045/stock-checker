from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from selection_logic import (
    get_default_event_id,
    get_tour_id_for_event,
)


BASE_DIR = Path(__file__).resolve().parents[1]

EVENTS = pd.read_csv(
    BASE_DIR / "data" / "events.csv",
    dtype=str,
    keep_default_na=False,
)


def jpdt(y, m, d, hh=12, mm=0):
    return datetime(
        y,
        m,
        d,
        hh,
        mm,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


def test_sep22_defaults_to_tokyo_sep23():
    result = get_default_event_id(
        EVENTS,
        now=jpdt(2026, 9, 22),
    )
    assert result == "FRESHEST_TOKYO_0923"


def test_on_osaka_day1_defaults_to_osaka_day1():
    result = get_default_event_id(
        EVENTS,
        now=jpdt(2026, 9, 18, 23, 30),
    )
    assert result == "FRESHEST_OSAKA_0918"


def test_on_two_part_day_selects_first_part():
    result = get_default_event_id(
        EVENTS,
        now=jpdt(2026, 9, 19, 15, 0),
    )
    assert result == "FRESHEST_OSAKA_0919_P1"


def test_before_tour_defaults_to_first_event():
    result = get_default_event_id(
        EVENTS,
        now=jpdt(2026, 8, 1),
    )
    assert result == "FRESHEST_AICHI_0821"


def test_after_all_events_falls_back_to_last_event_day():
    result = get_default_event_id(
        EVENTS,
        now=jpdt(2026, 10, 1),
    )
    assert result == "FRESHEST_TOKYO_0923"


def test_default_event_maps_to_tour():
    event_id = get_default_event_id(
        EVENTS,
        now=jpdt(2026, 9, 22),
    )
    assert (
        get_tour_id_for_event(EVENTS, event_id)
        == "FRESHEST_2026"
    )
