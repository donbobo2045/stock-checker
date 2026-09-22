from datetime import datetime
from zoneinfo import ZoneInfo

from status_logic import (
    AVAILABLE,
    AUTO,
    PRE_SALE,
    SOLD_OUT,
    get_effective_status,
)


SESSION = {
    "date": "2026-09-23",
    "sales_start_time": "13:00",
    "timezone": "Asia/Tokyo",
}


def test_auto_is_pre_sale_before_start():
    now = datetime(
        2026,
        9,
        23,
        12,
        59,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
    assert (
        get_effective_status(
            AUTO,
            SESSION,
            now=now,
        )
        == PRE_SALE
    )


def test_auto_is_available_at_start():
    now = datetime(
        2026,
        9,
        23,
        13,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
    assert (
        get_effective_status(
            AUTO,
            SESSION,
            now=now,
        )
        == AVAILABLE
    )


def test_sold_out_overrides_clock():
    now = datetime(
        2026,
        9,
        23,
        12,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
    assert (
        get_effective_status(
            SOLD_OUT,
            SESSION,
            now=now,
        )
        == SOLD_OUT
    )


def test_manual_available_overrides_pre_sale():
    now = datetime(
        2026,
        9,
        23,
        12,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
    assert (
        get_effective_status(
            AVAILABLE,
            SESSION,
            now=now,
        )
        == AVAILABLE
    )


def test_legacy_unknown_behaves_like_auto():
    now = datetime(
        2026,
        9,
        23,
        12,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
    assert (
        get_effective_status(
            "UNKNOWN",
            SESSION,
            now=now,
        )
        == PRE_SALE
    )
