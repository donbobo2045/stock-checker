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


def test_get_recent_posts_resolves_username_then_fetches_timeline():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "data": {
                        "id": "12345",
                        "username": "SDE_STARDUSTBIN",
                    }
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "999",
                            "text": "【完売情報】 テスト",
                            "created_at": "2026-09-22T09:00:00.000Z",
                        }
                    ]
                },
            ),
        ]
    )
    client = XApiClient("secret", session=session)

    posts = client.get_recent_posts(
        "@SDE_STARDUSTBIN",
        max_results=10,
    )

    assert len(posts) == 1
    assert posts[0].id == "999"
    assert posts[0].username == "SDE_STARDUSTBIN"
    assert posts[0].url == (
        "https://x.com/SDE_STARDUSTBIN/status/999"
    )

    first_url, first_kwargs = session.calls[0]
    assert first_url.endswith(
        "/users/by/username/SDE_STARDUSTBIN"
    )
    assert first_kwargs["headers"]["Authorization"] == (
        "Bearer secret"
    )

    second_url, second_kwargs = session.calls[1]
    assert second_url.endswith("/users/12345/tweets")
    assert second_kwargs["params"]["max_results"] == 10
    assert second_kwargs["params"]["tweet.fields"] == "created_at"


def test_max_results_is_clamped_to_x_api_range():
    session = FakeSession(
        [
            FakeResponse(200, {"data": {"id": "12345"}}),
            FakeResponse(200, {"data": []}),
        ]
    )
    client = XApiClient("secret", session=session)

    client.get_recent_posts("SDE_STARDUSTBIN", max_results=1)

    _, kwargs = session.calls[1]
    assert kwargs["params"]["max_results"] == 5


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
        client.get_user_by_username("SDE_STARDUSTBIN")
    except XApiError as exc:
        assert "認証に失敗" in str(exc)
        assert "Unauthorized" in str(exc)
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
        client.get_user_by_username("SDE_STARDUSTBIN")
    except XApiError as exc:
        assert "接続に失敗" in str(exc)
    else:
        raise AssertionError("XApiError was not raised")
