"""Offline fair-access and denial behavior; no real contact or network in fixtures."""

from datetime import UTC, datetime

import httpx
import pytest

from ragged_claws.ingestion.sec_http import SecAccessError, SecFilingClient, SecThrottle

URL = "https://www.sec.gov/Archives/edgar/data/70858/000095017024105263/0000950170-24-105263.txt"
FIXTURE_AGENT = "Invented test application fixture-contact@example.invalid"


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def test_user_agent_and_shared_throttle_serialize_multiple_clients() -> None:
    time = FakeTime()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"fixture")

    throttle = SecThrottle(clock=time.clock, sleep=time.sleep)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        clients = [
            SecFilingClient(user_agent=FIXTURE_AGENT, client=http, throttle=throttle)
            for _ in range(2)
        ]
        for client in (*clients, clients[0]):
            assert client.fetch(URL) == b"fixture"
    assert all(request.headers["User-Agent"] == FIXTURE_AGENT for request in requests)
    assert time.sleeps == [0.25, 0.25]


@pytest.mark.parametrize("agent", ["", "research", "research no-contact", "bad\nheader x@y.test"])
def test_live_client_requires_configured_contact(agent: str) -> None:
    with pytest.raises(ValueError, match="User-Agent"):
        SecFilingClient(user_agent=agent)


@pytest.mark.parametrize("status", [403, 404, 301])
def test_denials_and_redirects_are_not_circumvented(status: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, headers={"Location": "https://elsewhere.test"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = SecFilingClient(
            user_agent=FIXTURE_AGENT,
            client=http,
            throttle=SecThrottle(clock=lambda: 0, sleep=lambda _: None),
        )
        with pytest.raises(SecAccessError, match=f"HTTP {status}"):
            client.fetch(URL)
    assert calls == 1


@pytest.mark.parametrize("retry_after,delay", [("4", 4), ("Thu, 22 Oct 2026 22:00:05 GMT", 5)])
def test_transient_retry_respects_retry_after(retry_after: str, delay: float) -> None:
    time = FakeTime()
    statuses = iter([429, 503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        return httpx.Response(status, content=b"fixture", headers={"Retry-After": retry_after})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = SecFilingClient(
            user_agent=FIXTURE_AGENT,
            client=http,
            throttle=SecThrottle(clock=time.clock, sleep=time.sleep),
            sleep=time.sleep,
            now=lambda: datetime(2026, 10, 22, 22, tzinfo=UTC),
        )
        assert client.fetch(URL) == b"fixture"
    assert time.sleeps == [delay, delay]


def test_transient_retries_are_bounded() -> None:
    time = FakeTime()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = SecFilingClient(
            user_agent=FIXTURE_AGENT,
            client=http,
            throttle=SecThrottle(clock=time.clock, sleep=time.sleep),
            sleep=time.sleep,
        )
        with pytest.raises(SecAccessError, match="retry limit"):
            client.fetch(URL)
    assert calls == 3 and time.sleeps == [1, 2]


@pytest.mark.parametrize("header", ["999999", "malformed"])
def test_excessive_or_invalid_retry_after_stops_instead_of_retrying_early(header: str) -> None:
    time = FakeTime()
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, headers={"Retry-After": header}),
        )
    ) as http:
        client = SecFilingClient(
            user_agent=FIXTURE_AGENT,
            client=http,
            sleep=time.sleep,
            throttle=SecThrottle(clock=time.clock, sleep=time.sleep),
        )
        with pytest.raises(SecAccessError, match="Retry-After"):
            client.fetch(URL)
    assert not time.sleeps


@pytest.mark.parametrize(
    "url",
    [
        "http://www.sec.gov/Archives/edgar/data/1/a.xml",
        "https://www.sec.gov.evil.test/Archives/edgar/data/1/a.xml",
        "https://www.sec.gov/cgi-bin/browse-edgar",
        URL + "?crawl=1",
        URL + "#fragment",
    ],
)
def test_client_rejects_non_filing_resources(url: str) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: pytest.fail("invalid URL reached transport"),
            )
        ) as http,
        pytest.raises(ValueError, match="explicit SEC"),
    ):
        SecFilingClient(user_agent=FIXTURE_AGENT, client=http).fetch(url)


def test_throttle_rejects_rate_at_or_above_sec_ceiling() -> None:
    with pytest.raises(ValueError, match="below 10"):
        SecThrottle(interval=0.1)


def test_live_client_rejects_placeholder_contact_before_transport() -> None:
    with pytest.raises(ValueError, match="placeholder"):
        SecFilingClient(user_agent=FIXTURE_AGENT)


def test_transport_failures_use_bounded_backoff() -> None:
    time = FakeTime()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("invented transport failure")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = SecFilingClient(
            user_agent=FIXTURE_AGENT,
            client=http,
            sleep=time.sleep,
            throttle=SecThrottle(clock=time.clock, sleep=time.sleep),
        )
        with pytest.raises(SecAccessError, match="transport retry limit"):
            client.fetch(URL)
    assert calls == 3 and time.sleeps == [1, 2]
