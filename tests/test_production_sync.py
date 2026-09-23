from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from parser import ParseResult, ParsedSoldOutItem
from production_state import empty_production_state
from production_sync import sync_live_event_once
from x_client import XPost


class FakeClient:
    def __init__(self, posts):
        self.posts = posts
        self.calls = []

    def search_recent_posts(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return list(self.posts)


class FakeParser:
    def __init__(self, results):
        self.results = results

    def parse(self, text):
        return self.results[text]


def _events():
    return pd.DataFrame(
        [
            {
                "tour_id": "FRESHEST_2026",
                "date": "2026-09-23",
            }
        ]
    )


def _now():
    return datetime(
        2026,
        9,
        23,
        14,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


def test_live_sync_applies_sold_out_and_advances_cursor():
    post = XPost(
        id="2100000000000000001",
        text="good",
        username="SDE_STARDUSTBIN",
        created_at="2026-09-23T04:30:00Z",
    )
    parser = FakeParser(
        {
            "good": ParseResult(
                True,
                "ok",
                tour_id="FRESHEST_2026",
                sales_session_id="FRESHEST_TOKYO_0923",
                date="2026-09-23",
                venue="東京国際フォーラム ホールA",
                items=[
                    ParsedSoldOutItem(
                        "item_a",
                        "商品A",
                        "",
                    )
                ],
            )
        }
    )
    client = FakeClient([post])

    state, summary = sync_live_event_once(
        client=client,
        parser=parser,
        events=_events(),
        state=empty_production_state(),
        target_tour_id="FRESHEST_2026",
        username="SDE_STARDUSTBIN",
        query="query",
        now=_now(),
    )

    assert summary.parsed == 1
    assert summary.review == 0
    assert summary.cursor_after == post.id
    assert state["inventory"][0]["status"] == "SOLD_OUT"
    assert (
        state["inventory"][0]["sold_out_at"]
        == "2026-09-23T13:30:00+09:00"
    )
    assert state["sync"][
        "live:FRESHEST_2026:2026-09-23"
    ]["last_post_id"] == post.id

    _, kwargs = client.calls[0]
    assert kwargs["start_time"] == "2026-09-22T15:00:00Z"
    assert kwargs["since_id"] is None


def test_review_blocks_cursor_but_safe_post_is_applied():
    safe = XPost(
        id="2100000000000000001",
        text="safe",
        username="SDE_STARDUSTBIN",
    )
    review = XPost(
        id="2100000000000000002",
        text="review",
        username="SDE_STARDUSTBIN",
    )
    parser = FakeParser(
        {
            "safe": ParseResult(
                True,
                "ok",
                tour_id="FRESHEST_2026",
                sales_session_id="FRESHEST_TOKYO_0923",
                date="2026-09-23",
                venue="東京",
                items=[
                    ParsedSoldOutItem(
                        "item_a",
                        "商品A",
                        "",
                    )
                ],
            ),
            "review": ParseResult(
                False,
                "商品を一意に特定できません",
                tour_id="FRESHEST_2026",
                date="2026-09-23",
            ),
        }
    )

    state, summary = sync_live_event_once(
        client=FakeClient([safe, review]),
        parser=parser,
        events=_events(),
        state=empty_production_state(),
        target_tour_id="FRESHEST_2026",
        username="SDE_STARDUSTBIN",
        query="query",
        now=_now(),
    )

    assert summary.parsed == 1
    assert summary.review == 1
    assert summary.cursor_after is None
    assert state["inventory"][0]["item_id"] == "item_a"
    assert "live:FRESHEST_2026:2026-09-23" not in state["sync"]
    assert state["reviews"][
        "live:FRESHEST_2026:2026-09-23"
    ][0]["post_id"] == review.id


def test_existing_cursor_is_used_for_incremental_search():
    state = empty_production_state()
    state["sync"]["live:FRESHEST_2026:2026-09-23"] = {
        "last_post_id": "2100000000000000000"
    }
    client = FakeClient([])

    next_state, summary = sync_live_event_once(
        client=client,
        parser=FakeParser({}),
        events=_events(),
        state=state,
        target_tour_id="FRESHEST_2026",
        username="SDE_STARDUSTBIN",
        query="query",
        now=_now(),
    )

    assert not summary.changed
    assert next_state == state
    _, kwargs = client.calls[0]
    assert kwargs["since_id"] == "2100000000000000000"
    assert kwargs["start_time"] is None


def test_non_event_day_skips_without_calling_x():
    client = FakeClient([])

    state, summary = sync_live_event_once(
        client=client,
        parser=FakeParser({}),
        events=_events(),
        state=empty_production_state(),
        target_tour_id="FRESHEST_2026",
        username="SDE_STARDUSTBIN",
        query="query",
        now=datetime(
            2026,
            9,
            22,
            14,
            0,
            tzinfo=ZoneInfo("Asia/Tokyo"),
        ),
    )

    assert not summary.changed
    assert summary.skipped_reason is not None
    assert client.calls == []
