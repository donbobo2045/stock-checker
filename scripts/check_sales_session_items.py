from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = [
    "sales_session_id",
    "item_id",
    "variant",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mapping",
        nargs="?",
        default="data/sales_session_items.csv",
    )
    parser.add_argument(
        "--goods",
        default="data/goods.csv",
    )
    parser.add_argument(
        "--sessions",
        default="data/sales_sessions.csv",
    )
    args = parser.parse_args()

    mapping = pd.read_csv(
        args.mapping,
        dtype=str,
        keep_default_na=False,
    )
    goods = pd.read_csv(
        args.goods,
        dtype=str,
        keep_default_na=False,
    )
    sessions = pd.read_csv(
        args.sessions,
        dtype=str,
        keep_default_na=False,
    )

    errors = []
    passes = []

    if list(mapping.columns) == REQUIRED_COLUMNS:
        passes.append("列構成OK")
    else:
        errors.append(
            f"列構成NG: {list(mapping.columns)}"
        )

    if mapping.duplicated(
        subset=["sales_session_id", "item_id", "variant"]
    ).any():
        errors.append("マッピングに重複があります")
    else:
        passes.append("マッピング重複なし")

    valid_sessions = set(sessions["sales_session_id"])
    mapped_sessions = set(mapping["sales_session_id"])

    bad_sessions = mapped_sessions - valid_sessions
    missing_sessions = valid_sessions - mapped_sessions

    if bad_sessions:
        errors.append(
            f"存在しないsales_session_id: {sorted(bad_sessions)}"
        )
    else:
        passes.append("sales_session_id整合性OK")

    if missing_sessions:
        errors.append(
            f"商品マッピングがない物販セッション: {sorted(missing_sessions)}"
        )
    else:
        passes.append("全物販セッションに商品あり")

    valid_goods = {
        (row["item_id"], row["variant"])
        for _, row in goods.iterrows()
    }
    bad_goods = []
    for _, row in mapping.iterrows():
        key = (row["item_id"], row["variant"])
        if key not in valid_goods:
            bad_goods.append(
                (
                    row["sales_session_id"],
                    row["item_id"],
                    row["variant"],
                )
            )

    if bad_goods:
        errors.append(
            f"goods.csvに存在しない商品/variant: {bad_goods[:10]}"
        )
    else:
        passes.append("goods.csv整合性OK")

    print("\n=== sales_session_items.csv 自動チェック ===\n")
    for msg in passes:
        print(f"[PASS] {msg}")
    for msg in errors:
        print(f"[FAIL] {msg}")

    counts = (
        mapping.groupby("sales_session_id")
        .size()
        .sort_index()
    )
    print("\n物販セッション別の販売行数:")
    for sid, count in counts.items():
        print(f"  {sid}: {count}")

    print(f"\nPASS: {len(passes)} / FAIL: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
