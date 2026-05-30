"""HTTP transport for the ingestion API.

Wraps ``httpx.AsyncClient`` with a hand-rolled retry policy. Constants
are module-level so tests can monkey-patch them down to zero and skip
the real waiting.

Retry policy:
- 3 attempts total
- Retry on 5xx and any ``httpx.HTTPError`` (timeouts, conn refused, etc.)
- Do **not** retry 4xx - that's a client bug; drop the batch, log a warning
- Backoff before retry N: ``_BACKOFF_BASE * 2**N + uniform(0, _BACKOFF_MAX_JITTER)``
"""

from __future__ import annotations

import asyncio
import random

import httpx

from retrace._logging import get_logger

_log = get_logger()

_REQUEST_TIMEOUT = 10.0
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5
_BACKOFF_MAX_JITTER = 0.25
_INGEST_PATH = "/v1/ingest"


def _compute_backoff(attempt: int) -> float:
    """Backoff to sleep *before* the next attempt. ``attempt`` is the
    index of the attempt that just failed (0-based)."""
    return _BACKOFF_BASE * (2**attempt) + random.uniform(0, _BACKOFF_MAX_JITTER)


class HttpClient:
    """Async HTTP client for ``POST /v1/ingest``.

    Pass a custom ``transport`` (e.g. ``httpx.ASGITransport(app=...)``)
    to drive the client against an in-process FastAPI app instead of
    the network. Used by the integration test in commit 4.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=_REQUEST_TIMEOUT,
        )

    async def send_traces(self, payload: bytes) -> bool:
        """POST a serialized batch. Returns True on 2xx, False otherwise.

        Retry/drop decisions are logged as warnings; this method never
        raises - observability must not break the caller.
        """
        url = f"{self._endpoint}{_INGEST_PATH}"
        last_status: int | None = None
        last_error: BaseException | None = None

        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._client.post(url, content=payload, headers=self._headers)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    break
                await asyncio.sleep(_compute_backoff(attempt))
                continue

            last_status = resp.status_code
            if 200 <= resp.status_code < 300:
                return True
            if 400 <= resp.status_code < 500:
                # Client bug: don't retry. Truncate body in case it's huge.
                body = resp.text[:200]
                _log.warning(
                    "retrace: dropping batch on %d response: %s", resp.status_code, body
                )
                return False
            # 5xx - retry
            if attempt == _MAX_ATTEMPTS - 1:
                break
            await asyncio.sleep(_compute_backoff(attempt))

        if last_error is not None:
            _log.warning(
                "retrace: dropping batch after %d attempts (network): %s",
                _MAX_ATTEMPTS,
                last_error,
            )
        else:
            _log.warning(
                "retrace: dropping batch after %d attempts (last status %s)",
                _MAX_ATTEMPTS,
                last_status,
            )
        return False

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["HttpClient"]
