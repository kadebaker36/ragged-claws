"""Invented complete-submission variants and mocked requests, never real acquisition."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from ragged_claws.ingestion.sec import SecForm4Adapter
from ragged_claws.ingestion.sec_audit import AuditError, encoded, overlap, potential_interval
from ragged_claws.ingestion.sec_body_audit import load_inputs, regenerate, verify_receipt
from ragged_claws.ingestion.sec_body_capture import acquire
from ragged_claws.ingestion.sec_http import SecThrottle
from ragged_claws.models import Event
from ragged_claws.storage import CanonicalConflictError, DataLayout

ROOT = Path(__file__).resolve().parents[2]
DECL = ROOT / "research/audits/four-body-v1.json"
CONTEXT = ROOT / "research/audits/four-body-reference-context-v1.json"
SOURCE = ROOT / "tests/fixtures/sec/0000950170-24-105263.txt"


def capture(tmp_path: Path, *, variant: str = "valid", fail_at: int = 0) -> Path:
    declaration, _ = load_inputs(DECL, CONTEXT)
    resources = declaration["resources"]
    calls: list[str] = []
    tick = 0

    def now() -> datetime:
        nonlocal tick
        tick += 1
        return datetime(2026, 10, 24, tzinfo=UTC) + timedelta(seconds=2 * tick)

    def handler(request: httpx.Request) -> httpx.Response:
        n = len(calls)
        calls.append(str(request.url))
        assert str(request.url) == resources[n]["url"]
        raw = SOURCE.read_bytes().replace(
            b"0000950170-24-105263", resources[n]["accession"].encode()
        )
        status = 200
        if n == fail_at:
            if variant == "denied":
                status, raw = 403, b"invented denial"
            elif variant == "429":
                status, raw = 429, b"invented rate stop"
            elif variant == "redirect":
                status, raw = 302, b"invented redirect"
            elif variant == "transport":
                raise httpx.ConnectError("invented", request=request)
            elif variant == "oversize":
                raw = b"x" * (5242880 + 1)
            elif variant == "challenge":
                raw = b"<html>invented challenge</html>"
            elif variant == "accession":
                raw = raw.replace(resources[n]["accession"].encode(), b"0000000001-24-000001")
            elif variant == "form":
                raw = raw.replace(
                    b"CONFORMED SUBMISSION TYPE:\t4", b"CONFORMED SUBMISSION TYPE:\t3"
                )
            elif variant == "date":
                raw = raw.replace(
                    b"FILED AS OF DATE:\t\t20240910", b"FILED AS OF DATE:\t\t20240909"
                )
            elif variant == "empty":
                raw = raw.replace(
                    b"<transactionCode>S</transactionCode>", b"<transactionCode>A</transactionCode>"
                )
            elif variant == "unknown_time":
                raw = re.sub(rb"<ACCEPTANCE-DATETIME>[^\n]*\n", b"", raw)
            elif variant == "privacy":
                raw += b"test@example.invalid"
        return httpx.Response(status, stream=httpx.ByteStream(raw))

    root = tmp_path / "captures"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        m = acquire(
            DECL,
            CONTEXT,
            root,
            user_agent="Invented test test@example.invalid",
            client=client,
            throttle=SecThrottle(interval=1, sleep=lambda _: None),
            now=now,
        )
    assert len(calls) == m["requests_attempted"] <= 4
    assert m["bytes_retained"] <= 20971520
    return root


@pytest.mark.parametrize(
    "variant",
    [
        "denied",
        "429",
        "redirect",
        "transport",
        "oversize",
        "challenge",
        "accession",
        "form",
        "date",
        "privacy",
    ],
)
def test_global_stop_and_no_substitution(tmp_path: Path, variant: str) -> None:
    captures = capture(tmp_path, variant=variant, fail_at=1)
    m = json.loads((captures / "manifest.json").read_bytes())
    assert m["requests_attempted"] == 2
    assert [r["state"] for r in m["resources"]][2:] == ["unattempted", "unattempted"]
    r = regenerate(DECL, CONTEXT, captures, tmp_path / "out")
    assert not r["complete_declared_capture"]
    assert r["filings"][1]["event_count"] is None and r["filings"][2]["event_count"] is None
    assert r["counts"]["unique_observed_ps_events"] == 3


def test_complete_replay_clock_identity_raw_and_idempotency(tmp_path: Path) -> None:
    captures = capture(tmp_path, variant="unknown_time", fail_at=0)
    a = regenerate(DECL, CONTEXT, captures, tmp_path / "a")
    b = regenerate(DECL, CONTEXT, captures, tmp_path / "b")
    assert a == b and a["complete_declared_capture"]
    assert a["counts"]["unique_observed_ps_events"] == 12
    assert a["potential_supports"]["unknown_intervals"] == 3
    assert a["counts"]["unselected_uncollected_groups"] == 486
    assert a["uncollected_group_events"] is None and a["second_index_population"] is None
    assert all(
        e["actual_policy_entry"] is None
        and e["historical_decision_availability"] == "unknown"
        and e["capture_at"].startswith("2026")
        for e in a["events"]
    )
    assert a["filings"][0]["bundle"]["filing"]["issuer_cik"] == "0000070858"
    assert "/35527/" in a["filings"][0]["source_reference"]["url"]
    assert (tmp_path / "a/output-hashes.json").read_bytes() == (
        tmp_path / "b/output-hashes.json"
    ).read_bytes()
    record = a["filings"][1]["source_reference"]
    raw = (captures / "objects" / record["sha256"]).read_bytes()
    adapter = SecForm4Adapter(DataLayout(tmp_path / "a/data"))
    kwargs: dict[str, Any] = {
        "accession": record["accession"],
        "source_locator": record["url"],
        "retrieved_at": datetime.fromisoformat(record["retrieved_at"]),
        "acceptance_timezone": "America/New_York",
        "form_type": "4",
        "filed_as_of": datetime.fromisoformat(record["filed_as_of"]).date(),
    }
    adapter.ingest(raw, **kwargs)
    assert len(adapter.store.load(Event)) == 12
    with pytest.raises(CanonicalConflictError):
        adapter.ingest(raw.replace(b"39.6682", b"39.6683"), **kwargs)


def test_parsed_empty_is_zero_but_unavailable_is_not(tmp_path: Path) -> None:
    captures = capture(tmp_path, variant="empty")
    r = regenerate(DECL, CONTEXT, captures, tmp_path / "out")
    assert r["counts"]["parsed_no_events"] == 1 and r["filings"][0]["event_count"] == 0
    assert r["counts"]["unique_observed_ps_events"] == 9
    assert r["counts"]["row_exclusions"]


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "object",
        "clock",
        "status",
        "complete",
        "budget",
        "commit",
        "order",
        "extra",
        "scope",
    ],
)
def test_evidence_or_reference_contradiction_rejects_before_publication(
    tmp_path: Path, change: str
) -> None:
    captures = capture(tmp_path)
    path = captures / "manifest.json"
    m = json.loads(path.read_bytes())
    row = m["resources"][0]
    if change == "hash":
        del row["sha256"]
    elif change == "object":
        (captures / "objects" / row["sha256"]).unlink()
    elif change == "clock":
        row["retrieved_at"] = None
    elif change == "status":
        row["http_status"] = 403
    elif change == "complete":
        row["complete_body"] = False
    elif change == "budget":
        m["declared_budget"]["maximum_gets"] = 100
    elif change == "commit":
        m["declaration_commit"] = "0" * 40
    elif change == "order":
        m["resources"].reverse()
    elif change == "extra":
        m["resources"].append(row.copy())
    else:
        row["url"] = "https://evil.test/data"
    path.write_bytes(encoded(m))
    with pytest.raises(AuditError):
        regenerate(DECL, CONTEXT, captures, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_missing_configuration_interrupted_and_interval_oracle(tmp_path: Path) -> None:
    acquire(DECL, CONTEXT, tmp_path / "missing", user_agent=None)
    r = regenerate(DECL, CONTEXT, tmp_path / "missing", tmp_path / "out")
    assert r["counts"]["body_states"] == {"unattempted": 4}
    assert all(f["event_count"] is None for f in r["filings"])
    path = tmp_path / "missing/manifest.json"
    m = json.loads(path.read_bytes())
    m["stop_reason"] = "interrupted"
    m["requests_attempted"] = 1
    m["resources"][0].update(state="interrupted", attempted_at="2026-10-24T12:00:00+00:00")
    path.write_bytes(encoded(m))
    d, _ = load_inputs(DECL, CONTEXT)
    assert verify_receipt(d, m, tmp_path / "missing") == {}
    support = potential_interval(datetime(2024, 9, 11, 13, 30, tzinfo=UTC))
    assert support["exit"] == "2024-12-05T21:00:00+00:00"
    s = overlap([{**support, "issuer": "same"}, {**support, "issuer": "same"}])
    assert s["peak_event_supports"] == 2 and s["peak_repeat_issuer_excess_supports"] == 1
