from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from catalog import get_goods_for_session
from config import (
    ENABLE_SALES_END_STATUS as DEFAULT_ENABLE_SALES_END_STATUS,
    TEST_NOW_ISO as DEFAULT_TEST_NOW_ISO,
)
from dev_settings import build_virtual_now
from database import (
    apply_parsed_sold_out,
    apply_x_parsed_posts_and_advance_cursor,
    ensure_inventory_rows,
    get_inventory_for_session,
    get_x_sync_cursor,
    init_db,
    reset_session,
    reset_x_sync_cursor,
    set_x_sync_cursor,
    update_status,
)
from parser import SoldOutPostParser
from production_state import (
    load_production_state,
    overlay_production_inventory,
)
from search_logic import filter_goods_for_search
from selection_logic import get_default_event_id, get_tour_id_for_event
from x_client import XApiClient, XApiError
from x_preview import IGNORED, PARSED, REVIEW, classify_parse_result
from x_sync_logic import (
    build_event_day_search_plan,
    get_tour_event_dates,
    is_full_event_day_recent_search_eligible,
    newest_post_id,
)
from status_logic import (
    AUTO,
    AVAILABLE,
    PRE_SALE,
    SALES_ENDED,
    SOLD_OUT,
    get_effective_status,
    get_sales_end_at,
    get_sales_start_at,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

GOODS_CSV = DATA_DIR / "goods.csv"
EVENTS_CSV = DATA_DIR / "events.csv"
ALIASES_CSV = DATA_DIR / "item_aliases.csv"
SALES_SESSIONS_CSV = DATA_DIR / "sales_sessions.csv"
SALES_SESSION_ITEMS_CSV = DATA_DIR / "sales_session_items.csv"
PRODUCTION_STATE_PATH = DATA_DIR / "production_state.json"

X_USERNAME = "SDE_STARDUSTBIN"
X_SEARCH_QUERY = (
    "from:SDE_STARDUSTBIN "
    "(ICEx OR #ICEx) 完売 -is:retweet"
)

EFFECTIVE_LABELS = {
    PRE_SALE: "🟡 販売前",
    AVAILABLE: "🟢 販売中",
    SOLD_OUT: "🔴 完売",
    SALES_ENDED: "⚫ 販売終了",
}

STORED_STATUS_ORDER = [AUTO, AVAILABLE, SOLD_OUT]
STORED_STATUS_LABELS = {
    AUTO: "⏱ 自動判定",
    AVAILABLE: "🟢 販売中（手動固定）",
    SOLD_OUT: "🔴 完売",
}

st.set_page_config(
    page_title="ライブグッズ在庫チェッカー",
    page_icon="🛍️",
    layout="wide",
)


st.markdown(
    """
    <style>
    .block-container {
        max-width: 980px;
        padding-top: 1rem;
        padding-bottom: 3rem;
    }

    div[data-testid="stButton"] button {
        min-height: 44px;
    }

    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.75rem;
            padding-right: 0.75rem;
            padding-top: 0.5rem;
        }

        h1 {
            font-size: 1.65rem !important;
            line-height: 1.2 !important;
        }

        h2 {
            font-size: 1.35rem !important;
        }

        h3 {
            font-size: 1.15rem !important;
        }

        div[data-testid="stButton"] button,
        div[data-baseweb="select"] {
            min-height: 44px;
        }

        input, textarea {
            font-size: 16px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data():
    goods = pd.read_csv(
        GOODS_CSV,
        dtype=str,
        keep_default_na=False,
    )
    events = pd.read_csv(
        EVENTS_CSV,
        dtype=str,
        keep_default_na=False,
    )
    sessions = pd.read_csv(
        SALES_SESSIONS_CSV,
        dtype=str,
        keep_default_na=False,
    )
    session_items = pd.read_csv(
        SALES_SESSION_ITEMS_CSV,
        dtype=str,
        keep_default_na=False,
    )
    aliases = pd.read_csv(
        ALIASES_CSV,
        dtype=str,
        keep_default_na=False,
    )

    goods["price_numeric"] = pd.to_numeric(
        goods["price"],
        errors="coerce",
    )

    return goods, events, sessions, session_items, aliases


@st.cache_resource
def load_parser():
    return SoldOutPostParser.from_csv(
        GOODS_CSV,
        EVENTS_CSV,
        ALIASES_CSV,
        SALES_SESSION_ITEMS_CSV,
    )


def event_display_name(row: pd.Series) -> str:
    part = f" / {row['part_label']}" if row["part_label"] else ""
    return (
        f"{row['date']} / {row['prefecture']} / "
        f"{row['venue']}{part}"
    )


def format_price(value: object) -> str:
    try:
        return f"¥{int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def session_to_dict(row: pd.Series) -> dict:
    return {
        key: str(value)
        for key, value in row.to_dict().items()
    }


def get_current_time(
    session: dict,
    test_now: datetime | None = None,
) -> datetime:
    """
    通常は実時刻。
    test_now が指定されている場合は仮想現在時刻を使用。
    """
    timezone = ZoneInfo(session["timezone"])

    if test_now is None:
        return datetime.now(timezone)

    if test_now.tzinfo is None:
        return test_now.replace(tzinfo=timezone)

    return test_now.astimezone(timezone)


def format_sold_out_detail(
    inventory_row: dict,
    session: dict,
) -> str | None:
    raw_value = inventory_row.get("sold_out_at")
    if not raw_value:
        return None

    try:
        sold_out_at = datetime.fromisoformat(
            str(raw_value).replace("Z", "+00:00")
        )
    except ValueError:
        return None

    timezone = ZoneInfo(session["timezone"])
    if sold_out_at.tzinfo is None:
        sold_out_at = sold_out_at.replace(
            tzinfo=timezone
        )
    else:
        sold_out_at = sold_out_at.astimezone(
            timezone
        )

    sales_start_at = get_sales_start_at(session)
    elapsed_minutes = int(
        (
            sold_out_at - sales_start_at
        ).total_seconds()
        // 60
    )

    if elapsed_minutes < 0:
        elapsed_text = "販売開始前"
    else:
        hours, minutes = divmod(
            elapsed_minutes,
            60,
        )
        if hours and minutes:
            elapsed_text = (
                f"{hours}時間{minutes}分"
            )
        elif hours:
            elapsed_text = f"{hours}時間"
        else:
            elapsed_text = f"{minutes}分"

        elapsed_text = (
            f"販売開始から{elapsed_text}"
        )

    return (
        f"{sold_out_at.strftime('%H:%M')}完売"
        f"（{elapsed_text}）"
    )


def get_x_bearer_token() -> str:
    """Return X API Bearer Token without exposing it in the UI."""
    env_value = os.getenv("X_BEARER_TOKEN", "").strip()
    if env_value:
        return env_value

    try:
        value = st.secrets.get("X_BEARER_TOKEN", "")
    except (FileNotFoundError, KeyError):
        return ""

    return str(value or "").strip()


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_public_read_only() -> bool:
    """Public cloud mode hides all mutation/debug controls."""
    env_value = os.getenv("PUBLIC_READ_ONLY", "").strip()
    if env_value:
        return _as_bool(env_value)

    try:
        value = st.secrets.get("PUBLIC_READ_ONLY", False)
    except (FileNotFoundError, KeyError):
        return False

    return _as_bool(value)


public_read_only = get_public_read_only()
runtime_enable_sales_end = (
    True
    if public_read_only
    else DEFAULT_ENABLE_SALES_END_STATUS
)
runtime_test_now = None

init_db()

st.title("🛍️ ライブグッズ在庫チェッカー")
st.caption(
    "販売開始前は「販売前」、開始時刻以降は「販売中」、"
    "完売情報反映後は「完売」と表示します。"
)
if public_read_only:
    st.caption(
        "公開テスト版：完売情報はXから定期取得して自動反映します。"
        "管理・手動更新機能は非表示です。"
    )

try:
    goods, events, sales_sessions, sales_session_items, aliases = load_data()
    parser = load_parser()
except Exception as exc:
    st.error(f"初期化に失敗しました：{exc}")
    st.stop()

if goods.empty or events.empty or sales_sessions.empty:
    st.warning(
        "goods.csv / events.csv / sales_sessions.csv "
        "のいずれかにデータがありません。"
    )
    st.stop()

# 初回表示は「今日以降で最も近い公演日」。
# 全公演終了後は最終公演日にフォールバックする。
default_event_id_global = get_default_event_id(
    events,
    timezone_name="Asia/Tokyo",
)
default_tour_id_global = get_tour_id_for_event(
    events,
    default_event_id_global,
)

# ---- Sidebar ----
with st.sidebar:
    st.header("公演選択")

    tour_ids = sorted(
        set(goods["tour_id"]) & set(events["tour_id"])
    )
    if not tour_ids:
        st.error(
            "goods.csv と events.csv で"
            "共通の tour_id がありません。"
        )
        st.stop()

    default_tour_index = (
        tour_ids.index(default_tour_id_global)
        if default_tour_id_global in tour_ids
        else 0
    )

    selected_tour_id = st.selectbox(
        "ツアー",
        tour_ids,
        index=default_tour_index,
        format_func=lambda tid: goods.loc[
            goods["tour_id"] == tid,
            "tour_name",
        ].iloc[0],
    )

    tour_events = events[
        events["tour_id"] == selected_tour_id
    ].copy()
    tour_events["display_name"] = tour_events.apply(
        event_display_name,
        axis=1,
    )

    event_ids = tour_events["event_id"].tolist()

    default_event_id_for_tour = get_default_event_id(
        tour_events,
        timezone_name="Asia/Tokyo",
        tour_id=selected_tour_id,
    )

    default_event_index = (
        event_ids.index(default_event_id_for_tour)
        if default_event_id_for_tour in event_ids
        else 0
    )

    selected_event_id = st.selectbox(
        "公演",
        event_ids,
        index=default_event_index,
        format_func=lambda event_id: tour_events.loc[
            tour_events["event_id"] == event_id,
            "display_name",
        ].iloc[0],
    )

    selected_event = tour_events[
        tour_events["event_id"] == selected_event_id
    ].iloc[0]
    sales_session_id = selected_event["sales_session_id"]

    matching_sessions = sales_sessions[
        sales_sessions["sales_session_id"]
        == sales_session_id
    ]

    if len(matching_sessions) != 1:
        st.error(
            "sales_sessions.csv で物販セッションを"
            "一意に特定できません。"
        )
        st.stop()

    selected_sales_session = matching_sessions.iloc[0]
    selected_sales_session_dict = session_to_dict(
        selected_sales_session
    )

    st.divider()
    st.write("**物販セッション**")
    st.code(sales_session_id)
    st.write(
        f"**販売開始：** "
        f"{selected_sales_session['date']} "
        f"{selected_sales_session['sales_start_time']}"
    )

    if not public_read_only:
        st.divider()

        with st.expander("🧪 開発者用テスト設定", expanded=False):
            st.caption(
                "ここで変更した値はテスト用です。"
                "ウィジェットを変更すると即時反映されます。"
            )

            runtime_enable_sales_end = st.checkbox(
                "販売終了ステータスを有効化",
                value=DEFAULT_ENABLE_SALES_END_STATUS,
                key="dev_enable_sales_end",
                help=(
                    "ONにすると、公演日の翌日0:00以降、"
                    "完売以外の商品を「販売終了」と表示します。"
                ),
            )

            use_test_now = st.checkbox(
                "仮想現在時刻を使用",
                value=bool(DEFAULT_TEST_NOW_ISO),
                key="dev_use_test_now",
                help=(
                    "ONにすると、実際の現在時刻ではなく"
                    "下で指定した日時をステータス判定に使います。"
                ),
            )

            session_timezone = ZoneInfo(
                selected_sales_session_dict["timezone"]
            )

            if DEFAULT_TEST_NOW_ISO:
                try:
                    default_virtual_now = datetime.fromisoformat(
                        DEFAULT_TEST_NOW_ISO
                    )
                    if default_virtual_now.tzinfo is None:
                        default_virtual_now = default_virtual_now.replace(
                            tzinfo=session_timezone
                        )
                    else:
                        default_virtual_now = default_virtual_now.astimezone(
                            session_timezone
                        )
                except ValueError:
                    default_virtual_now = datetime.now(session_timezone)
            else:
                default_virtual_now = datetime.now(session_timezone)

            test_date = st.date_input(
                "仮想日付",
                value=default_virtual_now.date(),
                key="dev_test_date",
                disabled=not use_test_now,
            )

            test_time = st.time_input(
                "仮想時刻",
                value=default_virtual_now.time().replace(
                    second=0,
                    microsecond=0,
                    tzinfo=None,
                ),
                key="dev_test_time",
                step=60,
                disabled=not use_test_now,
            )

            if use_test_now:
                runtime_test_now = build_virtual_now(
                    test_date,
                    test_time,
                    selected_sales_session_dict["timezone"],
                )
                st.info(
                    "判定時刻："
                    f"{runtime_test_now.strftime('%Y-%m-%d %H:%M %Z')}"
                )
            else:
                runtime_test_now = None
                st.caption("判定時刻：実際の現在時刻")

            if runtime_enable_sales_end:
                st.warning(
                    "販売終了ロジック：ON\n\n"
                    "完売以外は翌日0:00以降に販売終了になります。"
                )
            else:
                st.success(
                    "販売終了ロジック：OFF（テスト推奨）"
                )

        st.divider()

        if st.button(
            "CSV / alias / parserを再読み込み",
            use_container_width=True,
        ):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()


if not public_read_only:
    # ---- X API sync preview (Phase 10.3) ----
    with st.expander(
        "📡 X API取得・在庫反映テスト（Phase 10.3）",
        expanded=False,
    ):
        st.caption(
            "@SDE_STARDUSTBIN のうち、本文にICExと完売を含む"
            "ポストだけを対象にします。"
            "イベント日単位で取得し、2回目以降はsince_idで"
            "増分取得します。解析成功分は確認後にSOLD_OUTへ反映できます。"
        )

        x_bearer_token = get_x_bearer_token()
        st.caption(f"検索条件：`{X_SEARCH_QUERY}`")

        actual_now_jst = datetime.now(ZoneInfo("Asia/Tokyo"))
        x_event_dates = get_tour_event_dates(
            events,
            selected_tour_id,
        )

        recent_rehearsal_dates = [
            event_date
            for event_date in x_event_dates
            if is_full_event_day_recent_search_eligible(
                event_date,
                actual_now_jst,
            )
        ]

        x_mode = st.radio(
            "取得モード",
            [
                "リハーサル（過去イベント日）",
                "本番当日",
            ],
            key="x_sync_mode",
        )

        x_fetch_enabled = bool(x_bearer_token)
        x_event_date = None
        x_cutoff = None
        x_scope = None

        if x_mode == "リハーサル（過去イベント日）":
            if not recent_rehearsal_dates:
                st.warning(
                    "Recent Searchでイベント日全体を取得できる"
                    "過去公演がありません。"
                )
                x_fetch_enabled = False
            else:
                x_event_date = st.selectbox(
                    "リハーサル対象日",
                    recent_rehearsal_dates,
                    index=len(recent_rehearsal_dates) - 1,
                    key="x_rehearsal_event_date",
                )

                rehearsal_cutoff_time = st.time_input(
                    "仮想の取得終了時刻",
                    value=datetime.strptime(
                        "15:00",
                        "%H:%M",
                    ).time(),
                    step=60,
                    key="x_rehearsal_cutoff_time",
                    help=(
                        "例：まず15:00で取得してsince_idを保存し、"
                        "次に18:00へ進めると増分取得を試せます。"
                    ),
                )

                x_cutoff = datetime.combine(
                    datetime.fromisoformat(
                        x_event_date
                    ).date(),
                    rehearsal_cutoff_time,
                    tzinfo=ZoneInfo("Asia/Tokyo"),
                )
                x_scope = (
                    f"rehearsal:{selected_tour_id}:"
                    f"{x_event_date}"
                )
        else:
            today_iso = actual_now_jst.date().isoformat()
            if today_iso not in x_event_dates:
                st.info(
                    f"今日は対象ツアーのイベント日ではありません。"
                    f"現在日：{today_iso}"
                )
                next_dates = [
                    d for d in x_event_dates
                    if d > today_iso
                ]
                if next_dates:
                    st.caption(
                        f"次のイベント日：{next_dates[0]}"
                    )
                x_fetch_enabled = False
            else:
                x_event_date = today_iso
                x_cutoff = actual_now_jst
                x_scope = (
                    f"live:{selected_tour_id}:"
                    f"{x_event_date}"
                )
                st.success(
                    f"本番当日モード：{x_event_date} "
                    f"{actual_now_jst.strftime('%H:%M:%S')} JST"
                )

        if not x_bearer_token:
            st.info(
                "X_BEARER_TOKEN が未設定です。"
                "ローカルでは .streamlit/secrets.toml、"
                "Streamlit Community CloudではApp settingsのSecretsに設定してください。"
            )

        x_max_results = st.number_input(
            "1回の検索で取得する最大件数",
            min_value=10,
            max_value=100,
            value=20,
            step=10,
            key="x_api_max_results",
        )

        x_cursor = (
            get_x_sync_cursor(x_scope)
            if x_scope
            else None
        )

        x_plan = None
        if x_event_date and x_cutoff:
            try:
                x_plan = build_event_day_search_plan(
                    x_event_date,
                    x_cutoff,
                    since_id=x_cursor,
                    timezone_name="Asia/Tokyo",
                )
            except ValueError as exc:
                st.warning(str(exc))
                x_fetch_enabled = False

        if x_plan is not None:
            if x_plan.mode == "initial":
                st.write("**取得方式：** 初回イベント日取得")
                st.caption(
                    f"start_time={x_plan.start_time} / "
                    f"end_time={x_plan.end_time}"
                )
            else:
                st.write("**取得方式：** since_idによる増分取得")
                if x_mode == "リハーサル（過去イベント日）":
                    st.caption(
                        f"since_id={x_plan.since_id} / "
                        "API上限は現在時刻・画面では仮想終了時刻までに絞り込み"
                    )
                else:
                    st.caption(
                        f"since_id={x_plan.since_id} / "
                        "現在時刻まで"
                    )

        cursor_col1, cursor_col2 = st.columns(2)
        with cursor_col1:
            if x_cursor:
                st.caption(f"保存済みsince_id：{x_cursor}")
            else:
                st.caption("保存済みsince_id：なし")

        with cursor_col2:
            if st.button(
                "since_idをリセット",
                disabled=not bool(x_cursor and x_scope),
                key="reset_x_preview_cursor",
                use_container_width=True,
            ):
                reset_x_sync_cursor(x_scope)
                st.session_state.pop(
                    "x_preview_results",
                    None,
                )
                st.session_state.pop(
                    "x_cursor_candidate",
                    None,
                )
                st.session_state.pop(
                    "x_preview_scope",
                    None,
                )
                st.rerun()

        if st.button(
            "このイベント日のポストを取得・解析",
            type="primary",
            disabled=not bool(x_fetch_enabled and x_plan),
            key="fetch_x_api_posts",
        ):
            try:
                with st.spinner(
                    "X APIでイベント日の条件一致ポストを検索しています..."
                ):
                    x_client = XApiClient(x_bearer_token)
                    x_posts = x_client.search_recent_posts(
                        X_SEARCH_QUERY,
                        username=X_USERNAME,
                        max_results=int(x_max_results),
                        start_time=x_plan.start_time,
                        end_time=x_plan.end_time,
                        since_id=x_plan.since_id,
                    )

                    # Incremental rehearsal uses since_id without end_time.
                    # Keep the API request production-like, then trim any posts
                    # later than the virtual rehearsal cutoff locally.
                    if (
                        x_plan.mode == "incremental"
                        and x_mode == "リハーサル（過去イベント日）"
                    ):
                        cutoff_utc = x_cutoff.astimezone(
                            ZoneInfo("UTC")
                        )
                        filtered_posts = []
                        for post in x_posts:
                            if not post.created_at:
                                continue
                            created_at = datetime.fromisoformat(
                                post.created_at.replace(
                                    "Z",
                                    "+00:00",
                                )
                            )
                            if created_at <= cutoff_utc:
                                filtered_posts.append(post)
                        x_posts = filtered_posts

                    preview_results = []
                    for post in x_posts:
                        parsed_result = parser.parse(post.text)
                        category = classify_parse_result(
                            parsed_result
                        )

                        # Safety gate: an API result is only auto-applicable when
                        # the parser resolved it to the same tour/event date that
                        # the X search is currently rehearsing or monitoring.
                        if (
                            category == PARSED
                            and (
                                parsed_result.tour_id
                                != selected_tour_id
                                or parsed_result.date
                                != x_event_date
                            )
                        ):
                            category = REVIEW
                            parsed_result.reason = (
                                "X取得対象とparser解析結果が不一致です。"
                                f" 取得={selected_tour_id}/{x_event_date},"
                                f" 解析={parsed_result.tour_id}/"
                                f"{parsed_result.date}"
                            )

                        preview_results.append(
                            {
                                "post": post,
                                "parsed_result": parsed_result,
                                "category": category,
                            }
                        )

                    st.session_state["x_preview_results"] = (
                        preview_results
                    )
                    st.session_state["x_cursor_candidate"] = (
                        newest_post_id(
                            [post.id for post in x_posts]
                        )
                    )
                    st.session_state["x_preview_scope"] = (
                        x_scope
                    )
                    st.session_state["x_preview_plan"] = (
                        x_plan
                    )
            except (XApiError, ValueError) as exc:
                st.session_state.pop(
                    "x_preview_results",
                    None,
                )
                st.session_state.pop(
                    "x_cursor_candidate",
                    None,
                )
                st.error(
                    f"X API取得に失敗しました：{exc}"
                )

        same_scope = (
            st.session_state.get("x_preview_scope")
            == x_scope
        )
        x_preview_results = (
            st.session_state.get(
                "x_preview_results",
                [],
            )
            if same_scope
            else []
        )
        x_cursor_candidate = (
            st.session_state.get(
                "x_cursor_candidate"
            )
            if same_scope
            else None
        )

        if (
            same_scope
            and "x_preview_results" in st.session_state
            and not x_preview_results
        ):
            st.info(
                "この取得範囲には条件一致の新規ポストがありませんでした。"
            )

        if x_preview_results:
            parsed_count = sum(
                1 for row in x_preview_results
                if row["category"] == PARSED
            )
            review_count = sum(
                1 for row in x_preview_results
                if row["category"] == REVIEW
            )
            ignored_count = sum(
                1 for row in x_preview_results
                if row["category"] == IGNORED
            )

            st.markdown(
                f"✅ **解析成功 {parsed_count}**　"
                f"⚠️ **要確認 {review_count}**　"
                f"－ **対象外 {ignored_count}**"
            )

            for row in x_preview_results:
                post = row["post"]
                parsed_result = row["parsed_result"]
                category = row["category"]

                label = {
                    PARSED: "✅ 解析成功",
                    REVIEW: "⚠️ 要確認",
                    IGNORED: "－ 対象外",
                }[category]

                with st.container(border=True):
                    st.markdown(
                        f"**{label}**　Post ID: {post.id}"
                    )
                    if post.created_at:
                        st.caption(
                            f"投稿時刻：{post.created_at}"
                        )
                    st.markdown(
                        f"[Xで元ポストを開く]({post.url})"
                    )
                    st.code(
                        post.text,
                        language=None,
                    )

                    if category == PARSED:
                        st.write(
                            f"**対象物販セッション：** "
                            f"{parsed_result.sales_session_id}  "
                            f"（{parsed_result.date} / "
                            f"{parsed_result.venue}）"
                        )
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "item_id": item.item_id,
                                        "商品名": item.item_name,
                                        "variant": (
                                            item.variant
                                            or "(なし)"
                                        ),
                                        "判定": (
                                            "SOLD_OUT候補"
                                        ),
                                    }
                                    for item
                                    in parsed_result.items
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.caption(
                            f"判定理由："
                            f"{parsed_result.reason}"
                        )

        if x_cursor_candidate and x_scope:
            st.divider()
            st.write(
                f"**今回の最新Post ID候補：** "
                f"{x_cursor_candidate}"
            )

            x_parsed_rows = [
                row
                for row in x_preview_results
                if row["category"] == PARSED
            ]
            x_review_rows = [
                row
                for row in x_preview_results
                if row["category"] == REVIEW
            ]

            if x_review_rows:
                st.warning(
                    "⚠️ 要確認の投稿が含まれるため、"
                    "SOLD_OUT反映とsince_id更新の同時確定は停止しています。"
                    "解析成功分だけを反映してもcursorは進めません。"
                )

                if x_parsed_rows:
                    confirm_partial_apply = st.checkbox(
                        "要確認投稿を飛ばさず、解析成功分だけ"
                        "SOLD_OUTへ反映することを確認しました",
                        key="confirm_x_partial_apply",
                    )
                    if st.button(
                        "解析成功分だけSOLD_OUTへ反映"
                        "（since_idは進めない）",
                        disabled=not confirm_partial_apply,
                        key="apply_x_parsed_without_cursor",
                        use_container_width=True,
                    ):
                        for row in x_parsed_rows:
                            post = row["post"]
                            parsed_result = row["parsed_result"]
                            apply_parsed_sold_out(
                                parsed_result.sales_session_id,
                                [
                                    (item.item_id, item.variant)
                                    for item in parsed_result.items
                                ],
                                source_post_id=post.id,
                                source_post_url=post.url,
                            )
                        st.success(
                            "解析成功分をSQLiteへ反映しました。"
                            "要確認投稿があるためsince_idは変更していません。"
                        )
                        st.rerun()
            elif x_parsed_rows:
                st.success(
                    "✅ 要確認投稿はありません。"
                    "解析成功分をSOLD_OUTへ反映し、"
                    "同時にsince_idを進められます。"
                )

                apply_preview_rows = []
                for row in x_parsed_rows:
                    post = row["post"]
                    parsed_result = row["parsed_result"]
                    for item in parsed_result.items:
                        apply_preview_rows.append(
                            {
                                "Post ID": post.id,
                                "sales_session_id": (
                                    parsed_result.sales_session_id
                                ),
                                "item_id": item.item_id,
                                "商品名": item.item_name,
                                "variant": item.variant or "(なし)",
                                "反映": "SOLD_OUT",
                            }
                        )

                st.dataframe(
                    pd.DataFrame(apply_preview_rows),
                    use_container_width=True,
                    hide_index=True,
                )

                confirm_x_apply = st.checkbox(
                    "上記のX API解析結果を確認しました",
                    key="confirm_x_apply_and_cursor",
                )

                if st.button(
                    "SOLD_OUTへ反映 ＋ since_idを保存",
                    type="primary",
                    disabled=not confirm_x_apply,
                    key="apply_x_and_advance_cursor",
                    use_container_width=True,
                ):
                    parsed_posts_payload = []
                    for row in x_parsed_rows:
                        post = row["post"]
                        parsed_result = row["parsed_result"]
                        parsed_posts_payload.append(
                            (
                                parsed_result.sales_session_id,
                                [
                                    (item.item_id, item.variant)
                                    for item in parsed_result.items
                                ],
                                post.id,
                                post.url,
                            )
                        )

                    apply_x_parsed_posts_and_advance_cursor(
                        x_scope,
                        parsed_posts_payload,
                        x_cursor_candidate,
                    )
                    st.success(
                        "SOLD_OUT反映とsince_id保存を"
                        "同一トランザクションで完了しました。"
                    )
                    st.session_state.pop(
                        "x_preview_results",
                        None,
                    )
                    st.session_state.pop(
                        "x_cursor_candidate",
                        None,
                    )
                    st.session_state.pop(
                        "x_preview_scope",
                        None,
                    )
                    st.rerun()
            else:
                st.info(
                    "今回の取得結果は対象外投稿のみです。"
                    "在庫DBは変更せず、cursorだけ進められます。"
                )
                if st.button(
                    "対象外投稿を処理済みとしてsince_idを保存",
                    key="advance_cursor_ignored_only",
                    use_container_width=True,
                ):
                    set_x_sync_cursor(
                        x_scope,
                        x_cursor_candidate,
                    )
                    st.success(
                        "在庫DBは変更せず、since_idだけ保存しました。"
                    )
                    st.rerun()


    # ---- Manual post parser / admin ----
    with st.expander("🛠 完売ポスト手動解析（テスト・管理）", expanded=False):
        post_text = st.text_area(
            "スタダ便の完売ポスト本文を貼り付け",
            height=260,
            placeholder=(
                "完売商品と「完売情報」または「本日分完売」を含む"
                "ポスト本文をそのまま貼り付けてください"
            ),
        )

        source_url = st.text_input(
            "元ポストURL（任意）",
            placeholder="https://x.com/...",
        )
        source_post_id = st.text_input(
            "Post ID（任意）",
            placeholder="X API接続後に利用予定",
        )

        parsed_result = None

        if st.button(
            "解析する",
            type="primary",
            disabled=not post_text.strip(),
        ):
            parsed_result = parser.parse(post_text)
            st.session_state["last_parse"] = parsed_result

        if "last_parse" in st.session_state:
            parsed_result = st.session_state["last_parse"]

        if parsed_result is not None:
            if not parsed_result.is_relevant:
                st.warning(
                    f"自動反映対象外：{parsed_result.reason}"
                )
            else:
                st.success("完売情報として解析できました。")

                st.write(
                    f"**対象物販セッション：** "
                    f"`{parsed_result.sales_session_id}`  "
                    f"（{parsed_result.date} / "
                    f"{parsed_result.venue}）"
                )

                preview_rows = [
                    {
                        "item_id": item.item_id,
                        "商品名": item.item_name,
                        "variant": item.variant or "(なし)",
                        "反映状態": "SOLD_OUT",
                    }
                    for item in parsed_result.items
                ]

                st.dataframe(
                    pd.DataFrame(preview_rows),
                    use_container_width=True,
                    hide_index=True,
                )

                if (
                    parsed_result.sales_session_id
                    != sales_session_id
                ):
                    st.info(
                        "現在画面で選択している公演とは"
                        "別の物販セッションです。"
                        "解析結果の公演へ反映されます。"
                    )

                confirm = st.checkbox(
                    "上記の解析結果を確認しました",
                    key="confirm_parse_apply",
                )

                if st.button(
                    "解析結果をSOLD_OUTとして反映",
                    disabled=not confirm,
                    type="primary",
                ):
                    apply_parsed_sold_out(
                        parsed_result.sales_session_id,
                        [
                            (item.item_id, item.variant)
                            for item in parsed_result.items
                        ],
                        source_post_id=(
                            source_post_id or None
                        ),
                        source_post_url=(
                            source_url or None
                        ),
                    )
                    st.success("SQLiteへ反映しました。")
                    st.session_state.pop(
                        "last_parse",
                        None,
                    )
                    st.rerun()

st.divider()

st.subheader("📍 現在選択中の公演")
st.markdown(
    f"## {event_display_name(selected_event)}"
)
st.caption(
    "スマホで公演を変更する場合は、左上メニューからサイドバーを開いてください。"
)

sales_start_at = get_sales_start_at(
    selected_sales_session_dict
)
now_for_header = get_current_time(
    selected_sales_session_dict,
    runtime_test_now,
)

sales_end_at = get_sales_end_at(
    selected_sales_session_dict
)

st.markdown(
    "**販売開始** "
    f"{sales_start_at.strftime('%H:%M')}　"
    "｜ **開場** "
    f"{selected_event['doors_time']}　"
    "｜ **開演** "
    f"{selected_event['start_time']}"
)
st.caption(
    "販売終了判定："
    f"{sales_end_at.strftime('%m/%d %H:%M')} ／ "
    "現在時刻："
    f"{now_for_header.strftime('%m/%d %H:%M')}"
)

if runtime_enable_sales_end:
    st.caption(
        "販売終了ロジック：ON。"
        "公演日の翌日0:00以降、完売以外の商品は"
        "「販売終了」になります。"
    )
else:
    st.caption(
        "販売終了ロジック：OFF（テストモード）。"
        "過去公演でも完売以外は販売中表示を維持します。"
    )

if runtime_test_now is not None:
    st.warning(
        "仮想現在時刻を使用中："
        f"{runtime_test_now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )

st.caption(
    "在庫表示は60秒ごとに自動更新します。"
    "AUTOの商品は販売開始時刻を境に"
    "「販売前 → 販売中」へ切り替わります。"
)



st.markdown("### 🔎 グッズ検索")
goods_search_query = st.text_input(
    "商品名・メンバー名・略称で検索",
    placeholder="例：うちわ、山本、アクスタ、ペンラ",
    key="goods_search_query",
)
st.caption(
    "検索は表示の絞り込みだけです。"
    "曖昧な語（例：シール、タオル）は該当候補を複数表示します。"
)



@st.fragment(run_every="60s")
def render_inventory():
    all_session_goods = get_goods_for_session(
        goods[
            goods["tour_id"] == selected_tour_id
        ].copy(),
        sales_session_items,
        sales_session_id,
    )

    # DB行は検索結果ではなく、その物販セッションの全商品分を確保する。
    ensure_inventory_rows(
        sales_session_id,
        [
            (
                row["item_id"],
                row["variant"],
            )
            for _, row in all_session_goods.iterrows()
        ],
    )

    tour_goods = filter_goods_for_search(
        all_session_goods,
        aliases,
        goods_search_query,
    )

    if goods_search_query.strip():
        matched_item_count = tour_goods["item_id"].nunique()
        st.caption(
            f"検索結果：{matched_item_count}商品 / "
            f"{len(tour_goods)}バリエーション"
        )

    if tour_goods.empty:
        st.info("検索条件に一致するグッズはありません。")
        return

    inventory = get_inventory_for_session(
        sales_session_id
    )
    production_state = load_production_state(
        PRODUCTION_STATE_PATH
    )
    inventory = overlay_production_inventory(
        inventory,
        production_state,
        sales_session_id,
    )

    session = selected_sales_session_dict
    now = get_current_time(session, runtime_test_now)

    effective_by_key = {}

    for _, row in tour_goods.iterrows():
        key = (
            row["item_id"],
            row["variant"],
        )
        stored = inventory.get(
            key,
            {"status": AUTO},
        )["status"]
        effective_by_key[key] = (
            get_effective_status(
                stored,
                session,
                now=now,
                enable_sales_end=runtime_enable_sales_end,
            )
        )

    effective_values = list(
        effective_by_key.values()
    )

    st.markdown(
        f"🟡 **販売前 {effective_values.count(PRE_SALE)}**　"
        f"🟢 **販売中 {effective_values.count(AVAILABLE)}**　"
        f"🔴 **完売 {effective_values.count(SOLD_OUT)}**　"
        f"⚫ **販売終了 {effective_values.count(SALES_ENDED)}**"
    )

    st.caption(
        f"最終時刻判定："
        f"{now.strftime('%Y-%m-%d %H:%M:%S')} "
        f"({session['timezone']})"
    )

    st.divider()

    for item_id, item_rows in tour_goods.groupby(
        "item_id",
        sort=False,
    ):
        item_name = item_rows[
            "item_name"
        ].iloc[0]
        price = item_rows[
            "price_numeric"
        ].iloc[0]
        image_urls = [
            url
            for url in item_rows[
                "image_url"
            ].tolist()
            if url
        ]

        with st.container(border=True):
            st.markdown(f"### {item_name}")
            st.write(f"**価格：{format_price(price)}**")

            if image_urls:
                st.image(
                    image_urls[0],
                    width=180,
                )
            else:
                st.caption("🛍️ 画像未登録")

            for _, row in item_rows.iterrows():
                variant = row["variant"]
                key = (
                    row["item_id"],
                    variant,
                )

                stored = inventory[
                    key
                ]["status"]
                effective = (
                    effective_by_key[key]
                )

                st.markdown(
                    f"**{variant if variant else '通常'}**　"
                    f"{EFFECTIVE_LABELS[effective]}"
                )

                if effective == SOLD_OUT:
                    sold_out_detail = (
                        format_sold_out_detail(
                            inventory[key],
                            session,
                        )
                    )
                    if sold_out_detail:
                        st.caption(
                            sold_out_detail
                        )

                if not public_read_only:
                    def status_option_label(
                        option: str,
                        effective_status=effective,
                    ) -> str:
                        if option == AUTO:
                            return (
                                "⏱ 自動判定"
                                f"（現在："
                                f"{EFFECTIVE_LABELS[effective_status]}"
                                f"）"
                            )
                        return STORED_STATUS_LABELS[
                            option
                        ]

                    current_index = (
                        STORED_STATUS_ORDER.index(
                            stored
                        )
                        if stored
                        in STORED_STATUS_ORDER
                        else 0
                    )

                    selected = st.selectbox(
                        f"{item_name}/{variant or '通常'} の状態変更",
                        STORED_STATUS_ORDER,
                        index=current_index,
                        format_func=status_option_label,
                        key=(
                            f"{sales_session_id}:"
                            f"{item_id}:"
                            f"{variant}"
                        ),
                        label_visibility="collapsed",
                    )

                    if selected != stored:
                        update_status(
                            sales_session_id,
                            row["item_id"],
                            variant,
                            selected,
                        )
                        st.rerun()

    st.divider()

    if not public_read_only:
        with st.expander("管理・DB確認"):
            if st.button(
                "この物販セッションを"
                "すべて自動判定に戻す"
            ):
                reset_session(
                    sales_session_id
                )
                st.rerun()

            refreshed = (
                get_inventory_for_session(
                    sales_session_id
                )
            )

            debug_rows = []
            for _, row in tour_goods.iterrows():
                key = (
                    row["item_id"],
                    row["variant"],
                )
                info = refreshed[key]
                effective = get_effective_status(
                    info["status"],
                    session,
                    now=now,
                    enable_sales_end=runtime_enable_sales_end,
                )

                debug_rows.append(
                    {
                        "sales_session_id": (
                            sales_session_id
                        ),
                        "item_id": (
                            row["item_id"]
                        ),
                        "item_name": (
                            row["item_name"]
                        ),
                        "variant": (
                            row["variant"]
                        ),
                        "stored_status": (
                            info["status"]
                        ),
                        "effective_status": (
                            effective
                        ),
                        "updated_at": (
                            info["updated_at"]
                        ),
                        "source_post_id": (
                            info[
                                "source_post_id"
                            ]
                        ),
                        "source_post_url": (
                            info[
                                "source_post_url"
                            ]
                        ),
                        "sold_out_at": (
                            info.get(
                                "sold_out_at"
                            )
                        ),
                    }
                )

            st.dataframe(
                pd.DataFrame(debug_rows),
                use_container_width=True,
                hide_index=True,
            )


render_inventory()
