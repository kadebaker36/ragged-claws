"""Immutable evaluations of sealed builder results, with no alternative return path."""

import json
from pathlib import Path
from uuid import uuid4, uuid5

from ragged_claws.models import Outcome, Provenance, SourceObservation
from ragged_claws.research.analysis_gate import (
    check_plan,
    check_price_contract,
    journal_scope,
    require_analysis_approval,
)
from ragged_claws.research.analysis_math import analyze_horizon, costs
from ragged_claws.research.analysis_models import AnalysisApproval, AnalysisPlan, Evaluation
from ragged_claws.research.build import assemble, markdown, report_for
from ragged_claws.research.models import Protocol, ResearchReport, ResearchRow, Snapshot
from ragged_claws.research.protocol import finish_attempt, start_attempt
from ragged_claws.research.snapshot import (
    NAMESPACE,
    ResearchError,
    digest,
    encoded,
    model_hash,
    output_rights,
    read_inputs,
    verify_snapshot,
    write_once,
)
from ragged_claws.storage import CanonicalParquetStore, DataLayout, load_envelope_records


def verified_result(
    root: Path,
    result: Path,
    snapshot: Snapshot,
) -> tuple[tuple[ResearchRow, ...], ResearchReport]:
    """Hashes plus semantic reassembly using the one existing forward engine.

    A user can reseal corrupt files, so file hashes alone cannot validate outcomes.
    This runs only after the real inspection gates; old environment mismatches fail.
    """
    seal = json.loads((result / "result.json").read_bytes())
    actual = {
        p.relative_to(result).as_posix(): digest(p.read_bytes())
        for p in result.rglob("*")
        if p.is_file() and p != result / "result.json"
    }
    if (
        any(p.is_symlink() for p in result.rglob("*"))
        or seal != {"snapshot_id": str(snapshot.snapshot_id), "files": actual}
        or (result / "snapshot.json").read_bytes() != (root / "snapshot.json").read_bytes()
    ):
        raise ResearchError("inconsistent or missing research result hashes/snapshot")
    rows = load_envelope_records(
        result / "research_rows.parquet",
        model_type=ResearchRow,
        id_field="row_id",
        dataset_kind="staging",
        model_schema_version="1.0.0",
    )
    keys = {(r.event.event_id, r.horizon_sessions) for r in rows}
    if len(keys) != len(rows):
        raise ResearchError("duplicate economic Event ID/horizon in analysis input")
    inputs = read_inputs(root)
    expected_rows, provenance = assemble(inputs, snapshot)
    if {r.row_id: model_hash(r) for r in rows} != {r.row_id: model_hash(r) for r in expected_rows}:
        raise ResearchError("research rows do not match canonical builder/forward outcomes")
    report = report_for(inputs, snapshot, rows, snapshot.config.mode == "validation")
    store = CanonicalParquetStore(DataLayout(result), read_only=True)
    expected_outcomes = tuple(r.outcome for r in rows if r.outcome is not None)
    paths = {"snapshot.json", "report.json", "report.md"}
    if rows:
        paths.add("research_rows.parquet")
    if expected_outcomes:
        paths.add("curated/outcome.parquet")
    if provenance:
        paths.add("curated/provenance.parquet")
    if (
        set(actual) != paths
        or {model_hash(r) for r in store.load(Outcome)}
        != {model_hash(r) for r in expected_outcomes}
        or {model_hash(r) for r in store.load(Provenance)} != {model_hash(r) for r in provenance}
        or (result / "report.json").read_bytes() != encoded(report)
        or (result / "report.md").read_bytes() != markdown(report)
    ):
        raise ResearchError("research report/outcome/dependency mismatch")
    return tuple(sorted(rows, key=lambda r: (r.horizon_sessions, str(r.event.event_id)))), report


def render(value: Evaluation) -> bytes:
    lines = [
        f"# Conditional analysis {value.evaluation_id}",
        "",
        f"Mode: {value.original_report.mode}; plan: {value.plan.plan_id}/{value.plan.version}.",
        f"Conditional proposed calculation: **{value.conditional_verdict}**.",
        "Investment validation: **not_evaluated**. " + value.investment_validation_reason,
        "",
        "INVENTED engineering support; no real investment evidence."
        if value.plan.purpose == "invented_engineering"
        else "Unaccepted proposal calculation only.",
        "",
        "Stock costs: 10/25/50 bps round trip, divided by 10000; SPY costs: zero. "
        "Daily-open/close fills and constant costs are assumptions. Sales remain long-stock "
        "event outcomes, not short positions. Equal costs cancel in the contrast; these "
        "scenarios are not independent robustness tests.",
        "",
        "| Sessions | Arm | Selected | Actionable | Complete | Complete issuers | Coverage | "
        "Gross excess | Net excess (25 bps) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for horizon in value.horizons:
        for arm, summary in horizon.arms.items():
            lines.append(
                f"| {horizon.horizon} | {arm} | {summary.selected} | "
                f"{summary.selected_actionable} | {summary.complete} | "
                f"{summary.distinct_complete_issuers} | {summary.complete_coverage} | "
                f"{summary.gross_excess_mean} | {summary.net_excess_means_by_bps['25']} |"
            )
        if horizon.bootstrap is not None:
            boot = horizon.bootstrap
            lines.extend(
                (
                    "",
                    f"Primary contrast: {boot.contrast}; nearest-rank 95% interval: "
                    f"[{boot.lower}, {boot.upper}]; missing-arm draws: "
                    f"{boot.missing_arm_draws}/{boot.draws}.",
                    "Reasons: " + ", ".join(horizon.reasons),
                    "",
                )
            )
    lines.extend(
        (
            "",
            "All original rows/status/reasons/dependencies, issuer concentrations, "
            "plan and input/code/lock/runtime hashes are preserved in evaluation.json.",
            "Issuer clustering assumes independent clusters; calendar shocks, overlap, "
            "selection, multiplicity and coverage/availability sensitivity need separate review.",
            "",
        )
    )
    return "\n".join(lines).encode()


def evaluate(
    root: Path,
    result: Path,
    plan_path: Path,
    output: Path,
    registry: Path,
    approval_path: Path | None = None,
) -> Evaluation:
    try:
        snapshot = Snapshot.model_validate_json((root / "snapshot.json").read_bytes())
    except Exception:
        # No outcomes read. Even invalid-header requests leave a persistent denial.
        attempt = registry / "attempts" / f"{uuid4()}.started.json"
        write_once(attempt, encoded({"mode": "diagnostic", "phase": "analysis_header_rejected"}))
        finish_attempt(attempt, inspected=False, success=False)
        raise
    for left in (root.resolve(), result.resolve()):
        for right in (output.resolve(), registry.resolve()):
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise ResearchError(
                    "analysis output/registry must not overlap frozen inputs/results"
                )
    # Rights apply before writing journals, including denied attempts.
    inputs_config = snapshot.config
    output_rights(inputs_config, (), registry)
    output_rights(inputs_config, (), output)
    attempt = start_attempt(registry, snapshot)
    inspected = False
    try:
        plan = AnalysisPlan.model_validate_json(plan_path.read_bytes())
        approval = (
            AnalysisApproval.model_validate_json(approval_path.read_bytes())
            if approval_path
            else None
        )
        protocol = Protocol.model_validate_json((root / "protocol.json").read_bytes())
        result_hash = digest((result / "result.json").read_bytes())
        journal_scope(attempt, plan, result_hash)
        if snapshot.config.mode in ("validation", "discovery"):
            require_analysis_approval(snapshot, protocol, root, registry, plan, approval, attempt)
            inspected = True  # Conservatively include failures while reading price payloads.
        check_plan(snapshot, protocol, plan)
        snapshot = verify_snapshot(root)
        inputs = read_inputs(root)
        output_rights(inputs.config, inputs.get(SourceObservation), output)
        output_rights(inputs.config, inputs.get(SourceObservation), registry)
        check_price_contract(inputs, plan)
        inspected = inputs.config.mode in ("validation", "discovery")
        rows, report = verified_result(root, result, snapshot)
        cost_rows = tuple(costs(r) for r in rows)
        horizons = tuple(analyze_horizon(cost_rows, plan, h) for h in (60, 20, 90))
        # A diagnostic cannot acquire a success verdict from missing/empty data.
        verdict = horizons[0].conditional_verdict
        if inputs.config.mode == "diagnostic":
            verdict = "not_evaluated"
            horizons = tuple(
                h.model_copy(
                    update={
                        "conditional_verdict": "not_evaluated",
                        "reasons": ("diagnostic_no_inference",),
                    }
                )
                for h in horizons
            )
        identity = digest(
            encoded(
                {
                    "snapshot": model_hash(snapshot),
                    "result": result_hash,
                    "plan": model_hash(plan),
                    "approval": model_hash(approval) if approval else None,
                }
            )
        )
        value = Evaluation(
            evaluation_id=uuid5(NAMESPACE, identity),
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=digest((root / "snapshot.json").read_bytes()),
            result_sha256=result_hash,
            protocol_sha256=snapshot.protocol_sha256,
            plan_sha256=model_hash(plan),
            plan=plan,
            source_code_sha256=snapshot.source_code_sha256,
            dependency_lock_sha256=snapshot.dependency_lock_sha256,
            runtime_versions=snapshot.runtime_versions,
            approval_sha256=model_hash(approval) if approval else None,
            original_report=report,
            rows=cost_rows,
            horizons=horizons,
            conditional_verdict=verdict,
        )
        target = output / str(value.evaluation_id)
        write_once(target / "evaluation.json", encoded(value))
        write_once(target / "evaluation.md", render(value))
        # Failures and successes are retained outside temporary workspaces.
        finish_attempt(
            attempt,
            inspected=inspected,
            success=True,
            inspection_period=type(inputs.config.period)(
                start=inputs.config.period.start,
                end=max(inputs.config.period.end, inputs.config.coverage_through),
            ),
        )
        return value
    except Exception:
        finish_attempt(
            attempt,
            inspected=inspected,
            success=False,
            inspection_period=type(snapshot.config.period)(
                start=snapshot.config.period.start,
                end=max(snapshot.config.period.end, snapshot.config.coverage_through),
            )
            if inspected
            else None,
        )
        raise
