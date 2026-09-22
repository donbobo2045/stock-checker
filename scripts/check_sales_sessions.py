from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


REQUIRED_COLUMNS = [
    "sales_session_id",
    "tour_id",
    "date",
    "sales_start_time",
    "timezone",
    "source_url",
    "note",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "sales_sessions",
        nargs="?",
        default="data/sales_sessions.csv",
    )
    parser.add_argument(
        "--events",
        default="data/events.csv",
    )
    args = parser.parse_args()

    sessions_path = Path(args.sales_sessions)
    events_path = Path(args.events)

    sessions = pd.read_csv(
        sessions_path,
        dtype=str,
        keep_default_na=False,
    )
    events = pd.read_csv(
        events_path,
        dtype=str,
        keep_default_na=False,
    )

    errors = []
    passes = []

    if list(sessions.columns) == REQUIRED_COLUMNS:
        passes.append("列構成OK")
    else:
        errors.append(
            f"列構成NG: {list(sessions.columns)}"
        )

    if sessions["sales_session_id"].duplicated().any():
        errors.append(
            "sales_session_id に重複があります"
        )
    else:
        passes.append(
            "sales_session_id 重複なし"
        )

    event_sessions = set(
        events["sales_session_id"]
    )
    master_sessions = set(
        sessions["sales_session_id"]
    )

    missing = event_sessions - master_sessions
    extra = master_sessions - event_sessions

    if missing:
        errors.append(
            f"events.csv にあるが"
            f"sales_sessions.csv にない: "
            f"{sorted(missing)}"
        )
    else:
        passes.append(
            "events.csv の全物販セッションを網羅"
        )

    if extra:
        errors.append(
            f"events.csv に存在しない"
            f"余分な物販セッション: "
            f"{sorted(extra)}"
        )
    else:
        passes.append(
            "余分な物販セッションなし"
        )

    event_session_meta = (
        events[
            [
                "sales_session_id",
                "tour_id",
                "date",
            ]
        ]
        .drop_duplicates()
        .set_index("sales_session_id")
    )

    for idx, row in sessions.iterrows():
        line = idx + 2
        sid = row["sales_session_id"]

        try:
            datetime.strptime(
                row["date"],
                "%Y-%m-%d",
            )
        except ValueError:
            errors.append(
                f"{line}行目: date形式NG"
            )

        try:
            datetime.strptime(
                row["sales_start_time"],
                "%H:%M",
            )
        except ValueError:
            errors.append(
                f"{line}行目: "
                f"sales_start_time形式NG"
            )

        try:
            ZoneInfo(row["timezone"])
        except Exception:
            errors.append(
                f"{line}行目: timezone不正 "
                f"{row['timezone']}"
            )

        if (
            row["source_url"]
            and not row["source_url"].startswith(
                ("https://", "http://")
            )
        ):
            errors.append(
                f"{line}行目: source_url形式NG"
            )

        if sid in event_session_meta.index:
            expected = event_session_meta.loc[sid]

            if (
                row["tour_id"]
                != expected["tour_id"]
            ):
                errors.append(
                    f"{sid}: tour_id不一致"
                )

            if (
                row["date"]
                != expected["date"]
            ):
                errors.append(
                    f"{sid}: date不一致"
                )

    if not errors:
        passes.append(
            "日付・時刻・timezone・"
            "events.csv整合性OK"
        )

    print(
        "\n=== sales_sessions.csv "
        "自動チェック ===\n"
    )
    for msg in passes:
        print(f"[PASS] {msg}")
    for msg in errors:
        print(f"[FAIL] {msg}")

    print(
        f"\nPASS: {len(passes)} / "
        f"FAIL: {len(errors)}"
    )

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
