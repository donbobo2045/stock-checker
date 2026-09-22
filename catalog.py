from __future__ import annotations

import pandas as pd


def get_goods_for_session(
    goods: pd.DataFrame,
    session_items: pd.DataFrame,
    sales_session_id: str,
) -> pd.DataFrame:
    """
    Return only the goods scheduled for sale in the selected sales session.
    Preserves the order of goods.csv.
    """
    goods = goods.fillna("").copy()
    session_items = session_items.fillna("").copy()

    required_goods = {"item_id", "variant"}
    required_map = {"sales_session_id", "item_id", "variant"}

    missing_goods = required_goods - set(goods.columns)
    missing_map = required_map - set(session_items.columns)

    if missing_goods:
        raise ValueError(
            "goods.csv に必要な列がありません: "
            + ", ".join(sorted(missing_goods))
        )
    if missing_map:
        raise ValueError(
            "sales_session_items.csv に必要な列がありません: "
            + ", ".join(sorted(missing_map))
        )

    selected = session_items[
        session_items["sales_session_id"] == sales_session_id
    ][["item_id", "variant"]].drop_duplicates()

    ordered = goods.copy()
    ordered["_catalog_order"] = range(len(ordered))

    result = ordered.merge(
        selected,
        on=["item_id", "variant"],
        how="inner",
        sort=False,
    )
    result = result.sort_values("_catalog_order", kind="stable")
    return result.drop(columns=["_catalog_order"]).reset_index(drop=True)
