from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from production_state import (
    clone_state,
    get_sync_cursor,
    set_review_posts,
    set_sync_cursor,
    upsert_sold_out,
)
from x_preview import PARSED, REVIEW, classify_parse_result
from x_sync_logic import (
    build_event_day_search_plan,
    get_tour_event_dates,
    newest_post_id,
)


@dataclass(frozen=True)
class AutoSyncSummary:
    scope_key: str | None
    event_date: str | None
    fetched: int
    parsed: int
    review: int
    ignored: int
    cursor_before: str | None
    cursor_after: str | None
    changed: bool
    skipped_reason: str | None = None


def sync_live_event_once(
    *,
    client: Any,
    parser: Any,
    events: pd.DataFrame,
    state: dict,
    target_tour_id: str,
    username: str,
    query: str,
    now: datetime,
    max_results: int = 100,
) -> tuple[dict, AutoSyncSummary]:
    event_dates = get_tour_event_dates(
        events,
        target_tour_id,
    )
    today_iso = now.date().isoformat()

    if today_iso not in event_dates:
        summary = AutoSyncSummary(
            scope_key=None,
            event_date=None,
            fetched=0,
            parsed=0,
            review=0,
            ignored=0,
            cursor_before=None,
            cursor_after=None,
            changed=False,
            skipped_reason=(
                f"{today_iso} is not an event date for "
                f"{target_tour_id}"
            ),
        )
        return state, summary

    scope_key = f"live:{target_tour_id}:{today_iso}"
    cursor_before = get_sync_cursor(
        state,
        scope_key,
    )

    plan = build_event_day_search_plan(
        today_iso,
        now,
        since_id=cursor_before,
        timezone_name="Asia/Tokyo",
    )

    posts = client.search_recent_posts(
        query,
        username=username,
        max_results=max_results,
        start_time=plan.start_time,
        end_time=plan.end_time,
        since_id=plan.since_id,
    )
    posts = sorted(
        posts,
        key=lambda post: int(post.id),
    )

    next_state = clone_state(state)
    parsed_count = 0
    review_rows: list[dict[str, str]] = []
    ignored_count = 0
    updated_at = now.isoformat()

    for post in posts:
        parsed_result = parser.parse(post.text)
        category = classify_parse_result(
            parsed_result
        )

        if (
            category == PARSED
            and (
                parsed_result.tour_id
                != target_tour_id
                or parsed_result.date
                != today_iso
            )
        ):
            category = REVIEW
            parsed_result.reason = (
                "X取得対象とparser解析結果が不一致です。"
                f" 取得={target_tour_id}/{today_iso},"
                f" 解析={parsed_result.tour_id}/"
                f"{parsed_result.date}"
            )

        if category == PARSED:
            parsed_count += 1
            for item in parsed_result.items or []:
                upsert_sold_out(
                    next_state,
                    sales_session_id=(
                        parsed_result.sales_session_id
                    ),
                    item_id=item.item_id,
                    variant=item.variant,
                    source_post_id=post.id,
                    source_post_url=post.url,
                    updated_at=updated_at,
                )
        elif category == REVIEW:
            review_rows.append(
                {
                    "post_id": post.id,
                    "post_url": post.url,
                    "reason": parsed_result.reason,
                }
            )
        else:
            ignored_count += 1

    set_review_posts(
        next_state,
        scope_key,
        review_rows,
    )

    cursor_after = cursor_before
    latest_id = newest_post_id(
        [post.id for post in posts]
    )

    # A review item blocks cursor advancement so it cannot be silently skipped.
    # Successfully parsed later posts are still applied idempotently.
    if latest_id and not review_rows:
        set_sync_cursor(
            next_state,
            scope_key,
            latest_id,
        )
        cursor_after = latest_id

    changed = next_state != state

    summary = AutoSyncSummary(
        scope_key=scope_key,
        event_date=today_iso,
        fetched=len(posts),
        parsed=parsed_count,
        review=len(review_rows),
        ignored=ignored_count,
        cursor_before=cursor_before,
        cursor_after=cursor_after,
        changed=changed,
        skipped_reason=None,
    )
    return next_state, summary
