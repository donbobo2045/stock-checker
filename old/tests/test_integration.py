from pathlib import Path
import sqlite3

import pandas as pd

import database
from parser import SoldOutPostParser


BASE_DIR = Path(__file__).resolve().parents[1]


def test_parser_result_can_update_database(tmp_path, monkeypatch):
    test_db = tmp_path / "inventory.db"
    monkeypatch.setattr(database, "DB_PATH", test_db)

    database.init_db()

    parser = SoldOutPostParser.from_csv(
        BASE_DIR / "data" / "goods.csv",
        BASE_DIR / "data" / "events.csv",
        BASE_DIR / "data" / "item_aliases.csv",
    )

    post = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・ペンラ
・アクスタ（中村）
本日分完売です！
ありがとうございます。"""

    result = parser.parse(post)
    assert result.is_relevant is True

    database.ensure_inventory_rows(
        result.sales_session_id,
        [
            (item.item_id, item.variant)
            for item in result.items
        ],
    )

    database.apply_parsed_sold_out(
        result.sales_session_id,
        [(item.item_id, item.variant) for item in result.items],
        source_post_url="https://x.com/example/status/123",
    )

    inventory = database.get_inventory_for_session(result.sales_session_id)

    assert inventory[("icex_penlight_ver4", "")]["status"] == "SOLD_OUT"
    assert inventory[("freshest_acrylic_stand", "中村旺太郎")]["status"] == "SOLD_OUT"
    assert inventory[("freshest_acrylic_stand", "中村旺太郎")]["source_post_url"] == "https://x.com/example/status/123"
