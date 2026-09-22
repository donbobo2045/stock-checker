from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
import re
import unicodedata

import pandas as pd


@dataclass
class ParsedSoldOutItem:
    item_id: str
    item_name: str
    variant: str
    status: str = "SOLD_OUT"


@dataclass
class ParseResult:
    is_relevant: bool
    reason: str
    tour_id: str | None = None
    sales_session_id: str | None = None
    date: str | None = None
    venue: str | None = None
    items: list[ParsedSoldOutItem] | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.items is None:
            data["items"] = []
        return data


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def compact_text(value: object) -> str:
    return normalize_text(value).replace(" ", "")


def normalize_item_text(value: object) -> str:
    """Normalize item text for matching while preserving meaningful punctuation like vol.30."""
    text = normalize_text(value)
    text = re.sub(r"^[・\-–—●○■□◆◇★☆※\s]+", "", text)
    text = re.sub(r"\s*[（(][^()（）]+[）)]\s*$", "", text)
    for prefix in ["ICEx FRESHest!!", "FRESHest!!", "ICEx"]:
        text = re.sub(rf"^{re.escape(prefix)}\s*", "", text, flags=re.I)
    return compact_text(text).lower()


def normalize_variant(value: object) -> str:
    return compact_text(value).lower()


def normalize_for_fuzzy(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).lower()
    return re.sub(r"[^a-z0-9ぁ-んァ-ヶ一-龯]+", "", text)


TOUR_FUZZY_THRESHOLD = 0.72
TOUR_FUZZY_MARGIN = 0.08


class SoldOutPostParser:
    def __init__(
        self,
        goods: pd.DataFrame,
        events: pd.DataFrame,
        item_aliases: pd.DataFrame | None = None,
        sales_session_items: pd.DataFrame | None = None,
    ):
        self.goods = goods.fillna("").copy()
        self.events = events.fillna("").copy()
        self.goods["variant"] = self.goods["variant"].map(normalize_text)

        if item_aliases is None:
            item_aliases = pd.DataFrame(columns=["alias", "item_id", "notes"])
        self.item_aliases_df = item_aliases.fillna("").copy()

        if sales_session_items is None:
            sales_session_items = pd.DataFrame(
                columns=["sales_session_id", "item_id", "variant"]
            )
        self.sales_session_items_df = sales_session_items.fillna("").copy()

        self.item_aliases = self._build_item_aliases()
        self.variant_aliases = self._build_variant_aliases()

    @classmethod
    def from_csv(
        cls,
        goods_path: str | Path,
        events_path: str | Path,
        aliases_path: str | Path | None = None,
        session_items_path: str | Path | None = None,
    ) -> "SoldOutPostParser":
        goods_path = Path(goods_path)
        events_path = Path(events_path)

        goods = pd.read_csv(goods_path, dtype=str, keep_default_na=False)
        events = pd.read_csv(events_path, dtype=str, keep_default_na=False)

        if aliases_path is None:
            candidate = goods_path.with_name("item_aliases.csv")
            aliases_path = candidate if candidate.exists() else None

        aliases = None
        if aliases_path is not None:
            aliases = pd.read_csv(
                aliases_path,
                dtype=str,
                keep_default_na=False,
            )

        if session_items_path is None:
            candidate = goods_path.with_name("sales_session_items.csv")
            session_items_path = candidate if candidate.exists() else None

        session_items = None
        if session_items_path is not None:
            session_items = pd.read_csv(
                session_items_path,
                dtype=str,
                keep_default_na=False,
            )

        return cls(goods, events, aliases, session_items)

    def _build_item_aliases(self) -> dict[str, set[str]]:
        """Build normalized alias -> set[item_id]. Duplicate aliases are allowed."""
        aliases: dict[str, set[str]] = {}
        known_ids = set(self.goods["item_id"])

        def add(alias: str, item_id: str) -> None:
            normalized = normalize_item_text(alias)
            if not normalized:
                return
            aliases.setdefault(normalized, set()).add(item_id)

        # Official item names always work as aliases.
        for _, row in self.goods.drop_duplicates("item_id").iterrows():
            add(row["item_name"], row["item_id"])

        # External alias master. Same alias may intentionally point to multiple products.
        required = {"alias", "item_id"}
        if not self.item_aliases_df.empty:
            missing = required - set(self.item_aliases_df.columns)
            if missing:
                raise ValueError(
                    "item_aliases.csv に必要な列がありません: "
                    + ", ".join(sorted(missing))
                )

            for _, row in self.item_aliases_df.iterrows():
                item_id = normalize_text(row["item_id"])
                if item_id not in known_ids:
                    raise ValueError(
                        f"item_aliases.csv に goods.csv に存在しない item_id があります: {item_id}"
                    )
                add(row["alias"], item_id)

        return aliases

    def _build_variant_aliases(self) -> dict[str, str]:
        variants = {
            normalize_text(v)
            for v in self.goods["variant"]
            if normalize_text(v)
        }
        aliases = {normalize_variant(v): v for v in variants}

        surname_map = {
            "志賀": "志賀李玖",
            "中村": "中村旺太郎",
            "阿久根": "阿久根温世",
            "千田": "千田波空斗",
            "筒井": "筒井俊旭",
            "山本": "山本龍人",
            "竹野": "竹野世梛",
            "八神": "八神遼介",
        }
        for short, full in surname_map.items():
            if full in variants:
                aliases[normalize_variant(short)] = full

        return aliases

    def parse(self, text: str) -> ParseResult:
        raw_text = text
        normalized = normalize_text(text)

        # まず対象ツアーかを判定する。
        # 「【完売情報】」は投稿上の見出しにすぎないため必須条件にはしない。
        tour_id = self._detect_tour_id(raw_text)
        if not tour_id:
            return ParseResult(False, "対象ツアーを特定できない")

        # 完売投稿として扱うための必須表現。
        if "本日分完売" not in normalized:
            return ParseResult(
                False,
                "本日分完売の明示がないため対象外",
                tour_id=tour_id,
            )

        event = self._detect_event(normalized, tour_id)
        if event is None:
            return ParseResult(False, "公演を特定できない", tour_id=tour_id)

        lines = self._extract_item_lines(raw_text)
        if not lines:
            return self._failure("完売商品を抽出できない", tour_id, event)

        parsed: list[ParsedSoldOutItem] = []
        pending: tuple[str, str] | None = None

        for line in lines:
            s = normalize_text(line)

            # Separate-line variant pattern, e.g. 種類：竹野世梛 / サイズ：M
            m = re.match(r"^(種類|サイズ)\s*[:：]\s*(.+)$", s, flags=re.I)
            if m and pending is not None:
                item_id, official_name = pending
                variant = self.variant_aliases.get(normalize_variant(m.group(2)))
                if not variant:
                    return self._failure(
                        f"variantを特定できない: {m.group(2)}", tour_id, event
                    )
                allowed = set(
                    self.goods.loc[self.goods["item_id"] == item_id, "variant"]
                )
                if variant not in allowed:
                    return self._failure(
                        f"variantを特定できない: {m.group(2)}", tour_id, event
                    )
                parsed.append(ParsedSoldOutItem(item_id, official_name, variant))
                pending = None
                continue

            if not s.startswith("・"):
                continue

            item_text = re.sub(r"^・\s*", "", s)
            item_text, inline_variant = self._split_inline_variant(item_text)
            item_id, match_error = self._match_item_id(item_text)

            if not item_id:
                return self._failure(match_error or f"商品を特定できない: {item_text}", tour_id, event)

            official_name = self.goods.loc[
                self.goods["item_id"] == item_id, "item_name"
            ].iloc[0]
            allowed = set(
                self.goods.loc[self.goods["item_id"] == item_id, "variant"]
            )

            if inline_variant:
                variant = self.variant_aliases.get(normalize_variant(inline_variant))
                if not variant or variant not in allowed:
                    return self._failure(
                        f"variantを特定できない: {inline_variant}", tour_id, event
                    )
                parsed.append(ParsedSoldOutItem(item_id, official_name, variant))
                pending = None
            elif allowed == {""}:
                parsed.append(ParsedSoldOutItem(item_id, official_name, ""))
                pending = None
            else:
                pending = (item_id, official_name)

        if pending is not None:
            return self._failure(
                f"variantが必要な商品なのに指定がない: {pending[1]}",
                tour_id,
                event,
            )

        if not parsed:
            return self._failure("完売商品を抽出できない", tour_id, event)

        # If a sales-session catalog exists, never apply a SOLD_OUT update
        # to an item that is not scheduled for sale in that session.
        if not self.sales_session_items_df.empty:
            required = {"sales_session_id", "item_id", "variant"}
            missing = required - set(self.sales_session_items_df.columns)
            if missing:
                raise ValueError(
                    "sales_session_items.csv に必要な列がありません: "
                    + ", ".join(sorted(missing))
                )

            available_rows = self.sales_session_items_df[
                self.sales_session_items_df["sales_session_id"]
                == event["sales_session_id"]
            ]
            available_keys = {
                (normalize_text(row["item_id"]), normalize_text(row["variant"]))
                for _, row in available_rows.iterrows()
            }

            for item in parsed:
                if (item.item_id, item.variant) not in available_keys:
                    return self._failure(
                        "この物販セッションの販売予定商品ではありません: "
                        f"{item.item_name}"
                        + (f" / {item.variant}" if item.variant else ""),
                        tour_id,
                        event,
                    )

        return ParseResult(
            True,
            "完売情報として解析成功",
            tour_id=tour_id,
            sales_session_id=event["sales_session_id"],
            date=event["date"],
            venue=event["venue"],
            items=parsed,
        )

    def _failure(self, reason: str, tour_id: str, event: dict) -> ParseResult:
        return ParseResult(
            False,
            reason,
            tour_id=tour_id,
            sales_session_id=event["sales_session_id"],
            date=event["date"],
            venue=event["venue"],
        )

    def _detect_tour_id(self, text: str) -> str | None:
        """
        公式名の正規化一致を優先し、失敗時だけ安全条件付きで類似一致する。
        """
        compact = compact_text(text).replace("''", "").replace('"', "").lower()
        tour_ids = sorted(set(self.goods["tour_id"]))

        # 1) Exact / normalized substring match.
        for tour_id in tour_ids:
            names = set(
                self.goods.loc[self.goods["tour_id"] == tour_id, "tour_name"]
            )
            for name in names:
                core = (
                    compact_text(name)
                    .replace("''", "")
                    .replace('"', "")
                    .lower()
                )
                if core and core in compact:
                    return tour_id

        # 2) Fuzzy matching is allowed only for posts that still say ICEx.
        if "icex" not in compact:
            return None

        # Compare title-like lines, not the entire post.
        candidate_lines = []
        for raw_line in str(text).splitlines():
            line = normalize_text(raw_line)
            lower = line.lower()
            if not line:
                continue
            if "icex" in lower and (
                "tour" in lower
                or "concert" in lower
                or "fresh" in lower
            ):
                candidate_lines.append(line)

        if not candidate_lines:
            return None

        scored: list[tuple[float, str]] = []

        for tour_id in tour_ids:
            names = set(
                self.goods.loc[self.goods["tour_id"] == tour_id, "tour_name"]
            )
            best = 0.0

            for official_name in names:
                official_norm = normalize_for_fuzzy(official_name)
                official_years = set(
                    re.findall(r"\b20\d{2}\b", official_name)
                )

                for candidate in candidate_lines:
                    candidate_norm = normalize_for_fuzzy(candidate)
                    candidate_years = set(
                        re.findall(r"\b20\d{2}\b", candidate)
                    )

                    # If both explicitly state a year, it must be the same year.
                    if (
                        official_years
                        and candidate_years
                        and official_years.isdisjoint(candidate_years)
                    ):
                        continue

                    score = SequenceMatcher(
                        None,
                        official_norm,
                        candidate_norm,
                    ).ratio()
                    best = max(best, score)

            scored.append((best, tour_id))

        scored.sort(reverse=True)

        if not scored or scored[0][0] < TOUR_FUZZY_THRESHOLD:
            return None

        # If two registered tours are similarly plausible, do not guess.
        if (
            len(scored) >= 2
            and scored[1][0] >= TOUR_FUZZY_THRESHOLD
            and (scored[0][0] - scored[1][0]) < TOUR_FUZZY_MARGIN
        ):
            return None

        return scored[0][1]

    def _detect_event(self, text: str, tour_id: str) -> dict | None:
        """
        公演特定ルール：

        1. 最低でも開催地域（東京/大阪/愛知/福岡など）または正式会場名が必要
        2. 正式会場名があれば、その会場の候補に絞る
        3. 会場名がなくても都道府県名があれば、その地域の候補に絞る
        4. Day1 / Day2 / 1日目 / 2日目 がある場合は、日付より優先する
        5. Day表記がない場合のみ、明示日付で絞る
        6. 同一地域に複数開催日があり、Day/日付のどちらもない場合は特定しない
        7. 地域情報なしで Day2 / 2日目 だけ書かれていても自動判定しない

        例：
          8/29 福岡 Day2
        のように日付とDay表記が矛盾していても、
        福岡の2日目が一意に特定できれば Day2 を優先する。
        """
        candidates = self.events[
            self.events["tour_id"] == tour_id
        ].copy()

        compact_post = compact_text(text)

        # ---- Geographic scope is mandatory ----
        geographic_match_found = False

        # 1) Full venue name match first.
        venue_rows = []
        for _, row in candidates.iterrows():
            venue = compact_text(row["venue"])
            if venue and venue in compact_post:
                venue_rows.append(row)

        if venue_rows:
            candidates = pd.DataFrame(venue_rows)
            geographic_match_found = True
        else:
            # 2) Prefecture / region match such as 東京・大阪・愛知・福岡.
            prefecture_rows = []
            for _, row in candidates.iterrows():
                prefecture = compact_text(row["prefecture"])
                if prefecture and prefecture in compact_post:
                    prefecture_rows.append(row)

            if prefecture_rows:
                candidates = pd.DataFrame(prefecture_rows)
                geographic_match_found = True

        # Region/venue is required. Never interpret "2日目" globally.
        if not geographic_match_found:
            return None

        sessions = (
            candidates[["date", "sales_session_id"]]
            .drop_duplicates()
            .sort_values("date")
            .reset_index(drop=True)
        )

        # ---- Day1 / Day2 / 1日目 / 2日目 has priority over calendar date ----
        day_no = self._extract_day_number(text)

        if day_no is not None:
            if 1 <= day_no <= len(sessions):
                sid = sessions.iloc[day_no - 1]["sales_session_id"]
                matched = candidates[
                    candidates["sales_session_id"] == sid
                ]
                if not matched.empty:
                    return matched.iloc[0].to_dict()

            # A Day number was explicitly written but does not exist
            # for this venue/region, so do not fall back to the date.
            return None

        # ---- No Day label: use explicit calendar date ----
        date_match = re.search(
            r"(?<!\d)(\d{1,2})/(\d{1,2})(?:\([^)]*\)|（[^）]*）)?",
            text,
        )

        if date_match:
            month, day = map(int, date_match.groups())
            matching = []

            for _, row in candidates.iterrows():
                dt = datetime.strptime(row["date"], "%Y-%m-%d")
                if dt.month == month and dt.day == day:
                    matching.append(row)

            if matching:
                # Same-day 1部/2部 share sales_session_id in this design.
                return matching[0].to_dict()

            # A date was explicitly written but doesn't match this region.
            return None

        # ---- No Day/date given ----
        # Region/venue alone is acceptable only when exactly one sales session remains.
        if len(sessions) == 1 and not candidates.empty:
            return candidates.iloc[0].to_dict()

        # Multiple dates remain within the same region/venue, so do not guess.
        return None

    def _extract_day_number(self, text: str) -> int | None:
        normalized = unicodedata.normalize("NFKC", str(text))

        for pattern in [
            r"\bDay\s*([1-9]\d*)\b",
            r"([1-9]\d*)\s*日(?:目|め)",
        ]:
            match = re.search(pattern, normalized, flags=re.I)
            if match:
                return int(match.group(1))

        japanese_days = {
            "一日目": 1,
            "二日目": 2,
            "三日目": 3,
            "一日め": 1,
            "二日め": 2,
            "三日め": 3,
        }
        for token, number in japanese_days.items():
            if token in normalized:
                return number

        return None

    def _extract_item_lines(self, text: str) -> list[str]:
        """
        完売対象の商品行を抽出する。

        「【完売情報】」は任意。
        見出しがある場合はその後ろを、ない場合は投稿全体を対象にし、
        「本日分完売」より前の「・商品名」および「種類：/サイズ：」行だけを
        後段の解析対象として返す。
        """
        if "【完売情報】" in text:
            target = text.split("【完売情報】", 1)[1]
        else:
            target = text

        for stop in ["本日分完売", "ありがとうございます"]:
            if stop in target:
                target = target.split(stop, 1)[0]

        extracted = []
        for line in target.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("・") or re.match(
                r"^(種類|サイズ)\s*[:：]",
                stripped,
                flags=re.I,
            ):
                extracted.append(stripped)

        return extracted

    def _split_inline_variant(self, text: str) -> tuple[str, str | None]:
        m = re.match(
            r"^(.*?)\s*[（(]\s*([^()（）]+?)\s*[）)]\s*$",
            normalize_text(text),
        )
        if m:
            return m.group(1), m.group(2)
        return text, None

    def _match_item_id(self, item_text: str) -> tuple[str | None, str | None]:
        """
        Matching order:
        1) normalized exact official/alias match
        2) controlled unique substring/suffix match
        3) if multiple candidates remain, stop as ambiguous
        """
        normalized = normalize_item_text(item_text)

        exact = self.item_aliases.get(normalized, set())
        if len(exact) == 1:
            return next(iter(exact)), None
        if len(exact) > 1:
            return None, self._ambiguous_reason(item_text, exact)

        candidates: set[str] = set()
        for alias, item_ids in self.item_aliases.items():
            if not alias:
                continue
            if normalized.endswith(alias) or alias.endswith(normalized):
                candidates.update(item_ids)

        if len(candidates) == 1:
            return next(iter(candidates)), None
        if len(candidates) > 1:
            return None, self._ambiguous_reason(item_text, candidates)

        return None, f"商品を特定できない: {item_text}"

    def _ambiguous_reason(self, item_text: str, item_ids: set[str]) -> str:
        labels = []
        for item_id in sorted(item_ids):
            name = self.goods.loc[
                self.goods["item_id"] == item_id, "item_name"
            ].iloc[0]
            labels.append(f"{name} ({item_id})")
        return (
            f"商品表記が曖昧で複数候補があります: {item_text} -> "
            + " / ".join(labels)
        )
