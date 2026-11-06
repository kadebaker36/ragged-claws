"""Synthetic daily indexes and complete submissions; all requests use MockTransport."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from ragged_claws.cli import app
from ragged_claws.ingestion.sec_http import (
    SecBoundedAccessError,
    SecFilingClient,
    SecThrottle,
    fetch_watch_resource,
)
from ragged_claws.models import Event
from ragged_claws.storage import CanonicalParquetStore, DataLayout, raw_object_path
from ragged_claws.watch.discovery import (
    HEADER,
    capture_index,
    fetch_index,
    index_url,
    load_scan,
    process_scan,
)
from ragged_claws.watch.ledger import build_report
from tests.integration.test_purchase_watch import (
    ACCESSION,
    AS_OF,
    OBSERVED,
    bind,
    purchase_bytes,
)

DAY = date(2024, 9, 11)
SECOND = "0000950170-24-105264"
AGENT = "Invented offline fixture fixture@example.invalid"


def index_bytes(*, rows: list[str] | None = None) -> bytes:
    if rows is None:
        rows = [
            f"70858|Invented issuer|4|20240910|edgar/data/70858/{SECOND}.txt",
            f"315090|Invented reporting owner|4|20240910|edgar/data/315090/{ACCESSION}.txt",
            f"70858|Invented issuer|4|20240910|edgar/data/70858/{ACCESSION}.txt",
            # Literal duplicate evidence is retained, never an extra filing.
            f"70858|Invented issuer|4|20240910|edgar/data/70858/{ACCESSION}.txt",
            "1|Invented amendment|4/A|2024-09-11|edgar/data/1/0000000001-24-000001.txt",
        ]
    return (
        "Description: invented fixture\nLast Data Received: Sep 11, 2024\n"
        + HEADER
        + "\n---------------------\n"
        + "\n".join(rows)
        + "\n"
    ).encode()


def test_partial_accounting_and_resume_are_deterministic_without_skip_or_duplicates(
    tmp_path: Path,
) -> None:
    layout = DataLayout(tmp_path / "data with spaces")
    raw = index_bytes()
    scan = capture_index(layout, raw, day=DAY, retrieved_at=OBSERVED)
    manifest_hashes = list(layout.raw_objects.glob("*/*"))
    assert any(p.read_bytes() == raw for p in manifest_hashes)
    assert len(scan.filings) == 2 and len(scan.filings[0].references) == 3
    assert scan.filings[0].selected_archive_path == f"edgar/data/70858/{ACCESSION}.txt"
    checkpoint = tmp_path / "scan with spaces.json"
    fetched = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        accession = url.rsplit("/", 1)[-1][:-4]
        return purchase_bytes(accession=accession)

    first = process_scan(
        layout,
        scan,
        checkpoint=checkpoint,
        fetch=fetch,
        limit=1,
        now=lambda: OBSERVED,
        acceptance_timezone="America/New_York",
    )
    summary = first.completeness(layout, as_of=AS_OF)
    assert summary.discovered_form4_count == 2
    assert summary.processed_filing_count == summary.successfully_ingested_count == 1
    assert summary.remaining_unprocessed_count == 1
    assert summary.rejected_count == summary.qualifying_p_event_count == 0
    assert summary.unresolved_p_event_count == 3
    assert not summary.index_processing_complete and summary.market_coverage == "unknown"
    resumed = load_scan(layout, checkpoint)
    final = process_scan(
        layout,
        resumed,
        checkpoint=checkpoint,
        fetch=fetch,
        limit=1,
        now=lambda: OBSERVED,
        acceptance_timezone="America/New_York",
    )
    assert len(fetched) == 2 and len(set(fetched)) == 2
    assert final.cursor == 2
    assert len(CanonicalParquetStore(layout).load(Event)) == 6
    again = process_scan(layout, final, checkpoint=checkpoint, fetch=fetch, limit=1)
    assert again == final and len(fetched) == 2
    assert load_scan(layout, checkpoint) == final
    summary = final.completeness(layout, as_of=AS_OF)
    assert summary.index_processing_complete and summary.remaining_unprocessed_count == 0
    assert summary.market_coverage == "unknown"
    bind(layout)
    assert final.completeness(layout, as_of=AS_OF).qualifying_p_event_count == 6
    report = build_report(layout, as_of=AS_OF, discovery=(summary,))
    assert report.discovery_status == "captured_index_scope_only_market_coverage_unknown"


def test_index_date_never_supplies_public_or_actionable_time(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    # Discovery day September 11, index filing date September 10; actual body acceptance is
    # September 10 23:13:16 UTC. Missing body acceptance stays unknown regardless of index.
    scan = capture_index(layout, index_bytes(), day=DAY, retrieved_at=OBSERVED)
    state = process_scan(
        layout,
        scan,
        checkpoint=tmp_path / "scan.json",
        fetch=lambda _: purchase_bytes(),
        limit=1,
        now=lambda: OBSERVED,
        acceptance_timezone="America/New_York",
    )
    events = CanonicalParquetStore(layout).load(Event)
    assert all(
        e.public_time is not None
        and e.public_time.timestamp == datetime(2024, 9, 10, 23, 13, 16, tzinfo=UTC)
        for e in events
    )
    assert all(e.actionable_at == datetime(2024, 9, 11, 13, 30, tzinfo=UTC) for e in events)
    assert state.filings[0].references[0].filing_date == date(2024, 9, 10)


def test_rejections_are_counted_and_resume_after_failure_stays_on_same_filing(
    tmp_path: Path,
) -> None:
    layout = DataLayout(tmp_path)
    scan = capture_index(layout, index_bytes(), day=DAY, retrieved_at=OBSERVED)
    checkpoint = tmp_path / "scan.json"

    def fail(_: str) -> bytes:
        raise SecBoundedAccessError("transport_failure", b"partial")

    with pytest.raises(SecBoundedAccessError):
        process_scan(layout, scan, checkpoint=checkpoint, fetch=fail, limit=1, now=lambda: OBSERVED)
    assert load_scan(layout, checkpoint).cursor == 0
    assert any(p.read_bytes() == b"partial" for p in layout.raw_objects.glob("*/*"))
    rejected = process_scan(
        layout,
        load_scan(layout, checkpoint),
        checkpoint=checkpoint,
        fetch=lambda _: b"invalid submission",
        limit=1,
        now=lambda: OBSERVED,
    )
    summary = rejected.completeness(layout, as_of=AS_OF)
    assert summary.rejected_count == 1 and summary.successfully_ingested_count == 0
    assert summary.remaining_unprocessed_count == 1


def test_conflicting_index_metadata_is_visible_and_rejected_without_request(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    rows = [
        f"1|Invented|4|20240910|edgar/data/1/{ACCESSION}.txt",
        f"2|Invented|4/A|20240910|edgar/data/2/{ACCESSION}.txt",
    ]
    scan = capture_index(layout, index_bytes(rows=rows), day=DAY, retrieved_at=OBSERVED)

    def forbidden(_: str) -> bytes:
        pytest.fail("conflicting reference requested")

    scan = process_scan(
        layout,
        scan,
        checkpoint=tmp_path / "checkpoint.json",
        fetch=forbidden,
        limit=1,
        now=lambda: OBSERVED,
    )
    assert scan.completeness(layout, as_of=AS_OF).rejected_count == 1
    assert len(scan.filings[0].references) == 2


@pytest.mark.parametrize(
    "path", ["../secret", "edgar/data/1/../x.txt", "https://elsewhere.invalid/a.txt"]
)
def test_unsafe_index_reference_is_captured_then_rejected(tmp_path: Path, path: str) -> None:
    layout = DataLayout(tmp_path)
    with pytest.raises(ValueError):
        capture_index(
            layout,
            index_bytes(rows=[f"1|Invented|4|20240910|{path}"]),
            day=DAY,
            retrieved_at=OBSERVED,
        )
    assert tuple(layout.raw_objects.glob("*/*"))


def test_checkpoint_is_bound_to_exact_raw_references(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    scan = capture_index(layout, index_bytes(), day=DAY, retrieved_at=OBSERVED)
    checkpoint = tmp_path / "scan.json"
    process_scan(
        layout,
        scan,
        checkpoint=checkpoint,
        fetch=lambda _: purchase_bytes(),
        limit=1,
        now=lambda: OBSERVED,
    )
    data = json.loads(checkpoint.read_bytes())
    data["filings"][0]["selected_archive_path"] = f"edgar/data/1/{ACCESSION}.txt"
    checkpoint.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="reference_mismatch"):
        load_scan(layout, checkpoint)


@pytest.mark.parametrize("status", [301, 403, 429, 503])
def test_watch_http_is_one_attempt_no_redirect_no_retry(tmp_path: Path, status: int) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.extensions["timeout"]["read"] == 10
        return httpx.Response(status, content=b"blocked", headers={"Location": "https://invalid"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = SecFilingClient(
            user_agent=AGENT, client=http, throttle=SecThrottle(interval=1, sleep=lambda _: None)
        )
        with pytest.raises(SecBoundedAccessError):
            fetch_index(DataLayout(tmp_path), client, day=DAY, retrieved_at=lambda: OBSERVED)
    assert len(calls) == 1
    assert any(p.read_bytes() == b"blocked" for p in (tmp_path / "raw/objects").glob("*/*"))
    assert all(AGENT not in p.read_text() for p in (tmp_path / "raw/manifests").glob("*.json"))


def test_response_size_limit_and_no_substitutions() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"123456")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = SecFilingClient(
            user_agent=AGENT, client=http, throttle=SecThrottle(interval=1, sleep=lambda _: None)
        )
        assert fetch_watch_resource(client, index_url(DAY), max_bytes=6) == b"123456"
        with pytest.raises(SecBoundedAccessError, match="size_bound") as error:
            fetch_watch_resource(client, index_url(DAY), max_bytes=5)
        assert error.value.content == b"123456"
        with pytest.raises(ValueError):
            fetch_watch_resource(client, "https://www.sec.gov/search", max_bytes=6)
    assert len(calls) == 2


def test_offline_discovery_cli_and_missing_live_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAGGED_CLAWS_SEC_LIVE", raising=False)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    runner = CliRunner()
    checkpoint = tmp_path / "scan.json"
    args = [
        "discover-sec-purchases",
        "--index-day",
        DAY.isoformat(),
        "--checkpoint",
        str(checkpoint),
        "--data-dir",
        str(tmp_path / "data"),
    ]
    result = runner.invoke(app, [*args, "--live"])
    assert result.exit_code == 2
    assert json.loads(result.output) == {
        "status": "rejected",
        "reason": "live_sec_configuration_missing",
    }
    assert not checkpoint.exists()
    index = tmp_path / "master.idx"
    index.write_bytes(index_bytes())
    bodies = tmp_path / "bodies"
    bodies.mkdir()
    (bodies / f"{ACCESSION}.txt").write_bytes(purchase_bytes())
    (bodies / f"{SECOND}.txt").write_bytes(purchase_bytes(accession=SECOND))
    result = runner.invoke(
        app,
        [
            *args,
            "--index-file",
            str(index),
            "--filings-dir",
            str(bodies),
            "--retrieved-at",
            OBSERVED.isoformat(),
            "--max-filings",
            "1",
            "--acceptance-timezone",
            "America/New_York",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["remaining_unprocessed_count"] == 1
    result = runner.invoke(
        app,
        [
            *args,
            "--filings-dir",
            str(bodies),
            "--max-filings",
            "1",
            "--acceptance-timezone",
            "America/New_York",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["remaining_unprocessed_count"] == 0


def test_raw_index_object_is_exact_and_empty_index_is_not_market_census(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    raw = index_bytes(rows=[])
    scan = capture_index(layout, raw, day=DAY, retrieved_at=OBSERVED)
    summary = scan.completeness(layout, as_of=AS_OF)
    assert summary.discovered_form4_count == summary.processed_filing_count == 0
    assert summary.index_processing_complete and summary.market_coverage == "unknown"
    from ragged_claws.storage import load_manifest

    manifest = load_manifest(layout, scan.index_capture_id)
    assert raw_object_path(layout, manifest.content_hash.value).read_bytes() == raw


def test_later_scan_progress_never_leaks_into_earlier_completeness(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    scan = capture_index(layout, index_bytes(), day=DAY, retrieved_at=OBSERVED)
    late = AS_OF.replace(day=12)
    scan = process_scan(
        layout,
        scan,
        checkpoint=tmp_path / "scan.json",
        fetch=lambda _: purchase_bytes(),
        limit=1,
        now=lambda: late,
    )
    early = scan.completeness(layout, as_of=AS_OF)
    assert early.cursor == early.processed_filing_count == early.successfully_ingested_count == 0
    assert early.remaining_unprocessed_count == 2
    assert scan.completeness(layout, as_of=late).processed_filing_count == 1
    with pytest.raises(ValueError, match="not observed"):
        scan.completeness(layout, as_of=OBSERVED.replace(hour=11))


def test_crash_after_ingestion_before_checkpoint_replays_without_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ragged_claws.watch.discovery as discovery

    layout = DataLayout(tmp_path)
    scan = capture_index(layout, index_bytes(), day=DAY, retrieved_at=OBSERVED)
    checkpoint = tmp_path / "scan.json"
    original = discovery.save_scan

    def interrupted(state: discovery.DiscoveryScan, path: Path) -> None:
        if state.cursor:
            raise OSError("invented checkpoint interruption")
        original(state, path)

    monkeypatch.setattr(discovery, "save_scan", interrupted)
    with pytest.raises(OSError, match="checkpoint interruption"):
        process_scan(
            layout,
            scan,
            checkpoint=checkpoint,
            fetch=lambda _: purchase_bytes(),
            limit=1,
            now=lambda: OBSERVED,
            acceptance_timezone="America/New_York",
        )
    assert load_scan(layout, checkpoint).cursor == 0
    first = CanonicalParquetStore(layout).load(Event)
    monkeypatch.setattr(discovery, "save_scan", original)
    replay = process_scan(
        layout,
        load_scan(layout, checkpoint),
        checkpoint=checkpoint,
        fetch=lambda _: purchase_bytes(),
        limit=1,
        now=lambda: AS_OF.replace(day=12),
        acceptance_timezone="America/New_York",
    )
    assert replay.cursor == 1
    assert CanonicalParquetStore(layout).load(Event) == first


@pytest.mark.parametrize(
    "opt_in,agent",
    [
        (None, None),
        (None, AGENT),
        ("0", AGENT),
        ("1", None),
        ("1", ""),
    ],
)
def test_explicit_live_missing_configuration_rejects_without_requests_or_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    opt_in: str | None,
    agent: str | None,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> httpx.Response:
        pytest.fail("misconfigured live invocation must not issue any request")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setenv("INVENTED_PRIVATE_TEST_VALUE", "DO_NOT_EXPOSE_TEST_VALUE")
    for key, value in (("RAGGED_CLAWS_SEC_LIVE", opt_in), ("SEC_USER_AGENT", agent)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    checkpoint = tmp_path / "private-checkpoint.json"
    result = CliRunner().invoke(
        app,
        [
            "discover-sec-purchases",
            "--live",
            "--index-day",
            "2024-09-11",
            "--checkpoint",
            str(checkpoint),
            "--data-dir",
            str(tmp_path / "data"),
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.output) == {
        "status": "rejected",
        "reason": "live_sec_configuration_missing",
    }
    assert AGENT not in result.output and "DO_NOT_EXPOSE_TEST_VALUE" not in result.output
    assert str(tmp_path) not in result.output
    assert not checkpoint.exists() and not (tmp_path / "data").exists()


@pytest.mark.parametrize("agent", ["bad-header-DO_NOT_EXPOSE", AGENT])
def test_invalid_live_configuration_is_nonzero_safe_and_network_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> httpx.Response:
        pytest.fail("invalid live configuration must not issue any request")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setenv("RAGGED_CLAWS_SEC_LIVE", "1")
    monkeypatch.setenv("SEC_USER_AGENT", agent)
    result = CliRunner().invoke(
        app,
        [
            "discover-sec-purchases",
            "--live",
            "--index-day",
            "2024-09-11",
            "--checkpoint",
            str(tmp_path / "checkpoint.json"),
            "--data-dir",
            str(tmp_path / "data"),
        ],
    )
    assert result.exit_code == 2
    assert agent not in result.output and str(tmp_path) not in result.output
    assert not (tmp_path / "checkpoint.json").exists()


def test_denied_live_request_is_nonzero_with_no_retry_or_contact_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ragged_claws.ingestion.sec_http as sec_http

    calls = []

    def denied(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(403, content=b"invented access denial")

    constructor = sec_http.SecFilingClient
    with httpx.Client(transport=httpx.MockTransport(denied)) as http:

        def mock_client(
            *, user_agent: str, throttle: SecThrottle, max_attempts: int
        ) -> SecFilingClient:
            return constructor(
                user_agent=user_agent, throttle=throttle, max_attempts=max_attempts, client=http
            )

        monkeypatch.setattr(sec_http, "SecFilingClient", mock_client)
        monkeypatch.setenv("RAGGED_CLAWS_SEC_LIVE", "1")
        monkeypatch.setenv("SEC_USER_AGENT", AGENT)
        result = CliRunner().invoke(
            app,
            [
                "discover-sec-purchases",
                "--live",
                "--index-day",
                "2024-09-11",
                "--checkpoint",
                str(tmp_path / "checkpoint.json"),
                "--data-dir",
                str(tmp_path / "data"),
            ],
        )
    assert result.exit_code == 2
    assert len(calls) == 1
    assert AGENT not in result.output and str(tmp_path) not in result.output
    assert not (tmp_path / "checkpoint.json").exists()
