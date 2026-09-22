import requests

from x_client import XApiClient, XApiError


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_search_recent_posts_uses_server_side_query():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "999",
                            "text": "#ICEx\n【完売情報】\n・うちわ（筒井）",
                            "created_at": "2026-09-22T09:00:00.000Z",
                        }
                    ]
                },
            ),
        ]
    )
    client = XApiClient("secret", session=session)

    query = (
        "from:SDE_STARDUSTBIN "
        "(ICEx OR #ICEx) 完売 -is:retweet"
    )
    posts = client.search_recent_posts(
        query,
        username="@SDE_STARDUSTBIN",
        max_results=10,
    )

    assert len(posts) == 1
    assert posts[0].id == "999"
    assert posts[0].username == "SDE_STARDUSTBIN"
    assert posts[0].url == (
        "https://x.com/SDE_STARDUSTBIN/status/999"
    )

    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url.endswith("/tweets/search/recent")
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kwargs["params"]["query"] == query
    assert kwargs["params"]["max_results"] == 10
    assert kwargs["params"]["tweet.fields"] == "created_at"


def test_max_results_is_clamped_to_recent_search_range():
    session = FakeSession(
        [
            FakeResponse(200, {"data": []}),
        ]
    )
    client = XApiClient("secret", session=session)

    client.search_recent_posts(
        "from:SDE_STARDUSTBIN ICEx 完売",
        username="SDE_STARDUSTBIN",
        max_results=1,
    )

    _, kwargs = session.calls[0]
    assert kwargs["params"]["max_results"] == 10


def test_empty_query_is_rejected_before_request():
    session = FakeSession([])
    client = XApiClient("secret", session=session)

    try:
        client.search_recent_posts(
            "   ",
            username="SDE_STARDUSTBIN",
        )
    except ValueError as exc:
        assert "検索クエリが空" in str(exc)
    else:
        raise AssertionError("ValueError was not raised")

    assert session.calls == []


def test_401_becomes_human_readable_error():
    session = FakeSession(
        [
            FakeResponse(
                401,
                {"detail": "Unauthorized"},
            )
        ]
    )
    client = XApiClient("secret", session=session)

    try:
        client.search_recent_posts(
            "from:SDE_STARDUSTBIN ICEx 完売",
            username="SDE_STARDUSTBIN",
        )
    except XApiError as exc:
        assert "認証に失敗" in str(exc)
        assert "Unauthorized" in str(exc)
    else:
        raise AssertionError("XApiError was not raised")


def test_402_becomes_credit_error():
    session = FakeSession(
        [
            FakeResponse(
                402,
                {"detail": "credits depleted"},
            )
        ]
    )
    client = XApiClient("secret", session=session)

    try:
        client.search_recent_posts(
            "from:SDE_STARDUSTBIN ICEx 完売",
            username="SDE_STARDUSTBIN",
        )
    except XApiError as exc:
        assert "クレジット残高がありません" in str(exc)
        assert "credits depleted" in str(exc)
    else:
        raise AssertionError("XApiError was not raised")


def test_network_error_is_wrapped():
    class BrokenSession:
        def get(self, *args, **kwargs):
            raise requests.ConnectionError("boom")

    client = XApiClient(
        "secret",
        session=BrokenSession(),
    )

    try:
        client.search_recent_posts(
            "from:SDE_STARDUSTBIN ICEx 完売",
            username="SDE_STARDUSTBIN",
        )
    except XApiError as exc:
        assert "接続に失敗" in str(exc)
    else:
        raise AssertionError("XApiError was not raised")



def test_search_recent_posts_accepts_event_day_window():
    session = FakeSession(
        [
            FakeResponse(200, {"data": []}),
        ]
    )
    client = XApiClient("secret", session=session)

    client.search_recent_posts(
        "from:SDE_STARDUSTBIN ICEx 完売",
        username="SDE_STARDUSTBIN",
        start_time="2026-09-18T15:00:00Z",
        end_time="2026-09-19T06:00:00Z",
    )

    _, kwargs = session.calls[0]
    assert kwargs["params"]["start_time"] == (
        "2026-09-18T15:00:00Z"
    )
    assert kwargs["params"]["end_time"] == (
        "2026-09-19T06:00:00Z"
    )
    assert "since_id" not in kwargs["params"]


def test_search_recent_posts_accepts_since_id_increment():
    session = FakeSession(
        [
            FakeResponse(200, {"data": []}),
        ]
    )
    client = XApiClient("secret", session=session)

    client.search_recent_posts(
        "from:SDE_STARDUSTBIN ICEx 完売",
        username="SDE_STARDUSTBIN",
        since_id="123456789",
        end_time="2026-09-19T09:00:00Z",
    )

    _, kwargs = session.calls[0]
    assert kwargs["params"]["since_id"] == "123456789"
    assert kwargs["params"]["end_time"] == (
        "2026-09-19T09:00:00Z"
    )
    assert "start_time" not in kwargs["params"]


def test_search_recent_posts_rejects_start_time_with_since_id():
    session = FakeSession([])
    client = XApiClient("secret", session=session)

    try:
        client.search_recent_posts(
            "from:SDE_STARDUSTBIN ICEx 完売",
            username="SDE_STARDUSTBIN",
            start_time="2026-09-18T15:00:00Z",
            since_id="123456789",
        )
    except ValueError as exc:
        assert "同時に指定できません" in str(exc)
    else:
        raise AssertionError("ValueError was not raised")

    assert session.calls == []
