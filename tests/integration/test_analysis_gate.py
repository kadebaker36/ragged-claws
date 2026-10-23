"""Temporary invented approvals over EMPTY inputs; never real outcome inspection."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ragged_claws.research.analysis import evaluate
from ragged_claws.research.analysis_models import AnalysisApproval, AnalysisPlan
from ragged_claws.research.build import build
from ragged_claws.research.models import (
    BuildConfig,
    Controls,
    OriginInventory,
    PriceInputs,
    Protocol,
)
from ragged_claws.research.protocol import register
from ragged_claws.research.snapshot import ResearchError, digest, encoded, freeze, model_hash

ROOT = Path(__file__).parents[2]


def empty_scope(tmp_path: Path) -> tuple[Path, Path, AnalysisPlan, AnalysisApproval]:
    protocol = Protocol.model_validate_json(
        (ROOT / "research/hypotheses/sec-p-s-v2.json").read_bytes()
    )
    plan = AnalysisPlan.model_validate_json(
        (ROOT / "research/analysis-plans/sec-p-s-v2.json").read_bytes()
    )
    config = BuildConfig(
        mode="validation",
        hypothesis_id=protocol.hypothesis_id,
        protocol_version=protocol.version,
        period=protocol.validation,
        as_of=datetime(2026, 10, 22, 23, tzinfo=UTC),
        coverage_through=datetime(2026, 10, 22).date(),
        features=protocol.features,
        feed="iex",
        adjustment=plan.adjustment,
    )
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    for name, value in (
        ("config", config),
        ("protocol", protocol),
        ("controls", Controls()),
        ("prices", PriceInputs()),
        ("origins", OriginInventory(records=())),
    ):
        (prepared / f"{name}.json").write_bytes(encoded(value))
    frozen = tmp_path / "frozen"
    snapshot = freeze(prepared, frozen)
    registry = tmp_path / "persistent-test-registry"
    register(
        protocol,
        frozen / "origins.json",
        registry,
        approval_reference="fixture://INVENTED-EMPTY-TEST-ONLY",
        attest_uninspected=True,
    )
    approval = AnalysisApproval(
        supervisor_reference="fixture://INVENTED-EMPTY-TEST-ONLY",
        protocol_sha256=snapshot.protocol_sha256,
        plan_sha256=model_hash(plan),
        source_code_sha256=snapshot.source_code_sha256,
        dependency_lock_sha256=snapshot.dependency_lock_sha256,
        origin_inventory_sha256=digest((frozen / "origins.json").read_bytes()),
        snapshot_sha256=digest((frozen / "snapshot.json").read_bytes()),
        result_scope_snapshot_id=snapshot.snapshot_id,
        registry_path=str(registry.resolve()),
        preserved_history={},
        preserved_history_review_reference="fixture://INVENTED-empty-history",
        reconciled_unpublished_inspections=True,
        execution_context="persistent_operator_workspace",
        calendar_dependence_review="fixture://INVENTED-not-method-acceptance",
        multiplicity_review="fixture://INVENTED-not-method-acceptance",
        availability_and_coverage_review="fixture://INVENTED-not-method-acceptance",
    )
    return frozen, registry, plan, approval


def test_matching_empty_test_scope_cannot_produce_investment_verdict(tmp_path: Path) -> None:
    frozen, registry, plan, approval = empty_scope(tmp_path)
    report = build(
        frozen, tmp_path / "research", registry, analysis_plan=plan, analysis_approval=approval
    )
    assert report.input_events == 0 and report.protocol_status == "registered"
    (tmp_path / "plan.json").write_bytes(encoded(plan))
    (tmp_path / "approval.json").write_bytes(encoded(approval))
    value = evaluate(
        frozen,
        tmp_path / "research" / str(report.snapshot_id),
        tmp_path / "plan.json",
        tmp_path / "analyses",
        registry,
        tmp_path / "approval.json",
    )
    assert value.conditional_verdict == "insufficient"
    assert value.investment_validation == "not_evaluated"
    assert value.approval_sha256 == model_hash(approval)
    assert len(list((registry / "attempts").glob("*.analysis.json"))) == 2


@pytest.mark.parametrize(
    "field",
    [
        "protocol_sha256",
        "plan_sha256",
        "source_code_sha256",
        "dependency_lock_sha256",
        "origin_inventory_sha256",
        "snapshot_sha256",
        "result_scope_snapshot_id",
        "registry_path",
    ],
)
def test_scope_mismatch_denied_before_reading_returns(tmp_path: Path, field: str) -> None:
    frozen, registry, plan, approval = empty_scope(tmp_path)
    changed: object = "a" * 64
    if field == "result_scope_snapshot_id":
        from uuid import UUID

        changed = UUID(int=1)
    elif field == "registry_path":
        changed = str(tmp_path / "different")
    with pytest.raises(ResearchError, match="exact input/result scope"):
        build(
            frozen,
            tmp_path / "research",
            registry,
            analysis_plan=plan,
            analysis_approval=approval.model_copy(update={field: changed}),
        )
    finished = list((registry / "attempts").glob("*.finished.json"))
    assert len(finished) == 1
    assert json.loads(finished[0].read_bytes())["outcome_inspection"] is False
    assert not (tmp_path / "research").exists()


def test_unreconciled_or_changed_history_cannot_be_dropped(tmp_path: Path) -> None:
    frozen, registry, plan, approval = empty_scope(tmp_path)
    # A denial without a matching plan remains in the journal and requires review.
    with pytest.raises(ResearchError, match="separate supervisor analysis approval"):
        build(frozen, tmp_path / "research", registry)
    with pytest.raises(ResearchError, match="unreconciled"):
        build(
            frozen, tmp_path / "research", registry, analysis_plan=plan, analysis_approval=approval
        )
    files = {p.name: digest(p.read_bytes()) for p in (registry / "attempts").iterdir()}
    approval = approval.model_copy(update={"preserved_history": files})
    report = build(
        frozen, tmp_path / "research", registry, analysis_plan=plan, analysis_approval=approval
    )
    assert report.input_events == 0
    # Removing an anchored failed attempt is detected, even after a successful build.
    anchored_finish = next(name for name in files if name.endswith(".finished.json"))
    (registry / "attempts" / anchored_finish).unlink()
    with pytest.raises(ResearchError, match="preserved inspection history"):
        build(frozen, tmp_path / "other", registry, analysis_plan=plan, analysis_approval=approval)


def test_real_evaluation_unregistered_denial_logged_without_outcomes(tmp_path: Path) -> None:
    frozen, _, plan, _ = empty_scope(tmp_path)
    registry = tmp_path / "unregistered"
    result = tmp_path / "unread-outcomes"
    result.mkdir()
    (result / "result.json").write_bytes(b"{}")
    path = tmp_path / "plan.json"
    path.write_bytes(encoded(plan))
    with pytest.raises(ResearchError, match="not been reviewed and registered"):
        evaluate(frozen, result, path, tmp_path / "out", registry)
    finished = next((registry / "attempts").glob("*.finished.json"))
    assert not json.loads(finished.read_bytes())["outcome_inspection"]
