from pathlib import Path

import pandas as pd

from catalog import get_goods_for_session
from search_logic import (
    filter_goods_for_search,
    normalize_search_text,
)


BASE_DIR = Path(__file__).resolve().parents[1]

GOODS = pd.read_csv(
    BASE_DIR / "data" / "goods.csv",
    dtype=str,
    keep_default_na=False,
)
ALIASES = pd.read_csv(
    BASE_DIR / "data" / "item_aliases.csv",
    dtype=str,
    keep_default_na=False,
)
SESSION_ITEMS = pd.read_csv(
    BASE_DIR / "data" / "sales_session_items.csv",
    dtype=str,
    keep_default_na=False,
)

TOKYO_GOODS = get_goods_for_session(
    GOODS,
    SESSION_ITEMS,
    "FRESHEST_TOKYO_0923",
)


def test_normalize_search_text_absorbs_width_space_and_punctuation():
    assert normalize_search_text(" PHOTO SET vol.32 ") == normalize_search_text(
        "photo-set　vol32"
    )


def test_search_by_product_name():
    result = filter_goods_for_search(
        TOKYO_GOODS,
        ALIASES,
        "うちわ",
    )
    assert set(result["item_id"]) == {
        "freshest_uchiwa",
        "freshest_random_uchiwa_keychain",
    }


def test_search_by_member_name_filters_variant():
    result = filter_goods_for_search(
        TOKYO_GOODS,
        ALIASES,
        "山本",
    )
    assert not result.empty
    assert all(
        "山本" in variant
        for variant in result["variant"]
    )


def test_search_by_alias_penra():
    result = filter_goods_for_search(
        TOKYO_GOODS,
        ALIASES,
        "ペンラ",
    )
    assert set(result["item_id"]) == {
        "icex_penlight_ver4"
    }


def test_ambiguous_search_term_shows_multiple_candidates():
    result = filter_goods_for_search(
        TOKYO_GOODS,
        ALIASES,
        "シール",
    )
    assert {
        "freshest_sticker_sheet",
        "sutapii_sticker",
    }.issubset(set(result["item_id"]))


def test_empty_search_returns_all_rows():
    result = filter_goods_for_search(
        TOKYO_GOODS,
        ALIASES,
        "",
    )
    assert len(result) == len(TOKYO_GOODS)
