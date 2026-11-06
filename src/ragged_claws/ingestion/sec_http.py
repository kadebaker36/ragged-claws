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


class SecBoundedAccessError(SecAccessError):
    """Safe status with bounded response bytes for raw capture, never header/contact text."""

    def __init__(self, reason: str, content: bytes = b"", status: int | None = None) -> None:
        super().__init__(reason)
        self.content = content
        self.status = status


def fetch_watch_resource(client: SecFilingClient, url: str, *, max_bytes: int) -> bytes:
    """Narrow one-attempt watch boundary using the existing client/contact/throttle.

    The historical client's fetch/retry contract is unchanged. Only daily master indexes and
    literal complete-submission index paths are allowed here. No fallback or redirect.
    """
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.sec.gov"
        or parsed.query
        or parsed.fragment
        or re.fullmatch(
            r"/Archives/edgar/(?:daily-index/[0-9]{4}/QTR[1-4]/master\.[0-9]{8}\.idx"
            r"|data/[0-9]{1,10}/[0-9]{10}-[0-9]{2}-[0-9]{6}\.txt)",
            parsed.path,
        )
        is None
    ):
        raise ValueError("unsupported explicit SEC watch resource")
    if not 1 <= max_bytes <= 5_000_000:
        raise ValueError("invalid SEC watch response bound")
    if client.throttle.interval < 1:
        raise ValueError("watch requires serial cadence of at least one second")
    client.throttle.acquire()
    started = time.monotonic()
    content = bytearray()
    status = None
    try:
        with client.client.stream(
            "GET",
            url,
            headers={"User-Agent": client.user_agent, "Accept-Encoding": "identity"},
            follow_redirects=False,
            timeout=10,
        ) as response:
            status = response.status_code
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise SecBoundedAccessError("unsupported_content_encoding", status=status)
            for chunk in response.iter_bytes():
                content.extend(chunk[: max_bytes + 1 - len(content)])
                if len(content) > max_bytes:
                    raise SecBoundedAccessError("response_size_bound", bytes(content), status)
                if time.monotonic() - started > 30:
                    raise SecBoundedAccessError("response_deadline", bytes(content), status)
            if status != 200:
                raise SecBoundedAccessError("non200_response", bytes(content), status)
    except httpx.TransportError:
        raise SecBoundedAccessError("transport_failure", bytes(content), status) from None
    return bytes(content)
