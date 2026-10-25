"""Invented transport/agreements only. Never loads credentials or calls a live provider."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from ragged_claws.ingestion.quiver_access import (
    MAX_BODY_BYTES,
    MAX_HEADER_BYTES,
    QuiverAccessReview,
    retrieve_quiver,
)
from ragged_claws.ingestion.quiver_parser import QuiverError

TOKEN = "INVENTED-STREAM-TOKEN"
URL = "https://api.quiverquant.com/beta/live/govcontractsall?page=1&page_size=1"
NOW = datetime(2026, 10, 25, tzinfo=UTC)


def synthetic_review() -> QuiverAccessReview:
    """An invented fixture review, never an attestation about the user's actual agreement."""
    return QuiverAccessReview(
        agreement_sha256="1" * 64,
        reviewed_at=NOW - timedelta(days=1),
        entitled_endpoints=("contracts",),
        local_raw_retention_permitted=True,
        local_derived_retention_permitted=True,
        root_is_not_synced_or_shared=True,
    )


class TrackedStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes | Exception]) -> None:
        self.chunks = chunks
        self.consumed = 0
        self.closed = 0

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.chunks:
            self.consumed += 1
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self) -> None:
        self.closed += 1


class Rig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.stream = TrackedStream([b"[]"])
        self.headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json")]
        self.status = 200
        self.requests: list[httpx.Request] = []
        self.client = httpx.Client(
            transport=httpx.MockTransport(self.respond),
            timeout=None,
            follow_redirects=True,
            auth=httpx.BasicAuth("INVENTED", "INVENTED"),
        )

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["Accept-Encoding"] == "identity"
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), 30.0
        )
        return httpx.Response(self.status, headers=self.headers, stream=self.stream)

    def fetch(self, cap: int = 100) -> bytes:
        return retrieve_quiver(
            self.client,
            URL,
            endpoint="contracts",
            token=SecretStr(TOKEN),
            review=synthetic_review(),
            storage_root=self.root,
            at=NOW,
            opt_in=True,
            max_body_bytes=cap,
        )

    def rejected(self, consumed: int, cap: int = 100) -> None:
        with pytest.raises(QuiverError) as error:
            self.fetch(cap)
        assert TOKEN not in str(error.value) and "server-secret" not in str(error.value)
        assert URL not in str(error.value)
        assert self.stream.consumed == consumed and self.stream.closed == 1
        assert len(self.requests) == 1
        assert not list(self.root.rglob("*"))  # No raw/Parquet/canonical/partial files.


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    value = Rig(tmp_path / "private")
    try:
        yield value
    finally:
        value.client.close()


@pytest.mark.parametrize("declared", [False, True])
@pytest.mark.parametrize("cap", [2, MAX_BODY_BYTES])
def test_exact_entity_cap_and_eof_close(rig: Rig, declared: bool, cap: int) -> None:
    payload = b"[" + b" " * (cap - 2) + b"]"
    rig.stream = TrackedStream([payload[:1], payload[1:]])
    if declared:
        rig.headers.append((b"Content-Length", str(cap).encode()))
    assert rig.fetch(cap) == payload
    assert rig.stream.consumed == 2 and rig.stream.closed == 1
    assert len(rig.requests) == 1 and not list(rig.root.rglob("*"))


@pytest.mark.parametrize("declared", [None, b"2", b"1"])
def test_crossing_chunk_aborts_without_tail(rig: Rig, declared: bytes | None) -> None:
    rig.stream = TrackedStream([b"[", b" ]", b"UNCONSUMED-TAIL"])
    if declared is not None:
        rig.headers.append((b"content-length", declared))
    rig.rejected(2, cap=2)


def test_declared_oversize_rejects_before_iteration(rig: Rig) -> None:
    rig.headers.append((b"content-length", b"3"))
    rig.rejected(0, cap=2)


@pytest.mark.parametrize("extra", [0, 1])
def test_raw_parsed_header_aggregate_boundary(rig: Rig, extra: int) -> None:
    base = sum(len(k) + len(v) for k, v in rig.headers)
    rig.headers.extend(
        [(b"x-test", b"a" * 100), (b"X-Test", b"b" * (MAX_HEADER_BYTES - base - 12 - 100 + extra))]
    )
    assert sum(len(k) + len(v) for k, v in rig.headers) == MAX_HEADER_BYTES + extra
    if extra:
        rig.rejected(0)
    else:
        assert rig.fetch() == b"[]" and rig.stream.closed == 1


@pytest.mark.parametrize("status", [201, 301, 302, 307, 401, 403, 429, 500])
def test_status_and_redirect_never_consume_body(rig: Rig, status: int) -> None:
    rig.status = status
    rig.headers.append((b"location", b"https://example.invalid/server-secret"))
    rig.rejected(0)


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"content-type", b"text/html")],
        [(b"content-type", b"application/problem+json")],
        [(b"content-type", b"application/json"), (b"Content-Type", b"application/json")],
        [(b"content-type", b"application/json"), (b"content-encoding", b"gzip")],
        [(b"content-type", b"application/json"), (b"content-encoding", b"br")],
        [(b"content-type", b"application/json"), (b"content-encoding", b"")],
        [(b"content-type", b"application/json"), (b"content-encoding", b"identity, gzip")],
        [
            (b"content-type", b"application/json"),
            (b"content-encoding", b"identity"),
            (b"Content-Encoding", b"identity"),
        ],
    ],
)
def test_mime_encoding_and_challenge_reject_before_body(
    rig: Rig,
    headers: list[tuple[bytes, bytes]],
) -> None:
    rig.headers = headers
    rig.rejected(0)


@pytest.mark.parametrize(
    "value", [b"", b"-1", b"+2", b"2.0", b"1, 1", b"wat", b"\xff", b"\r2", b"2\n", b"\x0b2"]
)
def test_malformed_length_no_body(rig: Rig, value: bytes) -> None:
    rig.headers.append((b"content-length", value))
    rig.rejected(0)


@pytest.mark.parametrize("second", [b"2", b"3"])
def test_duplicate_even_equal_lengths_rejected(rig: Rig, second: bytes) -> None:
    rig.headers.extend([(b"content-length", b"2"), (b"Content-Length", second)])
    rig.rejected(0)


def test_transfer_encoding_and_length_ambiguous(rig: Rig) -> None:
    rig.headers.extend([(b"content-length", b"2"), (b"transfer-encoding", b"chunked")])
    rig.rejected(0)


def test_truncation_detected_at_eof(rig: Rig) -> None:
    rig.headers.append((b"content-length", b"3"))
    rig.rejected(1)


@pytest.mark.parametrize("length", [None, b"0002", b" 2\t"])
def test_absent_or_valid_length_with_identity_encoding(rig: Rig, length: bytes | None) -> None:
    rig.headers.append((b"content-encoding", b"Identity"))
    if length is not None:
        rig.headers.append((b"content-length", length))
    assert rig.fetch() == b"[]" and rig.stream.closed == 1


@pytest.mark.parametrize("failure", [httpx.ReadError, httpx.ReadTimeout, RuntimeError, QuiverError])
def test_midstream_failure_closes_and_withholds_exception(
    rig: Rig,
    failure: type[Exception],
) -> None:
    rig.stream = TrackedStream([b"[", failure(TOKEN + " server-secret " + URL), b"tail"])
    rig.rejected(2)


def test_literal_token_split_across_many_chunks_stops_before_tail(rig: Rig) -> None:
    rig.stream = TrackedStream([b'["', *[bytes([x]) for x in TOKEN.encode()], b'"TAIL"]'])
    rig.rejected(1 + len(TOKEN))


@pytest.mark.parametrize("kind", ["value", "key", "duplicate", "utf16"])
def test_json_escaped_token_rejected_after_eof(rig: Rig, kind: str) -> None:
    escaped = "".join(f"\\u{ord(c):04x}" for c in TOKEN)
    text = '{"x":"' + escaped + '"}'
    if kind == "key":
        text = '{"' + escaped + '":0}'
    if kind == "duplicate":
        text = '{"x":"' + escaped + '","x":"safe"}'
    payload = text.encode("utf16" if kind == "utf16" else "utf8")
    rig.stream = TrackedStream([payload[:5], payload[5:]])
    rig.rejected(2, cap=1000)


@pytest.mark.parametrize("body", [b"<html>challenge</html>", b"[{", b"NaN", b"[" * 2000])
def test_invalid_or_deep_json_never_returned(rig: Rig, body: bytes) -> None:
    rig.stream = TrackedStream([body])
    rig.rejected(1, cap=3000)


@pytest.mark.parametrize(
    "problem",
    [
        "review",
        "future_review",
        "entitlement",
        "optin",
        "token",
        "url",
        "malformed_url",
        "client_query",
        "sync",
        "git",
        "zero",
        "negative",
        "large",
        "bool",
    ],
)
def test_preconditions_dispatch_zero_requests(rig: Rig, problem: str) -> None:
    review = synthetic_review()
    if problem == "future_review":
        review = review.model_copy(update={"reviewed_at": NOW + timedelta(days=1)})
    if problem == "entitlement":
        review = review.model_copy(update={"entitled_endpoints": ("lobbying",)})
    root = rig.root
    if problem == "sync":
        root = root / "OneDrive"
    if problem == "git":
        (root / ".git").mkdir(parents=True)
    if problem == "client_query":
        rig.client.params = httpx.QueryParams({"ticker": "INVENTED"})
    cap = {"zero": 0, "negative": -1, "large": MAX_BODY_BYTES + 1, "bool": True}.get(problem, 100)
    request_url = "https://example.invalid" if problem == "url" else URL
    if problem == "malformed_url":
        request_url = "https://api.quiverquant.com\uff0f" + TOKEN
    with pytest.raises(QuiverError) as error:
        retrieve_quiver(
            rig.client,
            request_url,
            endpoint="contracts",
            token=SecretStr("" if problem == "token" else TOKEN),
            review=None if problem == "review" else review,
            storage_root=root,
            at=NOW,
            opt_in=problem != "optin",
            max_body_bytes=cap,
        )
    assert rig.requests == [] and rig.stream.consumed == rig.stream.closed == 0
    assert TOKEN not in str(error.value) and request_url not in str(error.value)
    assert not [p for p in rig.root.rglob("*") if p.is_file()]
