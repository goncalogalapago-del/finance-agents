import httpx
import pytest

from app.adapters.http_client import RetryRateLimitedHttpClient


def test_request_retries_request_error_and_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RetryRateLimitedHttpClient(max_retries=2, backoff_seconds=0.1, requests_per_second=0)
    attempts = {"count": 0}
    sleeps: list[float] = []

    def _fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        attempts["count"] += 1
        request = httpx.Request(method, url)
        if attempts["count"] == 1:
            raise httpx.RequestError("temporary error", request=request)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(client._client, "request", _fake_request)
    monkeypatch.setattr(
        "app.adapters.http_client.time.sleep", lambda seconds: sleeps.append(seconds)
    )

    response = client.request("GET", "https://example.com")
    client.close()

    assert response.status_code == 200
    assert attempts["count"] == 2
    assert sleeps == [0.1]


def test_request_raises_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RetryRateLimitedHttpClient(max_retries=2, backoff_seconds=0.1, requests_per_second=0)
    attempts = {"count": 0}
    sleeps: list[float] = []

    def _always_fail(method: str, url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        attempts["count"] += 1
        raise httpx.RequestError("network down", request=httpx.Request(method, url))

    monkeypatch.setattr(client._client, "request", _always_fail)
    monkeypatch.setattr(
        "app.adapters.http_client.time.sleep", lambda seconds: sleeps.append(seconds)
    )

    with pytest.raises(httpx.RequestError, match="network down"):
        client.request("GET", "https://example.com")
    client.close()

    assert attempts["count"] == 3
    assert sleeps == [0.1, 0.2]


def test_apply_rate_limit_sleeps_for_remaining_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RetryRateLimitedHttpClient(requests_per_second=2.0)
    sleeps: list[float] = []
    monotonic_values = iter([10.0, 10.2, 10.7])

    monkeypatch.setattr(
        "app.adapters.http_client.time.monotonic", lambda: next(monotonic_values)
    )
    monkeypatch.setattr(
        "app.adapters.http_client.time.sleep", lambda seconds: sleeps.append(seconds)
    )

    client._apply_rate_limit()
    client._apply_rate_limit()
    client.close()

    assert sleeps == [pytest.approx(0.3)]
    assert client._last_request_at == 10.7
