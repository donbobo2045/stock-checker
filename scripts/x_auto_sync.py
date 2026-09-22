from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd

from parser import SoldOutPostParser
from production_state import (
    load_production_state,
    save_production_state,
)
from production_sync import sync_live_event_once
from x_client import XApiClient


DATA_DIR = BASE_DIR / "data"

EVENTS_CSV = DATA_DIR / "events.csv"
GOODS_CSV = DATA_DIR / "goods.csv"
ALIASES_CSV = DATA_DIR / "item_aliases.csv"
SALES_SESSION_ITEMS_CSV = (
    DATA_DIR / "sales_session_items.csv"
)
PRODUCTION_STATE_PATH = (
    DATA_DIR / "production_state.json"
)

TARGET_TOUR_ID = os.getenv(
    "X_TARGET_TOUR_ID",
    "FRESHEST_2026",
)
X_USERNAME = "SDE_STARDUSTBIN"
X_SEARCH_QUERY = (
    "from:SDE_STARDUSTBIN "
    "(ICEx OR #ICEx) 完売 -is:retweet"
)


def main() -> int:
    now = datetime.now(
        ZoneInfo("Asia/Tokyo")
    )

    events = pd.read_csv(
        EVENTS_CSV,
        dtype=str,
        keep_default_na=False,
    )

    event_dates = set(
        events.loc[
            events["tour_id"] == TARGET_TOUR_ID,
            "date",
        ].astype(str)
    )
    today_iso = now.date().isoformat()

    if today_iso not in event_dates:
        print(
            f"SKIP: {today_iso} is not an event date "
            f"for {TARGET_TOUR_ID}"
        )
        return 0

    bearer_token = os.getenv(
        "X_BEARER_TOKEN",
        "",
    ).strip()
    if not bearer_token:
        raise RuntimeError(
            "X_BEARER_TOKEN is not configured"
        )

    parser = SoldOutPostParser.from_csv(
        GOODS_CSV,
        EVENTS_CSV,
        ALIASES_CSV,
        SALES_SESSION_ITEMS_CSV,
    )
    client = XApiClient(bearer_token)

    state = load_production_state(
        PRODUCTION_STATE_PATH
    )

    next_state, summary = sync_live_event_once(
        client=client,
        parser=parser,
        events=events,
        state=state,
        target_tour_id=TARGET_TOUR_ID,
        username=X_USERNAME,
        query=X_SEARCH_QUERY,
        now=now,
        max_results=100,
    )

    print(
        "SYNC:",
        f"scope={summary.scope_key}",
        f"fetched={summary.fetched}",
        f"parsed={summary.parsed}",
        f"review={summary.review}",
        f"ignored={summary.ignored}",
        f"cursor_before={summary.cursor_before}",
        f"cursor_after={summary.cursor_after}",
        f"changed={summary.changed}",
    )

    if summary.changed:
        save_production_state(
            PRODUCTION_STATE_PATH,
            next_state,
        )
        print(
            f"UPDATED: {PRODUCTION_STATE_PATH}"
        )
    else:
        print("NO_CHANGE")

    if summary.review:
        print(
            "WARNING: review posts exist; "
            "cursor was not advanced."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
