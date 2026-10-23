"""Sealed offline engine-to-analysis regressions; all prices/identities are invented."""

import json
import shutil
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from ragged_claws.cli import app
from ragged_claws.durable.models import CloudPolicy, DurableError
from ragged_claws.durable.validation import validate_layout
from ragged_claws.research.analysis import evaluate
from ragged_claws.research.analysis_demo import Case, prepare_demo
from ragged_claws.research.analysis_models import AnalysisPlan, Evaluation
from ragged_claws.research.build import build
from ragged_claws.research.models import ResearchRow
from ragged_claws.research.snapshot import (
    ResearchError,
    digest,
    encoded,
    freeze,
    model_hash,
    verify_snapshot,
)
from ragged_claws.storage import load_envelope_records, persist_envelope_records

ROOT = Path(__file__).parents[2]
PROPOSAL = ROOT / "research/hypotheses/sec-p-s-v2.json"


@pytest.fixture(scope="module")
def example(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("invented_analysis")
    prepare_demo(root / "prepared", PROPOSAL, "positive")
    snapshot = freeze(root / "prepared", root / "frozen")
    build(root / "frozen", root / "research", root / "registry")
    (root / "result-path.txt").write_text(str(root / "research" / str(snapshot.snapshot_id)))
    return root


def result_at(root: Path) -> Path:
    return Path((root / "result-path.txt").read_text())


def run(root: Path, output: Path, registry: Path) -> Evaluation:
    return evaluate(root / "frozen", result_at(root), root / "analysis-plan.json", output, registry)


def test_positive_cost_cancellation_dependencies_and_stable_regeneration(example: Path) -> None:
    value = run(example, example / "analyses", example / "registry")
    assert value.conditional_verdict == "positive"
    assert value.investment_validation == "not_evaluated"
    primary = value.horizons[0]
    assert primary.bootstrap is not None
    assert (
        primary.bootstrap.contrast
        == primary.bootstrap.lower
        == primary.bootstrap.upper
        == Decimal(".25")
    )
    assert primary.bootstrap.clusters == 2 and primary.bootstrap.valid_draws == 5000
    assert set(primary.equal_cost_contrast_by_bps.values()) == {Decimal(".25")}
    assert primary.arms["equity_purchase"].complete == 3
    assert primary.arms["equity_purchase"].distinct_complete_issuers == 2
    assert sorted(primary.arms["equity_purchase"].issuer_event_counts.values()) == [1, 2]
    assert primary.arms["equity_purchase"].net_excess_means_by_bps["25"] == Decimal(".2275")
    assert primary.arms["equity_sale"].gross_excess_mean == Decimal("-.02")
    assert all(h.conditional_verdict == "not_evaluated" for h in value.horizons[1:])
    assert len(value.rows) == 18  # six economic events, three horizons, no vendor votes
    for row in value.rows:
        assert row.row.event_evidence_ids and row.row.identity_provenance_ids
        assert row.row.outcome is not None and row.row.outcome.provenance_id
        assert row.gross_excess == row.row.outcome.excess_return
        assert row.gross_excess is not None
        assert row.net_excess_by_bps["10"] == row.gross_excess - Decimal(".001")
    before = {
        p.name: digest(p.read_bytes())
        for p in (example / "analyses" / str(value.evaluation_id)).iterdir()
    }
    assert run(example, example / "analyses", example / "registry") == value
    after = {
        p.name: digest(p.read_bytes())
        for p in (example / "analyses" / str(value.evaluation_id)).iterdir()
    }
    assert before == after
    assert len(list((example / "registry/attempts").glob("*.analysis.json"))) == 2
    result = CliRunner().invoke(
        app,
        [
            "research-evaluate",
            str(example / "frozen"),
            "--result",
            str(result_at(example)),
            "--plan",
            str(example / "analysis-plan.json"),
            "--output",
            str(example / "analyses"),
            "--registry",
            str(example / "registry"),
        ],
    )
    assert result.exit_code == 0 and '"conditional_verdict": "positive"' in result.stdout


@pytest.mark.parametrize(
    ("case", "verdict"),
    [
        ("negative", "negative"),
        ("one_arm_missing", "insufficient"),
        ("no_complete", "insufficient"),
    ],
)
def test_negative_missing_one_arm_and_no_complete_retained(
    tmp_path: Path,
    case: Case,
    verdict: str,
) -> None:
    prepare_demo(tmp_path / "prepared", PROPOSAL, case)
    snapshot = freeze(tmp_path / "prepared", tmp_path / "frozen")
    build(tmp_path / "frozen", tmp_path / "research", tmp_path / "registry")
    value = evaluate(
        tmp_path / "frozen",
        tmp_path / "research" / str(snapshot.snapshot_id),
        tmp_path / "analysis-plan.json",
        tmp_path / "analyses",
        tmp_path / "registry",
    )
    assert value.conditional_verdict == verdict and value.investment_validation == "not_evaluated"
    primary = value.horizons[0]
    assert primary.bootstrap is not None and primary.reasons
    if case == "one_arm_missing":
        assert primary.arms["equity_purchase"].complete_coverage == 1
        assert primary.arms["equity_sale"].complete_coverage == 0
        assert primary.bootstrap.missing_arm_fraction == 1
    if case == "no_complete":
        assert primary.bootstrap.contrast is primary.bootstrap.lower is None
        assert all(
            r.gross_stock is None and set(r.net_stock_by_bps.values()) == {None} for r in value.rows
        )
    assert (tmp_path / "analyses" / str(value.evaluation_id) / "evaluation.json").is_file()


@pytest.mark.parametrize(
    "field",
    [
        "protocol_sha256",
        "period",
        "features",
        "feed",
        "adjustment",
        "provider",
        "purpose",
        "source_families",
    ],
)
def test_plan_mismatch_is_denied_and_journaled(example: Path, tmp_path: Path, field: str) -> None:
    plan = json.loads((example / "analysis-plan.json").read_bytes())
    changes: dict[str, object] = {
        "protocol_sha256": "a" * 64,
        "period": {"start": "2024-01-01", "end": "2024-01-31"},
        "features": ["event_type"],
        "feed": "sip",
        "adjustment": "raw",
        "provider": "alpaca.market_data",
        "purpose": "proposed_validation",
        "source_families": ["sec.ownership"],
    }
    plan[field] = changes[field]
    path = tmp_path / "plan.json"
    path.write_bytes(encoded(plan))
    with pytest.raises(ValueError):
        evaluate(
            example / "frozen", result_at(example), path, tmp_path / "out", tmp_path / "registry"
        )
    finished = list((tmp_path / "registry/attempts").glob("*.finished.json"))
    assert len(finished) == 1
    assert not json.loads(finished[0].read_bytes())["outcome_inspection"]


def reseal(path: Path) -> None:
    seal = json.loads((path / "result.json").read_bytes())
    seal["files"] = {
        p.relative_to(path).as_posix(): digest(p.read_bytes())
        for p in path.rglob("*")
        if p.is_file() and p.name != "result.json"
    }
    (path / "result.json").write_bytes(encoded(seal))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_hash",
        "wrong_hash",
        "duplicate_event",
        "alter_return",
        "missing_dependency",
        "extra_file",
    ],
)
def test_inconsistent_or_resealed_result_rejected(
    example: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    result = tmp_path / "result"
    shutil.copytree(result_at(example), result)
    if mutation == "missing_hash":
        (result / "result.json").unlink()
    elif mutation == "wrong_hash":
        (result / "report.md").write_text("corrupt")
    elif mutation == "extra_file":
        (result / "unchecked.csv").write_text("future return")
        reseal(result)
    elif mutation == "missing_dependency":
        (result / "curated/provenance.parquet").unlink()
        reseal(result)
    else:
        rows = load_envelope_records(
            result / "research_rows.parquet",
            model_type=ResearchRow,
            id_field="row_id",
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
        row = rows[0]
        if mutation == "duplicate_event":
            replacement = (*rows, row.model_copy(update={"row_id": uuid4()}))
        else:
            assert row.outcome is not None
            replacement = (
                row.model_copy(
                    update={
                        "outcome": row.outcome.model_copy(update={"excess_return": Decimal("99")})
                    }
                ),
                *rows[1:],
            )
        (result / "research_rows.parquet").unlink()
        persist_envelope_records(
            result / "research_rows.parquet",
            model_type=ResearchRow,
            id_field="row_id",
            records=replacement,
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
        reseal(result)
    with pytest.raises((ValueError, OSError)):
        evaluate(
            example / "frozen",
            result,
            example / "analysis-plan.json",
            tmp_path / "out",
            tmp_path / "registry",
        )
    assert not (tmp_path / "out").exists()
    finished = list((tmp_path / "registry/attempts").glob("*.finished.json"))
    assert len(finished) == 1 and not json.loads(finished[0].read_bytes())["success"]


def test_new_analysis_exports_fail_explicitly_instead_of_trimming(
    example: Path, tmp_path: Path
) -> None:
    value = run(example, tmp_path / "local-analysis", tmp_path / "local-registry")
    cloud = tmp_path / "cloud"
    destination = cloud / "research/analyses" / str(value.evaluation_id)
    destination.mkdir(parents=True)
    (destination / "evaluation.json").write_bytes(encoded(value))
    policy = CloudPolicy(
        scope="invented_engineering",
        review_reference="fixture://invented",
        invented_attestation=True,
    )
    with pytest.raises(DurableError):
        validate_layout(cloud, policy)


def test_previous_protocol_bytes_hash_and_serialization_unchanged() -> None:
    # Pinned accepted-main v1 bytes; no newly serialized defaults in prior models.
    old = ROOT / "research/hypotheses/sec-p-s-v1.json"
    assert digest(old.read_bytes().replace(b"\r\n", b"\n")) == (
        "68f8144842335f34b7686510553aa4e32c218c9da3ad0661e93ee75d114a8c57"
    )
    plan = AnalysisPlan.model_validate_json(
        (ROOT / "research/analysis-plans/sec-p-s-v2.json").read_bytes()
    )
    assert model_hash(plan) and plan.protocol_version == "v2"


def test_actual_prior_frozen_artifact_models_recover_original_bytes() -> None:
    from ragged_claws.research.models import Protocol, ResearchReport, Snapshot

    root = ROOT / "tests/fixtures/research/history-v1"
    manifest = json.loads((root / "manifest.json").read_bytes())
    before = {}
    for name, expected in manifest["files"].items():
        content = (root / name).read_bytes()
        assert digest(content) == expected
        before[name] = content
    for name, model in (
        ("snapshot.json", Snapshot),
        ("protocol.json", Protocol),
        ("report.json", ResearchReport),
    ):
        value = model.model_validate_json(before[name])
        assert encoded(value) == before[name]
    snapshot = Snapshot.model_validate_json(before["snapshot.json"])
    report = ResearchReport.model_validate_json(before["report.json"])
    assert snapshot.snapshot_id == report.snapshot_id
    assert snapshot.source_code_sha256 != verify_current_source()
    assert snapshot.config.mode == report.mode == "diagnostic"
    assert report.input_events == 3
    assert all(h.counts["unresolved_security"] == 3 for h in report.horizons)
    assert json.loads(before["attempt.finished.json"])["outcome_inspection"] is False
    assert all((root / name).read_bytes() == content for name, content in before.items())


def verify_current_source() -> str:
    from ragged_claws.research.snapshot import environment

    return environment()[0]


def test_old_environment_is_readable_but_not_executable(example: Path, tmp_path: Path) -> None:
    from ragged_claws.research.models import Snapshot

    shutil.copytree(example / "frozen", tmp_path / "old")
    path = tmp_path / "old/snapshot.json"
    old = Snapshot.model_validate_json(path.read_bytes()).model_copy(
        update={"source_code_sha256": "a" * 64}
    )
    content = encoded(old)
    path.write_bytes(content)
    assert Snapshot.model_validate_json(content) == old and encoded(old) == content
    with pytest.raises(ResearchError):
        verify_snapshot(tmp_path / "old")
    assert path.read_bytes() == content


def test_recorded_sec_diagnostic_remains_three_unresolved_not_evaluated(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from ragged_claws.research.examples import prepare_sec
    from ragged_claws.research.snapshot import read_inputs

    prepare_sec(
        tmp_path / "prepared",
        ROOT / "tests/fixtures/sec/0000950170-24-105263.txt",
        ROOT / "tests/fixtures/sec/provenance.json",
        PROPOSAL,
        as_of=datetime(2026, 10, 22, 23, tzinfo=UTC),
    )
    inputs = read_inputs(tmp_path / "prepared")
    plan = AnalysisPlan.model_validate_json(
        (ROOT / "research/analysis-plans/sec-p-s-v2.json").read_bytes()
    )
    plan = plan.model_copy(update={"period": inputs.config.period})
    (tmp_path / "plan.json").write_bytes(encoded(plan))
    snapshot = freeze(tmp_path / "prepared", tmp_path / "frozen")
    report = build(tmp_path / "frozen", tmp_path / "research", tmp_path / "registry")
    value = evaluate(
        tmp_path / "frozen",
        tmp_path / "research" / str(snapshot.snapshot_id),
        tmp_path / "plan.json",
        tmp_path / "analyses",
        tmp_path / "registry",
    )
    assert report.input_events == 3
    assert value.conditional_verdict == value.investment_validation == "not_evaluated"
    assert len(value.rows) == 9
    assert all(r.row.status == "unresolved_security" and r.gross_excess is None for r in value.rows)
    assert all(r.row.event.security_id is None for r in value.rows)
    assert all(set(r.net_excess_by_bps.values()) == {None} for r in value.rows)
