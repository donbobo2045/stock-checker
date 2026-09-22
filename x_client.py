from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


API_BASE_URL = "https://api.x.com/2"


class XApiError(RuntimeError):
    """Raised when X API access or response handling fails."""


@dataclass(frozen=True)
class XPost:
    id: str
    text: str
    username: str
    created_at: str | None = None

    @property
    def url(self) -> str:
        return f"https://x.com/{self.username}/status/{self.id}"


class XApiClient:
    def __init__(
        self,
        bearer_token: str,
        *,
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        token = str(bearer_token or "").strip()
        if not token:
            raise ValueError("Bearer Token が空です。")

        self.bearer_token = token
        self.timeout = timeout
        self.session = session or requests.Session()

    def search_recent_posts(
        self,
        query: str,
        *,
        username: str,
        max_results: int = 10,
        start_time: str | None = None,
        end_time: str | None = None,
        since_id: str | None = None,
    ) -> list[XPost]:
        """
        Search recent X posts with a server-side query.

        Initial event-day reads use start_time + end_time.
        Incremental reads use since_id + end_time because X Recent Search
        does not allow start_time and since_id together.
        """
        normalized_query = str(query or "").strip()
        if not normalized_query:
            raise ValueError("X検索クエリが空です。")

        normalized_start = str(start_time or "").strip() or None
        normalized_end = str(end_time or "").strip() or None
        normalized_since = str(since_id or "").strip() or None

        if normalized_start and normalized_since:
            raise ValueError(
                "start_time と since_id は同時に指定できません。"
            )
        if normalized_since and not normalized_since.isdigit():
            raise ValueError("since_id は数値のPost IDで指定してください。")

        username = self._normalize_username(username)
        count = max(10, min(int(max_results), 100))

        params: dict[str, Any] = {
            "query": normalized_query,
            "max_results": count,
            "tweet.fields": "created_at",
        }
        if normalized_start:
            params["start_time"] = normalized_start
        if normalized_end:
            params["end_time"] = normalized_end
        if normalized_since:
            params["since_id"] = normalized_since

        payload = self._get(
            "/tweets/search/recent",
            params=params,
        )

        posts: list[XPost] = []
        for row in payload.get("data") or []:
            if not isinstance(row, dict):
                continue

            post_id = str(row.get("id") or "").strip()
            text = str(row.get("text") or "")
            if not post_id or not text:
                continue

            created_at = row.get("created_at")
            posts.append(
                XPost(
                    id=post_id,
                    text=text,
                    username=username,
                    created_at=(
                        str(created_at)
                        if created_at is not None
                        else None
                    ),
                )
            )

        return posts

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{API_BASE_URL}{path}"

        try:
            response = self.session.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.bearer_token}",
                    "User-Agent": "goods-stock-checker/phase10.2",
                },
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise XApiError(
                "X APIへの接続に失敗しました。"
            ) from exc

        if response.status_code >= 400:
            detail = self._error_detail(response)
            if response.status_code == 401:
                message = (
                    "X APIの認証に失敗しました。"
                    "Bearer Tokenを確認してください。"
                )
            elif response.status_code == 402:
                message = (
                    "X APIのクレジット残高がありません。"
                    "Developer ConsoleでCreditsを追加してください。"
                )
            elif response.status_code == 403:
                message = (
                    "X APIへのアクセスが拒否されました。"
                    "アプリの権限・利用条件を確認してください。"
                )
            elif response.status_code == 429:
                message = (
                    "X APIのレート制限に達しました。"
                    "時間を置いて再試行してください。"
                )
            else:
                message = (
                    f"X APIがHTTP {response.status_code}を返しました。"
                )

            if detail:
                message = f"{message} ({detail})"
            raise XApiError(message)

        try:
            payload = response.json()
        except ValueError as exc:
            raise XApiError(
                "X APIからJSONではない応答が返されました。"
            ) from exc

        if not isinstance(payload, dict):
            raise XApiError(
                "X APIの応答形式を解釈できませんでした。"
            )

        return payload

    @staticmethod
    def _normalize_username(username: str) -> str:
        normalized = str(username or "").strip().lstrip("@")
        if not normalized:
            raise ValueError("Xのユーザー名が空です。")
        return normalized

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""

        if not isinstance(payload, dict):
            return ""

        detail = payload.get("detail")
        if detail:
            return str(detail)

        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                for key in ("detail", "title"):
                    if first.get(key):
                        return str(first[key])

        title = payload.get("title")
        return str(title) if title else ""
