import sqlite3

import database


def test_unknown_is_migrated_to_auto(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "inventory.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE inventory_status (
                sales_session_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                variant TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'UNKNOWN',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_post_id TEXT,
                source_post_url TEXT,
                PRIMARY KEY (
                    sales_session_id,
                    item_id,
                    variant
                )
            )
            """
        )
        conn.execute(
            """
            INSERT INTO inventory_status (
                sales_session_id,
                item_id,
                variant,
                status
            )
            VALUES (
                'TEST',
                'item',
                '',
                'UNKNOWN'
            )
            """
        )
        conn.commit()

    monkeypatch.setattr(
        database,
        "DB_PATH",
        db_path,
    )
    database.init_db()

    inv = database.get_inventory_for_session(
        "TEST"
    )
    assert inv[("item", "")]["status"] == "AUTO"



def test_x_sync_cursor_round_trip(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "inventory.db"

    monkeypatch.setattr(
        database,
        "DB_PATH",
        db_path,
    )
    database.init_db()

    scope = "rehearsal:FRESHEST_2026:2026-09-19"

    assert database.get_x_sync_cursor(scope) is None

    database.set_x_sync_cursor(
        scope,
        "123456789",
    )
    assert database.get_x_sync_cursor(scope) == "123456789"

    database.set_x_sync_cursor(
        scope,
        "987654321",
    )
    assert database.get_x_sync_cursor(scope) == "987654321"

    database.reset_x_sync_cursor(scope)
    assert database.get_x_sync_cursor(scope) is None


def test_x_sync_cursor_rejects_non_numeric_id(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "inventory.db"

    monkeypatch.setattr(
        database,
        "DB_PATH",
        db_path,
    )
    database.init_db()

    try:
        database.set_x_sync_cursor(
            "scope",
            "not-a-post-id",
        )
    except ValueError as exc:
        assert "numeric X Post ID" in str(exc)
    else:
        raise AssertionError("ValueError was not raised")



def test_apply_x_parsed_posts_and_advance_cursor_is_atomic(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "inventory.db"

    monkeypatch.setattr(
        database,
        "DB_PATH",
        db_path,
    )
    database.init_db()

    scope = "rehearsal:FRESHEST_2026:2026-09-19"

    database.apply_x_parsed_posts_and_advance_cursor(
        scope,
        [
            (
                "SESSION_1",
                [
                    ("item_a", ""),
                    ("item_b", "筒井俊旭"),
                ],
                "2100000000000000001",
                "https://x.com/SDE_STARDUSTBIN/status/2100000000000000001",
            ),
            (
                "SESSION_1",
                [
                    ("item_c", ""),
                ],
                "2100000000000000002",
                "https://x.com/SDE_STARDUSTBIN/status/2100000000000000002",
            ),
        ],
        "2100000000000000002",
    )

    inv = database.get_inventory_for_session(
        "SESSION_1"
    )

    assert inv[("item_a", "")]["status"] == "SOLD_OUT"
    assert (
        inv[("item_b", "筒井俊旭")]["status"]
        == "SOLD_OUT"
    )
    assert inv[("item_c", "")]["status"] == "SOLD_OUT"
    assert (
        inv[("item_a", "")]["source_post_id"]
        == "2100000000000000001"
    )
    assert (
        inv[("item_c", "")]["source_post_id"]
        == "2100000000000000002"
    )
    assert (
        database.get_x_sync_cursor(scope)
        == "2100000000000000002"
    )


def test_apply_x_parsed_posts_rejects_invalid_cursor_before_write(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "inventory.db"

    monkeypatch.setattr(
        database,
        "DB_PATH",
        db_path,
    )
    database.init_db()

    try:
        database.apply_x_parsed_posts_and_advance_cursor(
            "scope",
            [
                (
                    "SESSION_1",
                    [("item_a", "")],
                    "2100000000000000001",
                    "https://x.com/example/status/2100000000000000001",
                )
            ],
            "invalid",
        )
    except ValueError as exc:
        assert "numeric X Post ID" in str(exc)
    else:
        raise AssertionError("ValueError was not raised")

    inv = database.get_inventory_for_session(
        "SESSION_1"
    )
    assert inv == {}
    assert database.get_x_sync_cursor("scope") is None
