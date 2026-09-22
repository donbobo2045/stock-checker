from __future__ import annotations

import re
import unicodedata

import pandas as pd


def normalize_search_text(value: object) -> str:
    """
    検索用に表記を緩く正規化する。
    大文字小文字、全角半角、空白・主要記号の差を吸収する。
    """
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return re.sub(r"[\s　・･!！'\"“”‘’()（）\-_./]+", "", text)


def filter_goods_for_search(
    goods: pd.DataFrame,
    aliases: pd.DataFrame,
    query: str,
) -> pd.DataFrame:
    """
    商品名・variant・item_idに加え、item_aliases.csv の別名でも絞り込む。

    検索は表示用なので、曖昧なaliasが複数商品に登録されている場合は
    それらをすべて候補として表示する。
    """
    goods = goods.fillna("").copy()
    aliases = aliases.fillna("").copy()

    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return goods.reset_index(drop=True)

    alias_map: dict[str, list[str]] = {}
    if {"alias", "item_id"}.issubset(aliases.columns):
        for _, row in aliases.iterrows():
            item_id = str(row["item_id"])
            alias_map.setdefault(item_id, []).append(str(row["alias"]))

    keep = []
    for _, row in goods.iterrows():
        item_id = str(row.get("item_id", ""))
        haystacks = [
            str(row.get("item_name", "")),
            str(row.get("variant", "")),
            item_id,
            *alias_map.get(item_id, []),
        ]

        matched = any(
            normalized_query in normalize_search_text(value)
            for value in haystacks
        )
        keep.append(matched)

    return goods.loc[keep].reset_index(drop=True)
