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
