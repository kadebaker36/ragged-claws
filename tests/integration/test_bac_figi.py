"""Invented and MockTransport-only BAC request/receipt/candidate boundary regressions."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from ragged_claws.ingestion.bac_figi_audit import (
    DECLARATION_HASH,
    FigiAuditError,
    analyze,
    digest,
    encoded,
    load_declaration,
    regenerate,
)
from ragged_claws.ingestion.bac_figi_capture import acquire
from ragged_claws.models import RetentionClass
from ragged_claws.storage import DataLayout, capture_raw_bytes, raw_object_path

REPO = Path(__file__).resolve().parents[2]
DECL = REPO / "research/identity/bac-figi-acquisition-v1.json"
FIXTURE = REPO / "tests/fixtures/openfigi-bac/invented.json"
BODY = b'[{"idType":"ID_CUSIP","idValue":"060505104","includeUnlistedEquities":true}]'


def capture(
    tmp_path: Path,
    raw: bytes | None = None,
    *,
    status: int = 200,
    headers: Any = None,
    failure: str | None = None,
) -> Path:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert (
            request.method == "POST" and str(request.url) == "https://api.openfigi.com/v3/mapping"
        )
        assert request.content == BODY and len(request.content) == 76
        assert dict(request.headers) == {
            "host": "api.openfigi.com",
            "content-length": "76",
            "content-type": "application/json",
            "accept": "application/json",
            "accept-encoding": "identity",
        }
        if failure == "timeout":
            raise httpx.ReadTimeout("INVENTED sensitive provider exception")
        if failure == "transport":
            raise httpx.ConnectError("INVENTED sensitive provider exception")
        if failure == "interrupt":
            raise KeyboardInterrupt
        return httpx.Response(
            status,
            headers=headers,
            stream=httpx.ByteStream(FIXTURE.read_bytes() if raw is None else raw),
        )

    ticks = iter(
        [datetime(2026, 10, 24, 16, tzinfo=UTC), datetime(2026, 10, 24, 16, 0, 2, tzinfo=UTC)]
    )
    root = tmp_path / "capture"
    if failure == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            acquire(
                DECL, REPO, root, transport=httpx.MockTransport(handler), now=lambda: next(ticks)
            )
    else:
        acquire(DECL, REPO, root, transport=httpx.MockTransport(handler), now=lambda: next(ticks))
    assert len(calls) == 1
    assert not list(root.rglob("*.parquet"))
    return root


def test_order_multiplicity_levels_private_lineage_and_replay(tmp_path: Path) -> None:
    root = capture(tmp_path)
    a = regenerate(DECL, REPO, root, tmp_path / "a")
    b = regenerate(DECL, REPO, root, tmp_path / "b")
    assert a == b
    assert (tmp_path / "a/output-hashes.json").read_bytes() == (
        tmp_path / "b/output-hashes.json"
    ).read_bytes()
    report = a["candidate_diagnostic"]
    assert report["candidate_occurrences"] == 3 and report["duplicate_row_excess"] == 1
    assert report["distinct_identifiers_by_provider_field"] == {
        "figi": 2,
        "shareClassFIGI": 1,
        "compositeFIGI": 1,
    }
    assert [r["provider_fields"]["figi"] for r in report["source_rows"]] == [
        "BBG000000020",
        "BBG000000020",
        "BBG000000001",
    ]
    assert report["source_rows"][0]["null_fields"] == ["name"]
    assert "ticker" in report["source_rows"][2]["missing_fields"]
    assert report["groups"]["shareClassFIGI"]["BBG000000010"] == ["/0/data/0", "/0/data/1"]
    assert a["source_observation"]["retention_class"] == "restricted"
    assert a["source_observation"]["public_time"] is None
    assert a["historical_known_from"] is None and a["historical_valid_from"] is None
    assert a["canonical_identity_records_created"] == a["event_bindings_created"] == 0
    assert a["venue_mic"] is None and a["SPY"] == "unresolved"
    assert not list((tmp_path / "a").rglob("*.parquet"))
    with pytest.raises(FigiAuditError):
        acquire(DECL, REPO, root)


@pytest.mark.parametrize(
    "raw,state",
    [
        (b'[{"warning":"INVENTED no result"}]', "no_result"),
        (b'[{"error":"INVENTED provider failure"}]', "provider_error"),
        (b'[{"data":[]}]', "no_result"),
        (b"[]", "invalid_shape"),
        (b'[{"data":null}]', "invalid_shape"),
        (b"[{}]", "invalid_shape"),
        (b'[{"data":[],"error":"INVENTED"}]', "invalid_shape"),
        (b'[{"warning":"INVENTED","error":"INVENTED"}]', "invalid_shape"),
        (b'[{"data":[],"next":"INVENTED"}]', "invalid_shape"),
        (b'[{"data":[],"data":[]}]', "invalid_json"),
        (b"INVENTED invalid", "invalid_json"),
        (b'[{"data":[{"figi":null}]}]', "invalid_identifier"),
        (b'[{"data":[{"figi":"bad"}]}]', "invalid_identifier"),
        (b'[{"data":[{"figi":"BBG000000001","shareClassFIGI":4}]}]', "invalid_shape"),
        (b'[{"data":[{"figi":"BBG000000001","unknownField":null}]}]', "invalid_shape"),
        (b'[{"data":[{"figi":"BBG000000001","ticker":""}]}]', "captured"),
        (b'[{"warning":null}]', "invalid_shape"),
    ],
)
def test_envelope_failures_no_result_and_error_consume_scope(
    tmp_path: Path, raw: bytes, state: str
) -> None:
    root = capture(tmp_path, raw)
    result = regenerate(DECL, REPO, root, tmp_path / "report")
    assert result["receipt"]["state"] == state
    assert result["receipt"]["requests_attempted"] == 1
    assert "INVENTED provider failure" not in (tmp_path / "report/report.json").read_text()
    if b'"ticker":""' in raw:
        assert result["candidate_diagnostic"]["source_rows"][0]["empty_fields"] == ["ticker"]


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_non200_no_retry_or_redirect(tmp_path: Path, status: int) -> None:
    root = capture(
        tmp_path,
        b"INVENTED denial",
        status=status,
        headers={"location": "https://forbidden.invalid/"},
    )
    result = regenerate(DECL, REPO, root, tmp_path / "report")
    assert result["receipt"]["state"] == ("denied" if status in {401, 403, 429} else "non200")
    assert not result["candidate_diagnostic"]


@pytest.mark.parametrize(
    "failure,state",
    [("timeout", "timeout"), ("transport", "transport_error"), ("interrupt", "interrupted")],
)
def test_incomplete_transport_and_interrupted_checkpoints(
    tmp_path: Path, failure: str, state: str
) -> None:
    root = capture(tmp_path, failure=failure)
    result = regenerate(DECL, REPO, root, tmp_path / "report")
    assert result["receipt"]["state"] == state and not result["candidate_diagnostic"]
    assert "sensitive provider exception" not in (tmp_path / "report/report.json").read_text()


@pytest.mark.parametrize("size", [1048576, 1048577])
def test_entity_cap_without_completion_proof(tmp_path: Path, size: int) -> None:
    root = capture(tmp_path, b"x" * size)
    result = regenerate(DECL, REPO, root, tmp_path / "report")
    assert result["receipt"]["state"] == "oversize"
    assert not result["receipt"]["complete_body"]
    assert result["receipt"]["bytes_retained"] == 1048576


def test_header_count_duplicates_and_no_private_header_values(tmp_path: Path) -> None:
    root = capture(tmp_path, headers=[(b"x-invented", b"a" * 8192), (b"x-invented", b"b" * 8192)])
    result = regenerate(DECL, REPO, root, tmp_path / "report")
    assert result["receipt"]["state"] == "header_oversize"
    assert result["receipt"]["header_bytes"] == 2 * (len(b"x-invented") + 8192)
    assert result["receipt"]["bytes_retained"] == 0
    assert b"a" * 100 not in (root / "receipt.json").read_bytes()


def test_privacy_blocked_evidence_stays_private_before_output(tmp_path: Path) -> None:
    root = capture(tmp_path, b'[{"error":"INVENTED test@example.invalid"}]')
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(FigiAuditError, match="blocked") as error:
        regenerate(DECL, REPO, root, tmp_path / "report")
    assert "test@example.invalid" not in str(error.value) and not (tmp_path / "report").exists()
    assert all(p.read_bytes() == content for p, content in before.items())


@pytest.mark.parametrize(
    "change",
    [
        "raw",
        "manifest",
        "state",
        "clock",
        "naive",
        "budget",
        "hash",
        "commit",
        "complete",
        "header",
        "total",
        "extra",
        "size",
        "boolean",
    ],
)
def test_evidence_contradictions_reject_before_output(tmp_path: Path, change: str) -> None:
    root = capture(tmp_path)
    path = root / "receipt.json"
    m = json.loads(path.read_bytes())
    if change == "raw":
        raw_object_path(DataLayout(root / "data"), m["raw_sha256"]).write_bytes(b"changed")
    elif change == "manifest":
        m["manifest_sha256"] = "0" * 64
    elif change == "state":
        m["state"] = m["stop_reason"] = "no_result"
    elif change == "clock":
        m["finished_at"] = "2026-10-24T15:00:00+00:00"
    elif change == "naive":
        m["attempted_at"] = "2026-10-24T15:00:00"
    elif change == "budget":
        m["budget"]["maximum_total_requests"] = 2
    elif change == "hash":
        m["declaration_sha256"] = "0" * 64
    elif change == "commit":
        m["declaration_commit"] = "0" * 40
    elif change == "complete":
        m["complete_body"] = False
    elif change == "header":
        m["header_bytes"] = 16385
    elif change == "total":
        (root / "INVENTED-extra").write_bytes(b"x" * 1114112)
    elif change == "extra":
        m["unsafe_metadata"] = "INVENTED"
    elif change == "size":
        m["bytes_retained"] += 1
    elif change == "boolean":
        m["requests_attempted"] = True
    path.write_bytes(encoded(m))
    with pytest.raises(FigiAuditError):
        regenerate(DECL, REPO, root, tmp_path / "report")
    assert not (tmp_path / "report").exists()


def test_context_mismatch_zero_requests_and_no_ambient_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = tmp_path / "bad.json"
    d.write_bytes(DECL.read_bytes() + b" ")
    with pytest.raises(FigiAuditError):
        acquire(d, REPO, tmp_path / "bad-output")
    assert not (tmp_path / "bad-output").exists()
    monkeypatch.setenv("HTTPS_PROXY", "http://INVENTED.invalid")
    monkeypatch.setenv("OPENFIGI_API_KEY", "INVENTED")
    monkeypatch.setenv("SSLKEYLOGFILE", str(tmp_path / "forbidden-keylog"))
    capture(tmp_path)
    assert not (tmp_path / "forbidden-keylog").exists()


def test_source_evidence_idempotency_and_derivative_bound(tmp_path: Path) -> None:
    raw = encoded([{"data": [{"figi": "BBG000000001"}] * 30000}])
    # Compact provider input fits1MiB; full diagnostic expansion exceeds8MiB.
    raw = json.dumps(json.loads(raw), separators=(",", ":")).encode()
    assert len(raw) < 1048576
    root = capture(tmp_path, raw)
    result = regenerate(DECL, REPO, root, tmp_path / "report")
    assert result["candidate_diagnostic"]["status"] == "report_unavailable"
    assert result["candidate_diagnostic"]["candidate_occurrences"] is None
    assert sum(p.stat().st_size for p in (tmp_path / "report").iterdir()) <= 8388608
    m = json.loads((root / "receipt.json").read_bytes())
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    capture_raw_bytes(
        DataLayout(root / "data"),
        raw,
        provider_namespace="openfigi",
        source_family="openfigi.mapping",
        retrieved_at=datetime.fromisoformat(m["finished_at"]),
        adapter_version="bac-figi-capture/1.0.0",
        parser_version="openfigi-mapping/1.0.0",
        retention_class=RetentionClass.RESTRICTED,
        source_native_id=digest(BODY),
        source_locator="https://api.openfigi.com/v3/mapping",
        request_parameters={
            "request_body_sha256": digest(BODY),
            "declaration_sha256": DECLARATION_HASH,
        },
        license_name="openfigi-private-reviewed-candidate-evidence",
    )
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_unattempted_receipt_size_and_private_storage(tmp_path: Path) -> None:
    root = capture(tmp_path, failure="interrupt")
    (root / "checkpoint-interrupted.json").unlink()
    result = regenerate(DECL, REPO, root, tmp_path / "report")
    assert result["receipt"]["state"] == "unattempted"
    (root / "receipt.json").write_bytes(b" " * 65537)
    with pytest.raises(FigiAuditError, match="bound"):
        regenerate(DECL, REPO, root, tmp_path / "too-large")
    with pytest.raises(FigiAuditError):
        acquire(DECL, REPO, tmp_path / "OneDrive" / "blocked")


@pytest.mark.parametrize("changed", ["proposal", "coverage_card", "source"])
def test_changed_context_makes_zero_requests(tmp_path: Path, changed: str) -> None:
    d = load_declaration(DECL, REPO)
    repo = tmp_path / "repo"
    paths = set(d["input_paths_sha256"]) | {d["proposal"]["path"], d["coverage_card"]["path"]}
    for name in paths:
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((REPO / name).read_bytes())
    name = d[changed]["path"] if changed != "source" else next(iter(d["input_paths_sha256"]))
    (repo / name).write_bytes(b"INVENTED changed context")
    calls: list[str] = []

    def forbidden(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        raise AssertionError("request forbidden")

    with pytest.raises(FigiAuditError):
        acquire(DECL, repo, tmp_path / "out", transport=httpx.MockTransport(forbidden))
    assert calls == [] and not (tmp_path / "out").exists()


def test_partial_response_and_cumulative_timeout(tmp_path: Path) -> None:
    class Partial(httpx.SyncByteStream):
        def __iter__(self):  # type: ignore[no-untyped-def]
            yield b'[{"data":'
            raise httpx.ReadError("INVENTED private exception")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Partial())

    root = tmp_path / "partial"
    acquire(DECL, REPO, root, transport=httpx.MockTransport(handler))
    result = regenerate(DECL, REPO, root, tmp_path / "partial-report")
    assert result["receipt"]["state"] == "transport_error"
    assert result["receipt"]["bytes_retained"] == len(b'[{"data":')
    ticks = iter([0.0, 31.0, 31.0])
    acquire(
        DECL,
        REPO,
        tmp_path / "timeout",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=httpx.ByteStream(FIXTURE.read_bytes()))
        ),
        monotonic=lambda: next(ticks),
    )
    timed = regenerate(DECL, REPO, tmp_path / "timeout", tmp_path / "timeout-report")
    assert timed["receipt"]["state"] == "timeout" and not timed["receipt"]["complete_body"]


def test_exact_header_boundary_and_deep_json_fail_closed(tmp_path: Path) -> None:
    root = capture(tmp_path, headers=[(b"x", b"a" * 16383)])
    result = regenerate(DECL, REPO, root, tmp_path / "report")
    assert result["receipt"]["state"] == "captured"
    assert result["receipt"]["header_bytes"] == 16384
    deep = tmp_path / "deep"
    deep.mkdir()
    blocked = capture(deep, b"[" * 2000 + b"]" * 1999)
    result = regenerate(DECL, REPO, blocked, tmp_path / "deep-report")
    assert result["receipt"]["state"] == "invalid_json"


def test_many_distinct_groups_preserve_each_source_pointer() -> None:
    rows = [{"figi": f"BBG{n:09d}", "shareClassFIGI": f"BBG{n:09d}"} for n in range(1000)]
    state, report = analyze(encoded([{"data": rows}]))
    assert state == "captured"
    assert len(report["groups"]["shareClassFIGI"]) == 1000
    assert report["groups"]["shareClassFIGI"]["BBG000000999"] == ["/0/data/999"]
    assert report["multiple_primary_identifiers"]


def test_orphan_raw_after_interrupt_is_not_interpreted_as_empty_result(tmp_path: Path) -> None:
    root = capture(tmp_path, failure="interrupt")
    (root / "orphan-private-response").write_bytes(FIXTURE.read_bytes())
    result = regenerate(DECL, REPO, root, tmp_path / "report")
    assert result["receipt_phase"] == "checkpoint_only"
    assert result["candidate_diagnostic"] == {} and result["source_observation"] is None
    assert result["retained_capture_directory_bytes"] > len(FIXTURE.read_bytes())
