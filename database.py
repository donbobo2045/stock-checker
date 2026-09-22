from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

DB_PATH = Path(__file__).resolve().parent / "inventory.db"

VALID_STATUSES = {"AUTO", "AVAILABLE", "SOLD_OUT"}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory_status (
                sales_session_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                variant TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'AUTO',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_post_id TEXT,
                source_post_url TEXT,
                PRIMARY KEY (sales_session_id, item_id, variant)
            )
            """
        )

        # Migration from older project versions.
        # UNKNOWN meant "no explicit inventory information", which is now AUTO.
        conn.execute(
            """
            UPDATE inventory_status
            SET status = 'AUTO'
            WHERE status = 'UNKNOWN'
            """
        )
        conn.commit()


def ensure_inventory_rows(
    sales_session_id: str,
    items: Iterable[tuple[str, str]],
) -> None:
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO inventory_status (
                sales_session_id,
                item_id,
                variant,
                status
            )
            VALUES (?, ?, ?, 'AUTO')
            """,
            [
                (sales_session_id, item_id, variant or "")
                for item_id, variant in items
            ],
        )
        conn.commit()


def get_inventory_for_session(
    sales_session_id: str,
) -> dict[tuple[str, str], dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                sales_session_id,
                item_id,
                variant,
                status,
                updated_at,
                source_post_id,
                source_post_url
            FROM inventory_status
            WHERE sales_session_id = ?
            """,
            (sales_session_id,),
        ).fetchall()

    return {
        (row["item_id"], row["variant"]): dict(row)
        for row in rows
    }


def update_status(
    sales_session_id: str,
    item_id: str,
    variant: str,
    status: str,
) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported status: {status}")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO inventory_status (
                sales_session_id,
                item_id,
                variant,
                status,
                updated_at,
                source_post_id,
                source_post_url
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, NULL, NULL)
            ON CONFLICT(sales_session_id, item_id, variant)
            DO UPDATE SET
                status = excluded.status,
                updated_at = CURRENT_TIMESTAMP,
                source_post_id = NULL,
                source_post_url = NULL
            """,
            (sales_session_id, item_id, variant or "", status),
        )
        conn.commit()


def reset_session(sales_session_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE inventory_status
            SET
                status = 'AUTO',
                updated_at = CURRENT_TIMESTAMP,
                source_post_id = NULL,
                source_post_url = NULL
            WHERE sales_session_id = ?
            """,
            (sales_session_id,),
        )
        conn.commit()


def apply_parsed_sold_out(
    sales_session_id: str,
    items: list[tuple[str, str]],
    source_post_id: str | None = None,
    source_post_url: str | None = None,
) -> None:
    with get_connection() as conn:
        for item_id, variant in items:
            conn.execute(
                """
                INSERT INTO inventory_status (
                    sales_session_id,
                    item_id,
                    variant,
                    status,
                    updated_at,
                    source_post_id,
                    source_post_url
                )
                VALUES (?, ?, ?, 'SOLD_OUT', CURRENT_TIMESTAMP, ?, ?)
                ON CONFLICT(sales_session_id, item_id, variant)
                DO UPDATE SET
                    status = 'SOLD_OUT',
                    updated_at = CURRENT_TIMESTAMP,
                    source_post_id = excluded.source_post_id,
                    source_post_url = excluded.source_post_url
                """,
                (
                    sales_session_id,
                    item_id,
                    variant or "",
                    source_post_id,
                    source_post_url,
                ),
            )
        conn.commit()
