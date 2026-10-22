"""Explicit-resource SEC client with shared process-local fair-access throttling."""

import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx


class SecAccessError(RuntimeError):
    """Access failed without bypassing SEC denial or timing requirements."""


class SecThrottle:
    """One process-local serialized request budget; share across clients/workers."""

    def __init__(
        self,
        *,
        interval: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if interval < 0.11:
            raise ValueError("SEC request interval must stay below 10 requests per second")
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            delay = max(0.0, self._next - self.clock())
            if delay:
                self.sleep(delay)
            self._next = self.clock() + self.interval


SHARED_SEC_THROTTLE = SecThrottle()


class SecFilingClient:
    """No discovery/crawler: request one validated Archives filing URL at a time."""

    def __init__(
        self,
        *,
        user_agent: str,
        client: httpx.Client | None = None,
        throttle: SecThrottle = SHARED_SEC_THROTTLE,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_attempts: int = 3,
        max_retry_after: float = 120,
    ) -> None:
        if not re.fullmatch(r"[^\r\n]+\s+[^\s@]+@[^\s@]+\.[^\s@]+", user_agent):
            raise ValueError("configure a declared SEC User-Agent with a real contact email")
        domain = user_agent.rsplit("@", 1)[-1].lower()
        if client is None and (
            domain.endswith((".invalid", ".test", ".example"))
            or domain in {"example.com", "example.org", "example.net"}
        ):
            raise ValueError("live SEC User-Agent cannot use a placeholder contact")
        if not 1 <= max_attempts <= 5 or not 0 < max_retry_after <= 300:
            raise ValueError("invalid bounded SEC retry configuration")
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)
        self._owns_client = client is None
        self.user_agent, self.throttle, self.sleep = user_agent, throttle, sleep
        self.now, self.max_attempts, self.max_retry_after = now, max_attempts, max_retry_after

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def fetch(self, url: str) -> bytes:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.sec.gov"
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(
                r"/Archives/edgar/data/[0-9]+/[0-9]{18}/[A-Za-z0-9_-]+\.(?:txt|xml)",
                parsed.path,
            )
        ):
            raise ValueError("only explicit SEC Archives filing text/XML URLs are supported")
        for attempt in range(self.max_attempts):
            self.throttle.acquire()
            try:
                response = self.client.get(
                    url, headers={"User-Agent": self.user_agent}, follow_redirects=False
                )
            except httpx.TransportError as exc:
                if attempt + 1 == self.max_attempts:
                    raise SecAccessError("SEC transport retry limit reached") from exc
                self.sleep(2**attempt)
                continue
            if response.status_code == 200:
                return response.content
            if response.status_code not in (429, 500, 502, 503, 504):
                raise SecAccessError(f"SEC access refused/failed: HTTP {response.status_code}")
            if attempt + 1 == self.max_attempts:
                raise SecAccessError("SEC transient retry limit reached")
            delay = float(2**attempt)
            if raw := response.headers.get("Retry-After"):
                try:
                    if re.fullmatch(r"[0-9]+", raw):
                        delay = max(delay, float(raw))
                    else:
                        until = parsedate_to_datetime(raw)
                        if until.tzinfo is None:
                            raise ValueError
                        delay = max(delay, (until - self.now()).total_seconds())
                except (ValueError, TypeError, OverflowError) as exc:
                    raise SecAccessError(
                        "invalid SEC Retry-After; refusing an early retry"
                    ) from exc
            if delay > self.max_retry_after:
                raise SecAccessError("SEC Retry-After exceeds bounded wait; retry later")
            self.sleep(delay)
        raise SecAccessError("SEC retry limit reached")
