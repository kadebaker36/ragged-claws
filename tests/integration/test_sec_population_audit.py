"""Invented index frames/submission transformations; no live access, returns or contacts."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from ragged_claws.ingestion.sec import SecForm4Adapter
from ragged_claws.ingestion.sec_audit import (
    HEADER,
    INDEX_URLS,
    AuditError,
    IndexConflict,
    digest,
    encoded,
    filing_path,
    overlap,
    parse_index,
    potential_interval,
    regenerate,
    select_four,
)
from ragged_claws.ingestion.sec_audit_capture import acquire, missing_configuration
from ragged_claws.ingestion.sec_http import SecThrottle
from ragged_claws.models import Event
from ragged_claws.storage import CanonicalConflictError, DataLayout

ROOT = Path(__file__).resolve().parents[2]
SCOPE = ROOT / "research/audits/population-timing-v1.json"
FIXTURE = ROOT / "tests/fixtures/sec/0000950170-24-105263.txt"
OLD_ACCESSION = "0000950170-24-105263"


def index(day: str, *, count: int = 6) -> bytes:
    # Deliberately reverse source order; selection must use accession, not CIK/name/yield.
    rows = [
        f"315090|INVENTED filer|4|{day}|edgar/data/315090/0000000001-24-{n:06}.txt"
        for n in reversed(range(1, count + 1))
    ]
    rows += [
        f"315090|INVENTED amendment|4/A|{day}|edgar/data/315090/0000000002-24-000001.txt",
        f"315090|INVENTED other|8-K|{day}|edgar/data/315090/0000000003-24-000001.txt",
    ]
    return (
        "Invented SEC daily master test fixture\n"
        + f"Last Data Received: Sep {int(day[-2:])}, 2024\n"
        + HEADER
        + "\n-----\n"
        + "\n".join(rows)
        + "\n"
    ).encode()


def body(accession: str, day: str) -> bytes:
    """Invented accession/date variation of the attributed recorded parser fixture."""
    raw = FIXTURE.read_bytes().replace(OLD_ACCESSION.encode(), accession.encode())
    return raw.replace(b"20240910", day.replace("-", "").encode())


def frame_payloads() -> dict[str, bytes]:
    # Distinct filing accessions across days, without altering within-day lexical rule.
    first = index("2024-09-10")
    second = index("2024-09-11").replace(b"-24-", b"-24-1")
    # Keep six-digit tail: 000001 -> 100001, not seven digits.
    second = second.replace(b"-24-10", b"-24-1")
    payloads = {INDEX_URLS[0]: first, INDEX_URLS[1]: second}
    for raw, day in [(first, "2024-09-10"), (second, "2024-09-11")]:
        for row in select_four(parse_index(raw, day)[0]):
            payloads[row.url] = body(row.accession, day)
    return payloads


def capture(
    tmp_path: Path, payloads: dict[str, bytes], *, denied: str | None = None, status: int = 403
) -> Path:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        assert url in payloads
        return httpx.Response(
            status if url == denied else 200,
            stream=httpx.ByteStream(b"Denied" if url == denied else payloads[url]),
        )

    tick = 0

    def now() -> datetime:
        nonlocal tick
        tick += 1
        return datetime(2026, 10, 24, tzinfo=UTC) + timedelta(seconds=tick * 2)

    target = tmp_path / "captures"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = acquire(
            SCOPE,
            target,
            user_agent="Invented audit test test@example.invalid",
            client=client,
            throttle=SecThrottle(interval=1, sleep=lambda _: None),
            now=now,
        )
    assert result["requests_attempted"] == len(calls) <= 10
    return target


def test_selection_conflict_duplicates_all_forms_and_unsafe_paths() -> None:
    raw = index("2024-09-10")
    rows, duplicates = parse_index(raw + raw.splitlines()[-1] + b"\n", "2024-09-10")
    assert duplicates == 1 and len(rows) == 9
    assert [r.accession for r in select_four(rows)] == [
        f"0000000001-24-{n:06}" for n in range(1, 5)
    ]
    assert len(select_four(parse_index(index("2024-09-10", count=2), "2024-09-10")[0])) == 2
    with pytest.raises(AuditError, match="conflicting"):
        parse_index(raw + raw.splitlines()[-1].replace(b"8-K", b"4") + b"\n", "2024-09-10")
    for bad in [
        b"bad row",
        raw.replace(b"2024-09-10", b"2024-09-11"),
        raw.replace(b"edgar/data/315090", b"edgar/data/1"),
        raw.replace(HEADER.encode(), b"bad"),
    ]:
        with pytest.raises(AuditError):
            parse_index(bad, "2024-09-10")
    for path in [
        "https://evil.test/a",
        "edgar/data/1/../a.txt",
        "/edgar/data/1/a.txt",
        "edgar/data/1/0000000001-24-000001.txt?x=1",
        "edgar/data/1/%2e%2e/0000000001-24-000001.txt",
        "edgar\\data\\1\\0000000001-24-000001.txt",
    ]:
        with pytest.raises(AuditError):
            filing_path(path)
    with pytest.raises(AuditError):
        filing_path("edgar/data/1/0000000001-24-000001.txt", "0000000001-24-000002")


def test_offline_regeneration_clock_identity_exclusions_and_immutable_inputs(
    tmp_path: Path,
) -> None:
    payloads = frame_payloads()
    selected_urls = list(payloads)[2:]
    # No substitution after no-P/S, malformed body or unknown timing.
    payloads[selected_urls[0]] = payloads[selected_urls[0]].replace(
        b"<transactionCode>S</transactionCode>", b"<transactionCode>A</transactionCode>"
    )
    payloads[selected_urls[1]] = b"invented malformed submission"
    payloads[selected_urls[2]] = re.sub(
        rb"<ACCEPTANCE-DATETIME>[^\n]*\n", b"", payloads[selected_urls[2]]
    )
    captures = capture(tmp_path, payloads)
    before = {p: digest(p.read_bytes()) for p in captures.rglob("*") if p.is_file()}
    first = regenerate(SCOPE, captures, tmp_path / "first")
    second = regenerate(SCOPE, captures, tmp_path / "second")
    assert first == second
    assert (tmp_path / "first/output-hashes.json").read_bytes() == (
        tmp_path / "second/output-hashes.json"
    ).read_bytes()
    assert before == {p: digest(p.read_bytes()) for p in before}
    assert not first["complete_declared_acquisition"]
    assert first["counts"]["selected_filings"] == 8
    assert first["counts"]["selected_no_events"] == 1
    assert first["counts"]["parse_states"] == {"parsed": 7, "malformed": 1}
    assert first["counts"]["unique_ps_events"] == 18
    assert first["potential_overlap"]["unknown_intervals"] == 3
    for frame in first["index_frames"]:
        assert frame["unique_form4"] == 6 and frame["selected"] == 4
        assert sum(r["selection"] == "uncollected" for r in frame["references"]) == 2
    parsed = [f for f in first["selected_filings"] if f["parse_state"] == "parsed"]
    assert all(f["index_cik"] == "315090" and f["body_issuer_cik"] == "0000070858" for f in parsed)
    for event in first["events"]:
        assert event["actual_policy_entry"] is None and event["actual_decision_at"] is None
        assert event["first_ever_collector_receipt"] is None
        assert event["historical_decision_availability"] == "unknown"
        assert event["retrieved_at"].startswith("2026")
        assert event["entry"] is None or event["entry"].startswith("2024")
    with pytest.raises(AuditError, match="fresh"):
        regenerate(SCOPE, captures, tmp_path / "first")
    record = json.loads((captures / "manifest.json").read_bytes())["resources"][0]
    (captures / "objects" / record["sha256"]).write_bytes(b"tampered")
    with pytest.raises(AuditError, match="hash"):
        regenerate(SCOPE, captures, tmp_path / "tampered")


@pytest.mark.parametrize("status", [403, 429, 302, 500])
def test_global_stop_no_retry_and_unattempted_not_zero(tmp_path: Path, status: int) -> None:
    payloads = frame_payloads()
    captures = capture(tmp_path, payloads, denied=INDEX_URLS[0], status=status)
    result = regenerate(SCOPE, captures, tmp_path / "output")
    assert result["acquisition"]["requests_attempted"] == 1
    assert result["index_frames"][1]["capture_status"] == "unattempted"
    assert all(f["unique_form4"] is None for f in result["index_frames"])
    assert not result["complete_declared_acquisition"]


def test_submission_failure_no_replacement_and_recorded_bytes(tmp_path: Path) -> None:
    payloads = frame_payloads()
    captures = capture(tmp_path, payloads, denied=list(payloads)[2])
    report = regenerate(SCOPE, captures, tmp_path / "output")
    assert report["counts"]["submission_states"] == {"denied": 1, "unattempted": 7}
    assert all(f["events"] is None for f in report["selected_filings"])
    assert report["counts"]["selected_no_events"] == 0
    assert report["acquisition"]["requests_attempted"] == 3


def test_oversize_challenge_invalid_index_and_scope_no_extra_gets(tmp_path: Path) -> None:
    for name, content, state in [
        ("large", b"x" * (2 * 1024**2 + 1), "oversize"),
        ("challenge", b"<html>challenge</html>", "challenge"),
        ("malformed", b"bad index", "invalid_index"),
    ]:
        sub = tmp_path / name
        sub.mkdir()
        payloads = frame_payloads()
        payloads[INDEX_URLS[0]] = content
        captures = capture(sub, payloads)
        manifest = json.loads((captures / "manifest.json").read_bytes())
        assert manifest["requests_attempted"] == 1 and manifest["stop_reason"] == state
        assert manifest["bytes_retained"] <= 2 * 1024**2
        result = regenerate(SCOPE, captures, sub / "out")
        assert not result["complete_declared_acquisition"]
    modified = tmp_path / "scope.json"
    modified.write_bytes(SCOPE.read_bytes() + b" ")
    with pytest.raises(AuditError, match="scope"):
        regenerate(modified, captures, tmp_path / "bad-scope")


def test_missing_contact_receipt_offline(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    missing_configuration(SCOPE, captures)
    report = regenerate(SCOPE, captures, tmp_path / "out")
    assert report["acquisition"]["requests_attempted"] == 0
    assert report["acquisition"]["stop_reason"] == "missing_sec_user_agent"
    assert not report["complete_declared_acquisition"]


def test_interval_oracle_endpoint_and_repeat_issuer() -> None:
    entry = datetime(2024, 9, 11, 13, 30, tzinfo=UTC)
    interval = potential_interval(entry)
    assert interval["exit"] == "2024-12-05T21:00:00+00:00"
    assert potential_interval(None)["status"] == "unknown_public_timing"
    with pytest.raises(AuditError, match="open"):
        potential_interval(entry + timedelta(seconds=1))
    intervals = [
        dict(interval, issuer="one"),
        dict(interval, issuer="one"),
        {"entry": interval["exit"], "exit": "2024-12-06T21:00:00+00:00", "issuer": "two"},
        {"entry": None, "exit": None, "issuer": "unknown"},
    ]
    summary = overlap(intervals)
    assert summary["peak_event_supports"] == 3 and summary["peak_distinct_issuers"] == 2
    assert summary["peak_repeat_issuer_excess_supports"] == 1
    assert summary["unknown_intervals"] == 1


def test_literal_index_path_adapter_replay_and_conflict(tmp_path: Path) -> None:
    adapter = SecForm4Adapter(DataLayout(tmp_path / "data"))
    accession = "0000000001-24-000001"
    raw = body(accession, "2024-09-10")
    params: dict[str, Any] = {
        "accession": accession,
        "retrieved_at": datetime(2026, 10, 24, tzinfo=UTC),
        "source_locator": f"https://www.sec.gov/Archives/edgar/data/315090/{accession}.txt",
        "acceptance_timezone": "America/New_York",
    }
    first = adapter.ingest(raw, **params)
    second = adapter.ingest(raw, **params)
    assert first == second and len(adapter.store.load(Event)) == 3
    with pytest.raises(CanonicalConflictError):
        adapter.ingest(raw.replace(b"39.6682", b"39.6683"), **params)
    assert len(adapter.store.load(Event)) == 3


def test_manifest_rejects_fake_success_extra_url_and_attempt_after_stop(tmp_path: Path) -> None:
    captures = capture(tmp_path, frame_payloads(), denied=INDEX_URLS[0])
    path = captures / "manifest.json"
    original = json.loads(path.read_bytes())
    for variant in ("fake_success", "extra_url", "after_stop"):
        manifest = json.loads(encoded(original))
        if variant == "fake_success":
            manifest["resources"][0]["state"] = "captured"
        elif variant == "extra_url":
            manifest["resources"].append(
                {"url": "https://evil.test", "kind": "submission", "state": "unattempted"}
            )
        else:
            manifest["resources"][1].update(manifest["resources"][0])
        path.write_bytes(encoded(manifest))
        with pytest.raises(AuditError):
            regenerate(SCOPE, captures, tmp_path / variant)


def test_recorded_index_conflict_preserves_failed_acquisition_and_denominators(
    tmp_path: Path,
) -> None:
    captures = ROOT / "tests/fixtures/sec-population/audit-v1"
    manifest = json.loads((captures / "manifest.json").read_bytes())
    raw = (captures / "objects" / manifest["resources"][0]["sha256"]).read_bytes()
    assert len(raw) == 337624
    assert digest(raw) == "ce75cb8eaa6d7f7fe5976aa4c8aa9e59c199b62c9025fa6cc769cc54cd1a7f5b"
    with pytest.raises(IndexConflict) as failed:
        parse_index(raw, "2024-09-10")
    context = failed.value.context
    assert context["physical_rows"] == 3857
    assert context["form4_row_references"] == 1053
    assert context["form4_unique_accession_labels"] == 490
    assert len(context["conflicts"]) == 1128
    report = regenerate(SCOPE, captures, tmp_path / "recorded")
    assert report["acquisition"] == manifest  # Original rejection is not rewritten as a success.
    assert report["index_frames"][0]["rejected_index_context"] == context
    assert report["index_frames"][0]["unique_form4"] is None
    assert report["index_frames"][1]["capture_status"] == "unattempted"
    assert report["counts"]["selected_filings"] == 0
    assert not report["complete_declared_acquisition"]
    assert not report["events"] and report["potential_overlap"]["known_intervals"] == 0
    assert not (tmp_path / "recorded/data/curated/event.parquet").exists()
    with pytest.raises(AuditError, match="header day"):
        parse_index(raw, "2024-09-11")


def test_older_official_filing_date_is_separate_from_index_day() -> None:
    raw = index("2024-09-10", count=1).replace(b"|2024-09-10|", b"|20240909|")
    rows, _ = parse_index(raw, "2024-09-10")
    assert rows[0].filed == "2024-09-09" and rows[0].filed_raw == "20240909"
    assert rows[0].index_day == "2024-09-10"


@pytest.mark.parametrize("variant", ["date", "form"])
def test_body_index_date_type_mismatch_does_not_publish(tmp_path: Path, variant: str) -> None:
    payloads = frame_payloads()
    url = list(payloads)[2]
    if variant == "date":
        payloads[url] = payloads[url].replace(
            b"FILED AS OF DATE:\t\t20240910", b"FILED AS OF DATE:\t\t20240909"
        )
    else:
        payloads[url] = payloads[url].replace(
            b"CONFORMED SUBMISSION TYPE:\t4", b"CONFORMED SUBMISSION TYPE:\t3"
        )
    captures = capture(tmp_path, payloads)
    result = regenerate(SCOPE, captures, tmp_path / "out")
    assert result["selected_filings"][0]["parse_state"] == "malformed"
    assert result["selected_filings"][0]["events"] is None
    assert result["counts"]["selected_filings"] == 8


def test_transport_failure_is_single_attempt_and_no_contact_in_receipt(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("invented private request context", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        manifest = acquire(
            SCOPE,
            tmp_path / "captures",
            client=client,
            user_agent="Invented audit test test@example.invalid",
        )
    assert calls == 1 and manifest["stop_reason"] == "transport_error"
    assert b"example.invalid" not in encoded(manifest)
    result = regenerate(SCOPE, tmp_path / "captures", tmp_path / "out")
    assert not result["complete_declared_acquisition"]


def empty_payloads() -> dict[str, bytes]:
    return {
        url: (
            f"Invented empty index\nLast Data Received: Sep {day}, 2024\n" + HEADER + "\n-----\n"
        ).encode()
        for url, day in zip(INDEX_URLS, (10, 11), strict=True)
    }


@pytest.mark.parametrize(
    "field",
    ["sha256", "size_bytes", "attempted_at", "retrieved_at", "http_status", "complete_body"],
)
def test_captured_empty_index_requires_all_evidence_fields(tmp_path: Path, field: str) -> None:
    captures = capture(tmp_path, empty_payloads())
    path = captures / "manifest.json"
    manifest = json.loads(path.read_bytes())
    del manifest["resources"][0][field]
    path.write_bytes(encoded(manifest))
    with pytest.raises(AuditError):
        regenerate(SCOPE, captures, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", None),
        ("sha256", "not-a-hash"),
        ("size_bytes", -1),
        ("size_bytes", True),
        ("retrieved_at", None),
        ("retrieved_at", "bad-clock"),
        ("http_status", None),
        ("complete_body", "true"),
    ],
)
def test_captured_metadata_cannot_be_null_or_coerced(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    captures = capture(tmp_path, empty_payloads())
    path = captures / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["resources"][0][field] = value
    path.write_bytes(encoded(manifest))
    with pytest.raises(AuditError):
        regenerate(SCOPE, captures, tmp_path / "output")


@pytest.mark.parametrize("kind", ["index", "submission"])
@pytest.mark.parametrize("failure", ["missing_hash", "absent_object", "directory_object"])
def test_each_captured_resource_requires_usable_bound_bytes(
    tmp_path: Path,
    kind: str,
    failure: str,
) -> None:
    captures = capture(tmp_path, frame_payloads())
    path = captures / "manifest.json"
    manifest = json.loads(path.read_bytes())
    record = next(r for r in manifest["resources"] if r["kind"] == kind)
    if failure == "missing_hash":
        del record["sha256"]
        path.write_bytes(encoded(manifest))
    else:
        obj = captures / "objects" / record["sha256"]
        obj.unlink()
        if failure == "directory_object":
            obj.mkdir()
    with pytest.raises(AuditError):
        regenerate(SCOPE, captures, tmp_path / "output")


@pytest.mark.parametrize("field", ["declaration_commit", "declared_budget"])
@pytest.mark.parametrize("mutation", ["missing", "conflicting"])
def test_receipt_identity_and_budget_must_match_scope(
    tmp_path: Path,
    field: str,
    mutation: str,
) -> None:
    captures = capture(tmp_path, empty_payloads())
    path = captures / "manifest.json"
    manifest = json.loads(path.read_bytes())
    if mutation == "missing":
        del manifest[field]
    elif field == "declaration_commit":
        manifest[field] = "0" * 40
    else:
        manifest[field]["max_submission_gets"] = 1000
    path.write_bytes(encoded(manifest))
    with pytest.raises(AuditError):
        regenerate(SCOPE, captures, tmp_path / "output")


def test_genuine_complete_empty_frames_remain_complete(tmp_path: Path) -> None:
    captures = capture(tmp_path, empty_payloads())
    result = regenerate(SCOPE, captures, tmp_path / "output")
    assert result["complete_declared_acquisition"]
    assert [f["rows"] for f in result["index_frames"]] == [0, 0]
    assert [f["unique_form4"] for f in result["index_frames"]] == [0, 0]
    assert result["events"] == [] and result["selected_filings"] == []


@pytest.mark.parametrize("state", ["interrupted", "partial_transport"])
def test_genuine_interrupted_and_partial_receipts_remain_incomplete(
    tmp_path: Path,
    state: str,
) -> None:
    captures = capture(tmp_path, empty_payloads(), denied=INDEX_URLS[0])
    path = captures / "manifest.json"
    manifest = json.loads(path.read_bytes())
    record = manifest["resources"][0]
    if state == "interrupted":
        start = record["attempted_at"]
        record.clear()
        record.update(url=INDEX_URLS[0], kind="index", state="interrupted", attempted_at=start)
        manifest["bytes_retained"] = 0
        manifest["stop_reason"] = "interrupted"
    else:
        record.update(state="transport_error", http_status=200, complete_body=False)
        manifest["stop_reason"] = "transport_error"
    path.write_bytes(encoded(manifest))
    result = regenerate(SCOPE, captures, tmp_path / "output")
    assert not result["complete_declared_acquisition"]
    assert result["index_frames"][0]["rows"] is None
    assert result["index_frames"][1]["capture_status"] == "unattempted"
    assert result["events"] == [] and result["population_overlap"] is None
