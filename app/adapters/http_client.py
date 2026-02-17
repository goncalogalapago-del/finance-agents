import time
from collections.abc import Mapping
from typing import Any, Optional

import httpx


class RetryRateLimitedHttpClient:
    """Small shared client wrapper for provider adapters."""

    def __init__(
        self,
        *,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        requests_per_second: float = 5.0,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._min_interval = 0.0 if requests_per_second <= 0 else 1.0 / requests_per_second
        self._last_request_at: Optional[float] = None
        self._client = httpx.Client(timeout=timeout_seconds)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            self._apply_rate_limit()
            try:
                response = self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                )
                if response.status_code >= 500:
                    response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError):
                attempt += 1
                if attempt > self._max_retries:
                    raise
                time.sleep(self._backoff_seconds * attempt)

    def _apply_rate_limit(self) -> None:
        if self._last_request_at is None or self._min_interval == 0:
            self._last_request_at = time.monotonic()
            return

        now = time.monotonic()
        elapsed = now - self._last_request_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def close(self) -> None:
        self._client.close()
