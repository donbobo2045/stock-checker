from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

AUTO = "AUTO"
AVAILABLE = "AVAILABLE"
SOLD_OUT = "SOLD_OUT"

PRE_SALE = "PRE_SALE"
SALES_ENDED = "SALES_ENDED"

STORED_STATUSES = {AUTO, AVAILABLE, SOLD_OUT}
EFFECTIVE_STATUSES = {
    PRE_SALE,
    AVAILABLE,
    SOLD_OUT,
    SALES_ENDED,
}


def get_sales_start_at(session: dict) -> datetime:
    timezone_name = str(session["timezone"]).strip()
    date_text = str(session["date"]).strip()
    time_text = str(session["sales_start_time"]).strip()

    tz = ZoneInfo(timezone_name)
    naive = datetime.strptime(
        f"{date_text} {time_text}",
        "%Y-%m-%d %H:%M",
    )
    return naive.replace(tzinfo=tz)


def get_sales_end_at(session: dict) -> datetime:
    """
    販売終了判定は「公演日の翌日 00:00」。

    実際の会場販売終了時刻ではなく、当日中は販売中扱いを維持する。
    """
    timezone_name = str(session["timezone"]).strip()
    date_text = str(session["date"]).strip()

    tz = ZoneInfo(timezone_name)
    event_date = datetime.strptime(
        date_text,
        "%Y-%m-%d",
    ).date()

    next_day = event_date + timedelta(days=1)

    return datetime(
        next_day.year,
        next_day.month,
        next_day.day,
        0,
        0,
        0,
        tzinfo=tz,
    )


def normalize_now(
    session: dict,
    now: datetime | None = None,
) -> datetime:
    tz = ZoneInfo(str(session["timezone"]).strip())

    if now is None:
        return datetime.now(tz)

    if now.tzinfo is None:
        return now.replace(tzinfo=tz)

    return now.astimezone(tz)


def get_effective_status(
    stored_status: str,
    session: dict,
    now: datetime | None = None,
    enable_sales_end: bool = False,
) -> str:
    """
    ステータス優先順位:

    1. SOLD_OUT は永続的に SOLD_OUT
    2. 販売終了機能が有効で翌日0:00以降なら SALES_ENDED
       （AUTO / AVAILABLE の両方が対象）
    3. 手動 AVAILABLE は販売中固定
    4. AUTO:
       販売開始前 -> PRE_SALE
       販売開始以降 -> AVAILABLE

    旧 UNKNOWN は後方互換のため AUTO と同様に扱う。
    """
    stored = (stored_status or "").strip().upper()
    current = normalize_now(session, now)

    if stored == SOLD_OUT:
        return SOLD_OUT

    if enable_sales_end:
        sales_end_at = get_sales_end_at(session)
        if current >= sales_end_at:
            return SALES_ENDED

    if stored == AVAILABLE:
        return AVAILABLE

    sales_start_at = get_sales_start_at(session)

    return (
        PRE_SALE
        if current < sales_start_at
        else AVAILABLE
    )
