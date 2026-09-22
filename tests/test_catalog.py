from pathlib import Path

import pandas as pd

from catalog import get_goods_for_session


BASE_DIR = Path(__file__).resolve().parents[1]
GOODS = pd.read_csv(
    BASE_DIR / "data" / "goods.csv",
    dtype=str,
    keep_default_na=False,
)
SESSION_ITEMS = pd.read_csv(
    BASE_DIR / "data" / "sales_session_items.csv",
    dtype=str,
    keep_default_na=False,
)


def ids_for(session_id):
    df = get_goods_for_session(
        GOODS,
        SESSION_ITEMS,
        session_id,
    )
    return df, set(df["item_id"])


def test_aichi_catalog_has_venue_additions_but_not_later_additions():
    df, ids = ids_for("FRESHEST_AICHI_0821")
    assert len(df) == 47
    assert "freshest_pouch" in ids
    assert "icex_bokunchi_mini_pouch" in ids
    assert "icex_fight_towel" in ids
    assert "random_acrylic_keyholder" in ids
    assert "icex_route8_drawstring_bag" in ids
    assert "sutapii_sticker" not in ids
    assert "photo_set_vol32" not in ids
    assert "photo_set_vol33" not in ids


def test_osaka_catalog_adds_sutapii_sticker():
    df, ids = ids_for("FRESHEST_OSAKA_0918")
    assert len(df) == 48
    assert "sutapii_sticker" in ids
    assert "photo_set_vol32" not in ids


def test_tokyo_catalog_adds_photo_32_and_33():
    df, ids = ids_for("FRESHEST_TOKYO_0923")
    assert len(df) == 50
    assert "sutapii_sticker" in ids
    assert "photo_set_vol32" in ids
    assert "photo_set_vol33" in ids
