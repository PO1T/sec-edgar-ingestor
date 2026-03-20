from __future__ import annotations

import json
import time

import httpx


class SecClientError(RuntimeError):
    """Raised when the SEC client cannot complete a request."""


class SecNotFoundError(SecClientError):
    """Raised when an SEC resource is not found."""


class SecClient:
    def __init__(
        self,
        user_agent: str,
        *,
        timeout_seconds: float,
        requests_per_second: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            transport=transport,
            headers={
                "User-Agent": user_agent,
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        self._request_interval = 1.0 / requests_per_second
        self._last_request_started_at = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SecClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_bytes(self, url: str, *, allow_404: bool = False) -> bytes | None:
        response = self._request(url, allow_404=allow_404)
        if response is None:
            return None
        return response.content

    def get_text(self, url: str, *, allow_404: bool = False) -> str | None:
        response = self._request(url, allow_404=allow_404)
        if response is None:
            return None
        return response.text

    def get_json(self, url: str, *, allow_404: bool = False) -> dict[str, object] | None:
        payload = self.get_text(url, allow_404=allow_404)
        if payload is None:
            return None
        return json.loads(payload)

    def _request(self, url: str, *, allow_404: bool) -> httpx.Response | None:
        last_error: Exception | None = None
        for attempt in range(3):
            self._wait_for_slot()
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == 2:
                    break
                time.sleep(0.5 * (attempt + 1))
                continue

            if response.status_code == 404 and allow_404:
                return None
            if response.status_code == 404:
                raise SecNotFoundError(f"SEC resource not found: {url}")

            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = SecClientError(
                    f"Transient SEC response {response.status_code} for {url}"
                )
                if attempt == 2:
                    break
                time.sleep(0.5 * (attempt + 1))
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise SecClientError(
                    f"Unexpected SEC response {response.status_code} for {url}"
                ) from exc

            return response

        if allow_404 and isinstance(last_error, SecNotFoundError):
            return None
        raise SecClientError(f"Unable to fetch SEC resource: {url}") from last_error

    def _wait_for_slot(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_started_at
        if elapsed < self._request_interval:
            time.sleep(self._request_interval - elapsed)
        self._last_request_started_at = time.monotonic()
