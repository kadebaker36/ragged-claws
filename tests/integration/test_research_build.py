"""Frozen assembly/PIT/registration regressions. All complete-price support is invented."""

import json
import shutil
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from pathlib import Path, PureWindowsPath
from typing import cast

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from ragged_claws.cli import app
from ragged_claws.models import (
    Event,
    FinancialValue,
    FinancialValueKind,
    Listing,
    ObservationRole,
    Outcome,
    Relationship,
    RetentionClass,
    SourceLineage,
    SourceObservation,
)
from ragged_claws.outcomes.engine import RETURN_CONTEXT
from ragged_claws.research.build import build, distribution
from ragged_claws.research.examples import ident, prepare_sec, prepare_synthetic
from ragged_claws.research.models import (
    BuildConfig,
    Controls,
    OriginInventory,
    Period,
    PriceInputs,
    Protocol,
    ResearchRow,
)
from ragged_claws.research.protocol import (
    check_configuration,
    finish_attempt,
    register,
    registration_path,
    start_attempt,
)
from ragged_claws.research.snapshot import (
    ResearchError,
    encoded,
    environment,
    freeze,
    inventory_for,
    model_hash,
    read_inputs,
    verify_snapshot,
)
from ragged_claws.resolution import day_value
from ragged_claws.storage import (
    CanonicalConflictError,
    CanonicalParquetStore,
    DataLayout,
    PersistenceError,
    capture_raw_bytes,
    load_envelope_records,
)

ROOT = Path(__file__).parents[2]
PROTOCOL = ROOT / "research" / "hypotheses" / "sec-p-s-v1.json"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("invented_research_prepared")
    prepare_synthetic(target, PROTOCOL)
    return target


def clone(prepared: Path, target: Path) -> Path:
    shutil.copytree(prepared, target)
    return target


def refresh_origins(root: Path, *, origin: str = "synthetic") -> None:
    (root / "origins.json").write_bytes(
        encoded(
            inventory_for(
                read_inputs(root), origin, "Invented test declarations; no real approval."
            )
        )
    )


def rows_at(output: Path, snapshot_id: object) -> tuple[ResearchRow, ...]:
    return load_envelope_records(
        output / str(snapshot_id) / "research_rows.parquet",
        model_type=ResearchRow,
        id_field="row_id",
        dataset_kind="staging",
        model_schema_version="1.0.0",
    )


@pytest.fixture(scope="module")
def assembled(prepared: Path, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, Path]:
    root = tmp_path_factory.mktemp("invented_research_results")
    frozen, output, registry = root / "frozen", root / "output", root / "registry"
    freeze(prepared, frozen)
    build(frozen, output, registry)
    return frozen, output, registry


def test_all_events_horizons_statuses_exact_returns_and_source_dependence(
    assembled: tuple[Path, Path, Path],
) -> None:
    frozen, output, _ = assembled
    snapshot = verify_snapshot(frozen)
    rows = rows_at(output, snapshot.snapshot_id)
    report = json.loads((output / str(snapshot.snapshot_id) / "report.json").read_bytes())
    assert len(rows) == 11 * 3
    assert {r.horizon_sessions for r in rows} == {20, 60, 90}
    assert report["mode"] == "synthetic" and "INVENTED" in report["interpretation"]
    assert report["input_events"] == 11 and report["qualifying_events"] == 10
    assert report["distinct_known_issuers"] == 7
    assert report["issuer_event_counts"][str(ident(101))] == 5
    assert report["unresolved_vendor_source_rows"] == 2 and report["vendor_snapshot_versions"] == 1
    assert report["possible_repeated_vendor_rows"] == 1  # not two new canonical events
    for item in report["horizons"]:
        assert item["denominator"] == sum(item["counts"].values()) == 11
        assert item["counts"] == {
            "complete": 3,
            "right_censored": 2,
            "unresolved_security": 1,
            "missing_price": 1,
            "terminal_delisted": 1,
            "excluded": 2,
            "rejected": 1,
        }
        assert item["spy_excess"]["n"] == 3
    complete = next(r for r in rows if r.event.event_id == ident(1) and r.horizon_sessions == 20)
    assert complete.outcome is not None
    assert complete.outcome.security_return == Decimal("0.1")
    assert complete.outcome.benchmark_return == Decimal("0.01")
    assert complete.outcome.excess_return == Decimal("0.09")
    assert (
        complete.primary_families == ("synthetic.primary",)
        and complete.normalized_vendor_observations == 1
    )
    assert len(complete.event_evidence_ids) == 2  # no second Event or primary vote
    assert complete.event.actors[0].role == "reporting_lawmaker"
    assert complete.event.actors[1].role == "transaction_owner"
    assert complete.event.actors[0].entity_id != complete.event.actors[1].entity_id
    assert "known_relationship_context" in complete.unavailable_features
    assert {feature.name for feature in complete.features} == {"event_type", "reported_shares"}
    assert all("future" not in feature.name for r in rows for feature in r.features)
    missing = next(r for r in rows if r.event.event_id == ident(4))
    terminal = next(r for r in rows if r.event.event_id == ident(5))
    assert missing.status == "missing_price" and terminal.status == "terminal_delisted"
    for row in (missing, terminal):
        assert (
            row.outcome is not None
            and row.outcome.security_return is row.outcome.excess_return is None
        )
    non_actionable = next(r for r in rows if r.event.event_id == ident(8))
    future_entry = next(r for r in rows if r.event.event_id == ident(9))
    assert non_actionable.outcome is None and non_actionable.reason == "missing_actionable_time"
    assert future_entry.status == "right_censored" and future_entry.outcome is None
    assert "no_outcome_fabricated" in (future_entry.reason or "")
    renamed = next(r for r in rows if r.event.event_id == ident(1) and r.horizon_sessions == 90)
    assert renamed.listing_history_ids == (ident(2011),)
    assert renamed.outcome is not None and renamed.outcome.listing_id == ident(2001)
    price_sources = renamed.outcome.methodology.price_source_observation_ids
    prices = read_inputs(frozen).prices
    assert any(
        bar.listing_id == ident(2011) and bar.source_observation_id in price_sources
        for packet in prices.packets
        for bar in packet.batch.bars
    )


def test_distributions_and_unavailable_statistics() -> None:
    result = distribution([Decimal("0.09"), Decimal("0.09"), Decimal("-0.11")])
    with localcontext(RETURN_CONTEXT):
        assert result.mean == Decimal("0.07") / 3
    assert result.median == result.maximum == result.p90_nearest_rank == Decimal("0.09")
    assert result.minimum == result.p10_nearest_rank == Decimal("-0.11")
    assert distribution([]).mean is distribution([]).median is None


def test_idempotent_regeneration_portable_inputs_and_strict_outputs(
    assembled: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    frozen, output, registry = assembled
    snapshot = verify_snapshot(frozen)
    target = output / str(snapshot.snapshot_id)
    before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    copied = clone(frozen, tmp_path / "portable-copy")
    build(copied, output, registry)
    assert before == {
        p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()
    }
    assert all(
        not Path(item.path).is_absolute() and ".." not in Path(item.path).parts
        for item in snapshot.files
    )
    assert not (
        frozen / "data" / "cache"
    ).exists()  # read-only loading did not create catalog state
    independent_output = tmp_path / "new-output"
    build(copied, independent_output, tmp_path / "independent-registry")
    assert before == {
        p.relative_to(independent_output / str(snapshot.snapshot_id)): p.read_bytes()
        for p in (independent_output / str(snapshot.snapshot_id)).rglob("*")
        if p.is_file()
    }
    store = CanonicalParquetStore(DataLayout(frozen / "data"), read_only=True)
    with pytest.raises(PersistenceError):
        store.persist(Event, store.load(Event))
    with pytest.raises(CanonicalConflictError):
        from ragged_claws.research.snapshot import write_once

        write_once(target / "report.json", b"different payload")


def test_new_coverage_has_new_outcome_scope_and_preserves_censored_run(
    assembled: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    old_frozen, output, _ = assembled
    old = verify_snapshot(old_frozen)
    before = (output / str(old.snapshot_id) / "curated" / "outcome.parquet").read_bytes()
    prepared = tmp_path / "matured"
    prepare_synthetic(prepared, PROTOCOL, coverage=date(2024, 12, 31))
    new = freeze(prepared, tmp_path / "frozen")
    build(tmp_path / "frozen", output, tmp_path / "registry")
    old_row = next(
        r
        for r in rows_at(output, old.snapshot_id)
        if r.event.event_id == ident(10) and r.horizon_sessions == 60
    )
    new_row = next(
        r
        for r in rows_at(output, new.snapshot_id)
        if r.event.event_id == ident(10) and r.horizon_sessions == 60
    )
    assert old.snapshot_id != new.snapshot_id
    assert old_row.status == "right_censored" and new_row.status == "complete"
    assert old_row.outcome is not None and new_row.outcome is not None
    assert old_row.outcome.outcome_id != new_row.outcome.outcome_id
    assert old_row.outcome.methodology.methodology_id != new_row.outcome.methodology.methodology_id
    assert (output / str(old.snapshot_id) / "curated" / "outcome.parquet").read_bytes() == before
    assert not CanonicalParquetStore(DataLayout(prepared / "data"), read_only=True).load(Outcome)


def test_recorded_sec_diagnostic_is_real_source_without_invented_prices(tmp_path: Path) -> None:
    prepared = tmp_path / "sec"
    prepare_sec(
        prepared,
        ROOT / "tests/fixtures/sec/0000950170-24-105263.txt",
        ROOT / "tests/fixtures/sec/provenance.json",
        PROTOCOL,
        as_of=datetime(2026, 10, 22, 23, tzinfo=UTC),
    )
    snapshot = freeze(prepared, tmp_path / "frozen")
    report = build(tmp_path / "frozen", tmp_path / "output", tmp_path / "registry")
    assert report.mode == "diagnostic" and report.protocol_status == "proposal_unregistered"
    assert (
        report.input_events == report.qualifying_events == 3 and report.distinct_known_issuers == 1
    )
    assert not read_inputs(tmp_path / "frozen").prices.packets
    for horizon in report.horizons:
        assert horizon.counts["unresolved_security"] == 3 and sum(horizon.counts.values()) == 3
        assert horizon.spy_excess.n == 0 and horizon.spy_excess.mean is None
    rows = rows_at(tmp_path / "output", snapshot.snapshot_id)
    assert all(r.outcome is None and r.event.event_type == "equity_sale" for r in rows)
    observed = read_inputs(tmp_path / "frozen").get(SourceObservation)
    assert (
        observed[0].raw_content_hash.value
        == "5eb55738b2b6e3a2e76cb6ffcbfb6e415dbc5c7af763c9c6ced9e30e7171e732"
    )
    assert not (tmp_path / "registry" / "registrations").exists()


@pytest.mark.parametrize(
    "dataset", ["Security", "Listing", "Provenance", "price_packet", "identity_binding"]
)
def test_synthetic_support_anywhere_cannot_enter_real_validation(
    prepared: Path, tmp_path: Path, dataset: str
) -> None:
    copied = clone(prepared, tmp_path / "prepared")
    inputs = read_inputs(copied)
    (copied / "config.json").write_bytes(
        encoded(
            inputs.config.model_copy(
                update={"mode": "validation", "period": inputs.protocol.validation}
            )
        )
    )
    inventory = inventory_for(
        read_inputs(copied), "recorded_public", "Invented mislabel test, not real evidence."
    )
    records = list(inventory.records)
    index = next(i for i, r in enumerate(records) if r.dataset == dataset)
    records[index] = records[index].model_copy(update={"origin": "synthetic"})
    (copied / "origins.json").write_bytes(encoded(OriginInventory(records=tuple(records))))
    with pytest.raises(ResearchError, match="synthetic support"):
        freeze(copied, tmp_path / "frozen")


def empty_real(prepared: Path, mode: str = "validation") -> Protocol:
    prepared.mkdir()
    protocol = Protocol.model_validate_json(PROTOCOL.read_bytes())
    config = BuildConfig.model_validate_json(
        encoded(
            {
                "mode": mode,
                "hypothesis_id": protocol.hypothesis_id,
                "protocol_version": protocol.version,
                "period": (
                    protocol.validation if mode == "validation" else protocol.discovery
                ).model_dump(mode="json"),
                "as_of": "2026-10-22T23:00:00Z",
                "coverage_through": "2026-10-22",
                "features": list(protocol.features),
                "feed": "iex",
                "adjustment": "all",
            }
        )
    )
    for name, value in (
        ("config", config),
        ("protocol", protocol),
        ("controls", Controls()),
        ("prices", PriceInputs()),
        ("origins", OriginInventory(records=())),
    ):
        (prepared / f"{name}.json").write_bytes(encoded(value))
    return protocol


def test_proposal_is_not_registration_and_validation_denial_is_logged(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    protocol = empty_real(prepared)
    frozen = tmp_path / "frozen"
    freeze(prepared, frozen)
    registry = tmp_path / "registry"
    with pytest.raises(ResearchError, match="not been reviewed and registered"):
        build(frozen, tmp_path / "output", registry)
    attempts = list((registry / "attempts").glob("*.finished.json"))
    assert (
        len(attempts) == 1 and json.loads(attempts[0].read_bytes())["outcome_inspection"] is False
    )
    assert not registration_path(registry, model_hash(protocol)).exists()
    with pytest.raises(ResearchError, match="approval"):
        register(
            protocol,
            prepared / "origins.json",
            registry,
            approval_reference="",
            attest_uninspected=False,
        )


def test_registration_exact_match_mismatches_and_prior_inspection_gate(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    protocol = empty_real(prepared)
    registry = tmp_path / "registry"
    approved = register(
        protocol,
        prepared / "origins.json",
        registry,
        approval_reference="fixture://invented-test-approval-only",
        attest_uninspected=True,
    )
    assert (
        register(
            protocol,
            prepared / "origins.json",
            registry,
            approval_reference="fixture://invented-test-approval-only",
            attest_uninspected=True,
        )
        == approved
    )
    frozen = tmp_path / "frozen"
    freeze(prepared, frozen)
    with pytest.raises(ResearchError, match="separate supervisor analysis approval"):
        build(frozen, tmp_path / "output", registry)
    # Old registrations remain readable, but cannot authorize a newly added analysis.
    assert not (tmp_path / "output").exists()
    with pytest.raises(ResearchError, match="immutable"):
        register(
            protocol,
            prepared / "origins.json",
            registry,
            approval_reference="different approval",
            attest_uninspected=True,
        )
    renamed = protocol.model_copy(update={"hypothesis_id": "renamed-after-inspection"})
    # Independently declared test inspection still prevents a renamed untouched claim.
    inspection = start_attempt(registry, verify_snapshot(frozen))
    finish_attempt(inspection, inspected=True, success=True)
    with pytest.raises(ResearchError, match="previously or potentially inspected"):
        register(
            renamed,
            prepared / "origins.json",
            registry,
            approval_reference="fixture://invented-later-approval",
            attest_uninspected=True,
        )


@pytest.mark.parametrize("mutation", ["period", "feature", "origin_review"])
def test_validation_rejects_undeclared_period_features_or_origin_review(
    tmp_path: Path, mutation: str
) -> None:
    prepared = tmp_path / "prepared"
    protocol = empty_real(prepared)
    registry = tmp_path / "registry"
    registration = register(
        protocol,
        prepared / "origins.json",
        registry,
        approval_reference="fixture://invented",
        attest_uninspected=True,
    )
    inputs = read_inputs(prepared)
    if mutation == "period":
        config = inputs.config.model_copy(
            update={"period": Period(start=date(2024, 1, 1), end=date(2024, 12, 31))}
        )
        (prepared / "config.json").write_bytes(encoded(config))
    elif mutation == "feature":
        (prepared / "config.json").write_bytes(
            encoded(inputs.config.model_copy(update={"features": ("event_type",)}))
        )
    else:
        path = registration_path(registry, model_hash(protocol))
        path.write_bytes(
            encoded(registration.model_copy(update={"origin_inventory_sha256": "a" * 64}))
        )
    freeze(prepared, tmp_path / "frozen")
    with pytest.raises(ResearchError):
        build(tmp_path / "frozen", tmp_path / "output", registry)
    assert not (tmp_path / "output").exists()


def test_bad_future_feature_names_are_schema_rejected(prepared: Path) -> None:
    payload = json.loads((prepared / "config.json").read_bytes())
    payload["features"] = ["event_type", "ExcessReturn", "new_future_metric"]
    with pytest.raises(ValidationError):
        BuildConfig.model_validate_json(encoded(payload))


def test_tampered_snapshot_and_missing_raw_fail_before_returns_and_are_logged(
    assembled: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    frozen, _, _ = assembled
    copied = clone(frozen, tmp_path / "copy")
    snapshot = verify_snapshot(copied)
    raw = next(item for item in snapshot.files if "/raw/objects/" in item.path)
    (copied / raw.path).write_bytes(b"corrupt")
    registry = tmp_path / "registry"
    with pytest.raises(ResearchError, match="changed"):
        build(copied, tmp_path / "output", registry)
    attempt = next((registry / "attempts").glob("*.finished.json"))
    assert json.loads(attempt.read_bytes())["outcome_inspection"] is False


def test_context_positive_requires_known_time_and_preserves_unavailable_as_unknown(
    prepared: Path, tmp_path: Path
) -> None:
    copied = clone(prepared, tmp_path / "prepared")
    store = CanonicalParquetStore(DataLayout(copied / "data"))
    relation = store.load(Relationship)[0]
    store.persist(
        Relationship,
        (
            relation.model_copy(
                update={"relationship_id": ident(5999), "known_from": day_value(date(2023, 1, 1))}
            ),
        ),
    )
    refresh_origins(copied)
    snapshot = freeze(copied, tmp_path / "frozen")
    from ragged_claws.research.build import features_for

    inputs = read_inputs(tmp_path / "frozen")
    event = next(e for e in inputs.get(Event) if e.event_id == ident(1))
    features, unavailable = features_for(inputs, event, snapshot.snapshot_id)
    assert next(f for f in features if f.name == "known_relationship_context").value == 1
    assert "known_relationship_context" not in unavailable


def test_cli_empty_registered_gate_reports_failure(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    empty_real(prepared)
    freeze(prepared, tmp_path / "frozen")
    result = CliRunner().invoke(
        app,
        [
            "research-build",
            str(tmp_path / "frozen"),
            "--output",
            str(tmp_path / "output"),
            "--registry",
            str(tmp_path / "registry"),
        ],
    )
    assert result.exit_code == 2 and json.loads(result.output)["rejected_build"] == 1


def test_code_fingerprint_change_rejects_frozen_inputs(
    assembled: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen, _, _ = assembled
    _, lock, runtime = environment()
    monkeypatch.setattr(
        "ragged_claws.research.snapshot.environment", lambda: ("a" * 64, lock, runtime)
    )
    with pytest.raises(ResearchError, match="environment differs"):
        verify_snapshot(frozen)


def test_output_cannot_mutate_the_frozen_input_tree(assembled: tuple[Path, Path, Path]) -> None:
    frozen, _, _ = assembled
    with pytest.raises(ResearchError, match="overlap"):
        build(frozen, frozen / "results", frozen / "journal")


def test_shares_feature_does_not_promote_a_price_to_quantity(prepared: Path) -> None:
    inputs = read_inputs(prepared)
    event = inputs.get(Event)[0].model_copy(
        update={
            "financial_values": (
                FinancialValue(
                    name="transaction_shares",
                    kind=FinancialValueKind.UNIT_PRICE,
                    value=Decimal("50"),
                    currency="USD",
                    unit="shares",
                ),
            )
        }
    )
    from ragged_claws.research.build import features_for

    features, unavailable = features_for(inputs, event, ident(99999))
    assert "reported_shares" in unavailable
    assert not any(feature.name == "reported_shares" for feature in features)


def add_restricted_source(prepared: Path, *, credentials: bool = False) -> None:
    store = CanonicalParquetStore(DataLayout(prepared / "data"))
    now = read_inputs(prepared).config.as_of
    capture = capture_raw_bytes(
        store.layout,
        b"INVENTED restricted-source guard test; no licensed records",
        provider_namespace="synthetic.restricted",
        source_family="synthetic.restricted",
        source_native_id="INVENTED",
        retrieved_at=now,
        adapter_version="invented/1",
        retention_class=RetentionClass.RESTRICTED,
        request_parameters={"api_key": "INVENTED-NOT-A-REAL-CREDENTIAL"} if credentials else {},
    )
    observation = SourceObservation(
        source_observation_id=ident(98765),
        provider_namespace="synthetic.restricted",
        source_native_id="INVENTED",
        lineage=SourceLineage(
            source_family="synthetic.restricted", observation_role=ObservationRole.SYNTHETIC
        ),
        observed_at=now,
        retrieved_at=now,
        raw_content_hash=capture.content_hash,
        adapter_version="invented/1",
        retention_class=RetentionClass.RESTRICTED,
    )
    store.persist(SourceObservation, (observation,))
    refresh_origins(prepared)


def permit_invented_restricted(root: Path) -> None:
    config = read_inputs(root).config.model_copy(
        update={
            "output_rights": "private_only",
            "restricted_raw_retention_permitted": True,
            "restricted_derivatives_permitted": True,
            "license_review_reference": "fixture://invented-review-not-real-permission",
        }
    )
    (root / "config.json").write_bytes(encoded(config))


def test_restricted_upstream_and_derivatives_require_private_non_sync_roots(
    prepared: Path, tmp_path: Path
) -> None:
    copied = clone(prepared, tmp_path / "prepared")
    add_restricted_source(copied)
    with pytest.raises(ResearchError, match="reviewed upstream"):
        freeze(copied, tmp_path / "frozen")
    config = read_inputs(copied).config.model_copy(
        update={
            "output_rights": "private_only",
            "restricted_raw_retention_permitted": True,
            "restricted_derivatives_permitted": True,
            "license_review_reference": "fixture://invented-review-not-permission-for-real-data",
        }
    )
    (copied / "config.json").write_bytes(encoded(config))
    with pytest.raises(ResearchError, match="sync"):
        freeze(copied, tmp_path / "OneDrive" / "frozen")
    (tmp_path / "fake-git" / ".git").mkdir(parents=True)
    with pytest.raises(ResearchError, match="outside Git"):
        freeze(copied, tmp_path / "fake-git" / "frozen")
    frozen = tmp_path / "private-frozen"
    freeze(copied, frozen)
    with pytest.raises(ResearchError, match="sync"):
        build(frozen, tmp_path / "OneDrive" / "output", tmp_path / "private-registry")


def test_capture_credentials_rejected_before_snapshot_publication(
    prepared: Path, tmp_path: Path
) -> None:
    copied = clone(prepared, tmp_path / "prepared")
    add_restricted_source(copied, credentials=True)
    permit_invented_restricted(copied)
    with pytest.raises(ResearchError, match="credential-bearing") as error:
        freeze(copied, tmp_path / "frozen")
    assert "INVENTED-NOT-A-REAL-CREDENTIAL" not in str(error.value)
    assert not (tmp_path / "frozen").exists()


def test_noncompleted_coverage_is_rejected_before_outcomes(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    empty_real(prepared, mode="discovery")
    inputs = read_inputs(prepared)
    (prepared / "config.json").write_bytes(
        encoded(inputs.config.model_copy(update={"as_of": datetime(2026, 10, 22, 15, tzinfo=UTC)}))
    )
    freeze(prepared, tmp_path / "frozen")
    with pytest.raises(ResearchError, match="not completed"):
        build(tmp_path / "frozen", tmp_path / "output", tmp_path / "registry")


def test_horizon_embargo_prevents_discovery_spilling_into_validation(tmp_path: Path) -> None:
    protocol = empty_real(tmp_path / "prepared", mode="discovery")
    unsafe = protocol.model_copy(
        update={"validation": Period(start=date(2020, 1, 1), end=date(2021, 12, 31))}
    )
    with pytest.raises(ResearchError, match="embargo"):
        check_configuration(unsafe, read_inputs(tmp_path / "prepared").config)


def test_inspection_journal_tracks_exit_dates_not_only_event_selection(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    protocol = empty_real(prepared, mode="discovery")
    snapshot = freeze(prepared, tmp_path / "frozen")
    registry = tmp_path / "registry"
    attempt = start_attempt(registry, snapshot)
    finish_attempt(
        attempt,
        inspected=True,
        success=True,
        inspection_period=Period(start=date(2016, 1, 1), end=date(2020, 6, 1)),
    )
    revised = protocol.model_copy(
        update={
            "hypothesis_id": "renamed-hypothesis",
            "discovery": Period(start=date(2016, 1, 1), end=date(2018, 12, 31)),
            "validation": Period(start=date(2020, 1, 1), end=date(2020, 12, 31)),
        }
    )
    with pytest.raises(ResearchError, match="previously or potentially inspected"):
        register(
            revised,
            prepared / "origins.json",
            registry,
            approval_reference="fixture://invented",
            attest_uninspected=True,
        )


def test_missing_capture_manifest_cannot_be_replaced_by_hash_claims(
    prepared: Path, tmp_path: Path
) -> None:
    copied = clone(prepared, tmp_path / "prepared")
    for path in (copied / "data" / "raw" / "manifests").glob("*.json"):
        if json.loads(path.read_bytes())["provider_namespace"] == "synthetic.primary":
            path.unlink()
    with pytest.raises(ResearchError, match="capture manifest"):
        freeze(copied, tmp_path / "frozen")


def test_declared_decimal_features_roundtrip_without_becoming_text(
    assembled: tuple[Path, Path, Path],
) -> None:
    frozen, output, _ = assembled
    snapshot = verify_snapshot(frozen)
    rows = rows_at(output, snapshot.snapshot_id)
    assert isinstance(
        next(
            feature.value
            for row in rows
            for feature in row.features
            if feature.name == "reported_shares"
        ),
        Decimal,
    )


def test_future_entry_censoring_cannot_hide_expired_listing(
    assembled: tuple[Path, Path, Path],
) -> None:
    from dataclasses import replace

    from ragged_claws.research.build import assemble

    frozen, _, _ = assembled
    inputs = read_inputs(frozen)
    event = next(e for e in inputs.get(Event) if e.event_id == ident(9))
    binding = next(b for b in inputs.controls.bindings if b.event_id == event.event_id)
    records = dict(inputs.records)
    records["Listing"] = tuple(
        item.model_copy(update={"effective_to": day_value(date(2024, 7, 1))})
        if item.listing_id == binding.listing_id
        else item
        for item in inputs.get(Listing)
    )
    # No price math is needed: an invalid entry identity must fail before censoring.
    rows, _ = assemble(replace(inputs, records=records), verify_snapshot(frozen))
    future = [r for r in rows if r.event.event_id == event.event_id]
    assert len(future) == 3
    assert all(r.status == "rejected" and r.outcome is None for r in future)
    assert all(r.reason == "entry_outside_source_backed_listing_interval" for r in future)


def test_cli_model_rejection_does_not_echo_input_payload(tmp_path: Path) -> None:
    protocol = tmp_path / "invalid.json"
    protocol.write_text('{"private_payload": "INVENTED-PRIVATE-CONTENT"}')
    result = CliRunner().invoke(
        app,
        [
            "research-prepare-synthetic",
            "--protocol",
            str(protocol),
            "--output",
            str(tmp_path / "prepared"),
        ],
    )
    assert result.exit_code == 2
    assert "INVENTED-PRIVATE-CONTENT" not in result.output
    assert json.loads(result.output)["preparation_rejected"] == 1


@pytest.mark.parametrize("location", ["OneDrive", "fake-git"])
def test_restricted_preparation_location_rejected_before_graph_processing(
    prepared: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    parent = tmp_path / location
    parent.mkdir()
    if location == "fake-git":
        (parent / ".git").mkdir()
    copied = clone(prepared, parent / "prepared")
    add_restricted_source(copied)
    permit_invented_restricted(copied)

    def unexpected_graph(_: object) -> None:
        pytest.fail("restricted input must be rejected before raw/staging graph processing")

    monkeypatch.setattr("ragged_claws.research.snapshot.verify_graph", unexpected_graph)
    with pytest.raises(ResearchError, match="sync|Git/shared"):
        freeze(copied, tmp_path / "private-frozen")
    assert copied.exists() and not (tmp_path / "private-frozen").exists()


@pytest.mark.parametrize("location", ["OneDrive", "fake-git"])
def test_relocated_restricted_snapshot_rejects_verification_and_build(
    prepared: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    copied = clone(prepared, tmp_path / "prepared")
    add_restricted_source(copied)
    permit_invented_restricted(copied)
    original = tmp_path / "private-frozen"
    freeze(copied, original)
    before = (original / "snapshot.json").read_bytes()
    parent = tmp_path / location
    parent.mkdir()
    if location == "fake-git":
        (parent / ".git").mkdir()
    relocated = clone(original, parent / "frozen")

    def unexpected_graph(_: object) -> None:
        pytest.fail("relocated restricted input must be rejected before graph processing")

    monkeypatch.setattr("ragged_claws.research.snapshot.verify_graph", unexpected_graph)
    with pytest.raises(ResearchError, match="sync|Git/shared"):
        verify_snapshot(relocated)
    registry = tmp_path / "private-registry"
    with pytest.raises(ResearchError, match="sync|Git/shared"):
        build(relocated, tmp_path / "private-output", registry)
    assert not (tmp_path / "private-output").exists()
    assert all(
        not json.loads(path.read_bytes())["outcome_inspection"]
        for path in (registry / "attempts").glob("*.finished.json")
    )
    assert (original / "snapshot.json").read_bytes() == before
    assert relocated.exists()


def test_restricted_snapshot_can_relocate_between_private_roots(
    prepared: Path, tmp_path: Path
) -> None:
    copied = clone(prepared, tmp_path / "private-prepared")
    add_restricted_source(copied)
    permit_invented_restricted(copied)
    original = tmp_path / "private-frozen"
    snapshot = freeze(copied, original)
    relocated = clone(original, tmp_path / "other-private-frozen")
    assert verify_snapshot(relocated) == snapshot
    output, registry = tmp_path / "private-output", tmp_path / "private-registry"
    first = build(original, output, registry)
    before = (output / str(snapshot.snapshot_id) / "result.json").read_bytes()
    assert build(relocated, output, registry) == first
    assert (output / str(snapshot.snapshot_id) / "result.json").read_bytes() == before


def test_public_source_snapshot_remains_portable_to_sync_and_git_roots(tmp_path: Path) -> None:
    prepared = tmp_path / "public-prepared"
    prepare_sec(
        prepared,
        ROOT / "tests/fixtures/sec/0000950170-24-105263.txt",
        ROOT / "tests/fixtures/sec/provenance.json",
        PROTOCOL,
        as_of=datetime(2026, 10, 22, 23, tzinfo=UTC),
    )
    original = tmp_path / "public-frozen"
    snapshot = freeze(prepared, original)
    for name in ("OneDrive", "fake-git"):
        parent = tmp_path / name
        parent.mkdir()
        if name == "fake-git":
            (parent / ".git").mkdir()
        relocated = clone(original, parent / "frozen")
        assert verify_snapshot(relocated) == snapshot
        # Public preparations at those roots may also freeze without weakening private policy.
        public_prepared = clone(prepared, parent / "prepared")
        assert freeze(public_prepared, parent / "second-frozen") == snapshot
        report = build(relocated, parent / "output", parent / "registry")
        assert report.input_events == 3
        assert all(h.counts["unresolved_security"] == 3 for h in report.horizons)


def test_private_input_metadata_guard_rejects_unc_without_network_access(
    prepared: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ragged_claws.research.snapshot import input_rights

    config = read_inputs(prepared).config.model_copy(update={"output_rights": "private_only"})

    # Simulate only the resolved anchor; no UNC directory is accessed or created.
    def shared_resolution(_: Path) -> Path:
        return cast(Path, PureWindowsPath("//invented-server/invented-share/private"))

    with monkeypatch.context() as context:
        context.setattr(Path, "resolve", shared_resolution)
        with pytest.raises(ResearchError, match="Git/shared"):
            input_rights(tmp_path / "no-input-read", config)
