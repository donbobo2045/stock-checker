from pathlib import Path

from production_state import (
    empty_production_state,
    get_sync_cursor,
    load_production_state,
    overlay_production_inventory,
    save_production_state,
    set_sync_cursor,
    upsert_sold_out,
)


def test_production_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    state = empty_production_state()

    assert set_sync_cursor(
        state,
        "live:T1:2026-09-23",
        "123",
    )
    assert upsert_sold_out(
        state,
        sales_session_id="SESSION",
        item_id="item_a",
        variant="",
        source_post_id="123",
        source_post_url="https://x.com/a/status/123",
        updated_at="2026-09-23T13:00:00+09:00",
    )

    save_production_state(path, state)
    loaded = load_production_state(path)

    assert get_sync_cursor(
        loaded,
        "live:T1:2026-09-23",
    ) == "123"
    assert loaded["inventory"][0]["status"] == "SOLD_OUT"


def test_same_post_does_not_change_state_timestamp():
    state = empty_production_state()

    assert upsert_sold_out(
        state,
        sales_session_id="SESSION",
        item_id="item_a",
        variant="",
        source_post_id="123",
        source_post_url="https://x.com/a/status/123",
        updated_at="first",
    )

    assert not upsert_sold_out(
        state,
        sales_session_id="SESSION",
        item_id="item_a",
        variant="",
        source_post_id="123",
        source_post_url="https://x.com/a/status/123",
        updated_at="second",
    )
    assert state["inventory"][0]["updated_at"] == "first"


def test_production_sold_out_overrides_local_auto():
    local = {
        ("item_a", ""): {
            "status": "AUTO",
            "updated_at": "local",
            "source_post_id": None,
            "source_post_url": None,
        }
    }
    state = empty_production_state()
    upsert_sold_out(
        state,
        sales_session_id="SESSION",
        item_id="item_a",
        variant="",
        source_post_id="123",
        source_post_url="https://x.com/a/status/123",
        updated_at="prod",
    )

    merged = overlay_production_inventory(
        local,
        state,
        "SESSION",
    )

    assert merged[("item_a", "")]["status"] == "SOLD_OUT"
    assert merged[("item_a", "")]["source_post_id"] == "123"
    assert merged[("item_a", "")]["updated_at"] == "prod"
