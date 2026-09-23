from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


STATE_VERSION = 1


def empty_production_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "inventory": [],
        "sync": {},
        "reviews": {},
    }


def load_production_state(
    path: str | Path,
) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return empty_production_state()

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("production state must be a JSON object")

    state = empty_production_state()
    state.update(payload)

    if not isinstance(state.get("inventory"), list):
        raise ValueError("production state inventory must be a list")
    if not isinstance(state.get("sync"), dict):
        raise ValueError("production state sync must be an object")
    if not isinstance(state.get("reviews"), dict):
        raise ValueError("production state reviews must be an object")

    return state


def save_production_state(
    path: str | Path,
    state: dict[str, Any],
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    text = json.dumps(
        state,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def clone_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    return copy.deepcopy(state)


def get_production_inventory_for_session(
    state: dict[str, Any],
    sales_session_id: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in state.get("inventory", []):
        if row.get("sales_session_id") != sales_session_id:
            continue
        key = (
            str(row.get("item_id") or ""),
            str(row.get("variant") or ""),
        )
        result[key] = dict(row)
    return result


def upsert_sold_out(
    state: dict[str, Any],
    *,
    sales_session_id: str,
    item_id: str,
    variant: str,
    source_post_id: str,
    source_post_url: str,
    updated_at: str,
    sold_out_at: str | None = None,
) -> bool:
    inventory = state.setdefault("inventory", [])
    normalized_variant = str(variant or "")

    key = (
        str(sales_session_id),
        str(item_id),
        normalized_variant,
    )

    desired = {
        "sales_session_id": key[0],
        "item_id": key[1],
        "variant": key[2],
        "status": "SOLD_OUT",
        "source_post_id": str(source_post_id),
        "source_post_url": str(source_post_url),
        "updated_at": str(updated_at),
        "sold_out_at": (
            str(sold_out_at)
            if sold_out_at
            else None
        ),
    }

    for index, row in enumerate(inventory):
        row_key = (
            str(row.get("sales_session_id") or ""),
            str(row.get("item_id") or ""),
            str(row.get("variant") or ""),
        )
        if row_key != key:
            continue

        if not sold_out_at:
            desired["sold_out_at"] = row.get("sold_out_at")

        # Do not create a new commit every poll when the exact same post was
        # already applied.
        comparable_existing = dict(row)
        comparable_desired = dict(desired)
        comparable_existing.pop("updated_at", None)
        comparable_desired.pop("updated_at", None)

        if comparable_existing == comparable_desired:
            return False

        inventory[index] = desired
        return True

    inventory.append(desired)
    inventory.sort(
        key=lambda row: (
            str(row.get("sales_session_id") or ""),
            str(row.get("item_id") or ""),
            str(row.get("variant") or ""),
        )
    )
    return True


def get_sync_cursor(
    state: dict[str, Any],
    scope_key: str,
) -> str | None:
    value = state.get("sync", {}).get(scope_key)
    if isinstance(value, dict):
        value = value.get("last_post_id")

    normalized = str(value or "").strip()
    return normalized or None


def set_sync_cursor(
    state: dict[str, Any],
    scope_key: str,
    last_post_id: str,
) -> bool:
    normalized = str(last_post_id or "").strip()
    if not normalized.isdigit():
        raise ValueError("last_post_id must be a numeric X Post ID")

    sync = state.setdefault("sync", {})
    desired = {"last_post_id": normalized}
    if sync.get(scope_key) == desired:
        return False

    sync[scope_key] = desired
    return True


def set_review_posts(
    state: dict[str, Any],
    scope_key: str,
    rows: list[dict[str, str]],
) -> bool:
    reviews = state.setdefault("reviews", {})
    normalized_rows = sorted(
        [
            {
                "post_id": str(row.get("post_id") or ""),
                "post_url": str(row.get("post_url") or ""),
                "reason": str(row.get("reason") or ""),
            }
            for row in rows
        ],
        key=lambda row: row["post_id"],
    )

    if normalized_rows:
        if reviews.get(scope_key) == normalized_rows:
            return False
        reviews[scope_key] = normalized_rows
        return True

    if scope_key in reviews:
        del reviews[scope_key]
        return True

    return False



def overlay_production_inventory(
    local_inventory: dict[tuple[str, str], dict[str, Any]],
    state: dict[str, Any],
    sales_session_id: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    """
    Overlay committed production SOLD_OUT state on top of local SQLite rows.

    Production SOLD_OUT is authoritative for the public app and must not be
    downgraded by an AUTO/AVAILABLE value from the instance-local SQLite DB.
    """
    result = {
        key: dict(value)
        for key, value in local_inventory.items()
    }

    production_rows = get_production_inventory_for_session(
        state,
        sales_session_id,
    )
    for key, row in production_rows.items():
        current = dict(
            result.get(
                key,
                {
                    "sales_session_id": sales_session_id,
                    "item_id": key[0],
                    "variant": key[1],
                },
            )
        )
        current.update(
            {
                "status": "SOLD_OUT",
                "updated_at": row.get("updated_at"),
                "source_post_id": row.get("source_post_id"),
                "source_post_url": row.get("source_post_url"),
                "sold_out_at": row.get("sold_out_at"),
            }
        )
        result[key] = current

    return result
