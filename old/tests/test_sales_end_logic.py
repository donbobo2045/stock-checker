from datetime import datetime
from zoneinfo import ZoneInfo

from status_logic import (
    AVAILABLE,
    AUTO,
    PRE_SALE,
    SALES_ENDED,
    SOLD_OUT,
    get_effective_status,
    get_sales_end_at,
)


SESSION = {
    "date": "2026-09-23",
    "sales_start_time": "13:00",
    "timezone": "Asia/Tokyo",
}


def jpdt(y, m, d, hh, mm):
    return datetime(
        y,
        m,
        d,
        hh,
        mm,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


def test_sales_end_is_next_day_midnight():
    assert get_sales_end_at(SESSION) == jpdt(
        2026, 9, 24, 0, 0
    )


def test_sales_end_disabled_keeps_auto_available_after_event_day():
    result = get_effective_status(
        AUTO,
        SESSION,
        now=jpdt(2026, 9, 24, 12, 0),
        enable_sales_end=False,
    )
    assert result == AVAILABLE


def test_sales_end_enabled_makes_auto_sales_ended_after_midnight():
    result = get_effective_status(
        AUTO,
        SESSION,
        now=jpdt(2026, 9, 24, 0, 1),
        enable_sales_end=True,
    )
    assert result == SALES_ENDED


def test_sales_end_enabled_keeps_available_until_end_of_event_day():
    result = get_effective_status(
        AUTO,
        SESSION,
        now=jpdt(2026, 9, 23, 23, 59),
        enable_sales_end=True,
    )
    assert result == AVAILABLE


def test_sold_out_is_preserved_after_sales_end():
    result = get_effective_status(
        SOLD_OUT,
        SESSION,
        now=jpdt(2026, 9, 24, 12, 0),
        enable_sales_end=True,
    )
    assert result == SOLD_OUT


def test_manual_available_becomes_sales_ended_when_feature_enabled():
    result = get_effective_status(
        AVAILABLE,
        SESSION,
        now=jpdt(2026, 9, 24, 12, 0),
        enable_sales_end=True,
    )
    assert result == SALES_ENDED


def test_manual_available_remains_available_when_feature_disabled():
    result = get_effective_status(
        AVAILABLE,
        SESSION,
        now=jpdt(2026, 9, 24, 12, 0),
        enable_sales_end=False,
    )
    assert result == AVAILABLE


def test_pre_sale_still_works_before_start():
    result = get_effective_status(
        AUTO,
        SESSION,
        now=jpdt(2026, 9, 23, 12, 59),
        enable_sales_end=True,
    )
    assert result == PRE_SALE
