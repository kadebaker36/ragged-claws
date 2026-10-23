"""Versioned archival checks only: no outcome engine, evaluation or approval installation."""

from datetime import UTC, date, datetime
from fractions import Fraction
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import Field

from ragged_claws.durable.models import MAX_FILES, CloudPolicy, DurableError, safe_path
from ragged_claws.models import Event
from ragged_claws.models.base import CanonicalModel, NonEmptyStr
from ragged_claws.models.evidence import Sha256Hex
from ragged_claws.research.analysis import render
from ragged_claws.research.analysis_math import ARMS, arm_summary, costs, decide, decimal, mean
from ragged_claws.research.analysis_models import AnalysisApproval, AnalysisPlan, Evaluation
from ragged_claws.research.build import report_for
from ragged_claws.research.models import (
    BuildConfig,
    Period,
    Protocol,
    Registration,
    ResearchReport,
    ResearchRow,
    Snapshot,
)
from ragged_claws.research.snapshot import (
    NAMESPACE,
    digest,
    encoded,
    model_hash,
    read_inputs,
    write_once,
)
from ragged_claws.storage import load_envelope_records

SEALS = "research/registry/archives/"
PLANS = "research/registry/plans/"
APPROVALS = "research/registry/approvals/"
ATTEMPTS = "research/registry/attempts/"
ANALYSES = "research/analyses/"


class ArchiveSeal(CanonicalModel):
    format_version: Literal["analysis-archive/1.0.0"] = "analysis-archive/1.0.0"
    destination: Literal["private_operator_archive"] = "private_operator_archive"
    absolute_operator_paths_reviewed: Literal[True]
    review_reference: NonEmptyStr
    files: dict[str, Sha256Hex] = Field(max_length=MAX_FILES)
    attempt_approvals: dict[str, Sha256Hex] = Field(default_factory=dict, max_length=MAX_FILES)


def archived_path(name: str) -> bool:
    return name.startswith((ANALYSES, PLANS, APPROVALS, ATTEMPTS))


def seal_archive(
    root: Path,
    policy: CloudPolicy,
    *,
    absolute_paths_reviewed: bool,
    attempt_approvals: dict[str, str] | None = None,
) -> str:
    """Append a content-addressed local inventory; not cloud authority or a scientific seal."""
    from ragged_claws.durable.validation import capture_layout

    if not absolute_paths_reviewed:
        raise DurableError("private_archive_path_review_required")
    # Make the extension discoverable before capture; no payload is uploaded here.
    (root / SEALS).mkdir(parents=True, exist_ok=True)
    files = capture_layout(root)
    value = ArchiveSeal(
        review_reference=policy.review_reference,
        absolute_operator_paths_reviewed=True,
        files={name: digest(content) for name, content in files.items() if archived_path(name)},
        attempt_approvals=attempt_approvals or {},
    )
    identity = model_hash(value)
    write_once(root / SEALS / f"{identity}.json", encoded(value))
    return identity


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise DurableError("invalid_archive_journal_time")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise DurableError("invalid_archive_journal_time")
    return result.astimezone(UTC)


def journal_records(records: dict[str, dict[str, Any]], files: dict[str, bytes]) -> None:
    """Optional finish is intentional; never create/normalize/erase an attempt."""
    from ragged_claws.durable.validation import _journals

    # Retain the legacy parser for all full journals; only the declared reduced
    # header and the separately versioned scope sidecars need an additional parser.
    full = {
        name: value
        for name, value in records.items()
        if not name.endswith(".analysis.json")
        and records.get(name.split(".")[0] + ".started.json")
        != {"mode": "diagnostic", "phase": "analysis_header_rejected"}
    }
    _journals(full)
    for name, value in records.items():
        suffix = next(
            (s for s in (".started.json", ".finished.json", ".analysis.json") if name.endswith(s)),
            None,
        )
        if suffix is None:
            raise DurableError("unsupported_inspection_journal_file")
        stem = name.removesuffix(suffix)
        if str(UUID(stem)) != stem:
            raise DurableError("invalid_archive_attempt_identity")
        started = records.get(stem + ".started.json")
        if started is None:
            raise DurableError("archive_journal_start_missing")
        reduced = started == {"mode": "diagnostic", "phase": "analysis_header_rejected"}
        if suffix == ".started.json":
            if reduced:
                continue
            if set(value) != {
                "attempt_id",
                "snapshot_id",
                "hypothesis_id",
                "protocol_sha256",
                "mode",
                "period",
                "potential_coverage_end",
                "started_at",
            }:
                raise DurableError("invalid_inspection_journal_start")
            if value["attempt_id"] != stem or value["mode"] not in (
                "synthetic",
                "diagnostic",
                "discovery",
                "validation",
            ):
                raise DurableError("invalid_inspection_journal_start")
            snapshot_path = f"snapshots/{value['snapshot_id']}/snapshot.json"
            if snapshot_path not in files:
                raise DurableError("archive_attempt_snapshot_missing")
            snapshot = Snapshot.model_validate_json(files[snapshot_path])
            if (
                str(snapshot.snapshot_id) != value["snapshot_id"]
                or snapshot.protocol_sha256 != value["protocol_sha256"]
                or snapshot.config.hypothesis_id != value["hypothesis_id"]
                or snapshot.config.mode != value["mode"]
                or snapshot.config.period != Period.model_validate_json(encoded(value["period"]))
                or snapshot.config.coverage_through.isoformat() != value["potential_coverage_end"]
            ):
                raise DurableError("archive_attempt_snapshot_mismatch")
            _time(value["started_at"])
        elif suffix == ".finished.json":
            if (
                set(value)
                not in (
                    {"outcome_inspection", "success", "finished_at"},
                    {"outcome_inspection", "success", "finished_at", "inspection_period"},
                )
                or type(value["success"]) is not bool
                or type(value["outcome_inspection"]) is not bool
            ):
                raise DurableError("invalid_inspection_journal_finish")
            finish = _time(value["finished_at"])
            if reduced:
                if value["success"] or value["outcome_inspection"] or "inspection_period" in value:
                    raise DurableError("invalid_archive_header_denial")
            else:
                if finish < _time(started["started_at"]):
                    raise DurableError("invalid_archive_journal_time")
                real = started["mode"] in ("discovery", "validation")
                if (value["success"] and real and not value["outcome_inspection"]) or (
                    value["outcome_inspection"] and not real
                ):
                    raise DurableError("archive_inspection_mode_mismatch")
                if (
                    value["success"]
                    and f"research/{started['snapshot_id']}/result.json" not in files
                ):
                    raise DurableError("archive_success_result_missing")
                period = Period.model_validate_json(encoded(started["period"]))
                if "inspection_period" in value:
                    inspected = Period.model_validate_json(encoded(value["inspection_period"]))
                    end = max(period.end, date.fromisoformat(started["potential_coverage_end"]))
                    if value["outcome_inspection"] and (
                        inspected.start > period.start
                        or inspected.end < (period.end if value["success"] else end)
                    ):
                        raise DurableError("archive_inspection_interval_truncated")
                elif value["outcome_inspection"]:
                    raise DurableError("archive_inspected_period_missing")
        else:
            if reduced or set(value) != {"plan_sha256", "result_sha256"}:
                raise DurableError("invalid_archive_analysis_scope")
            if value["plan_sha256"] is not None and (
                f"{PLANS}{value['plan_sha256']}.json" not in files
            ):
                raise DurableError("archive_scope_plan_missing")
            if value["result_sha256"] is not None:
                path = f"research/{started['snapshot_id']}/result.json"
                if path not in files or digest(files[path]) != value["result_sha256"]:
                    raise DurableError("archive_scope_result_missing")


def _plan_matches(plan: AnalysisPlan, snapshot: Snapshot, protocol: Protocol) -> None:
    config = snapshot.config
    if (
        plan.protocol_sha256 != snapshot.protocol_sha256
        or model_hash(protocol) != snapshot.protocol_sha256
        or (plan.hypothesis_id, plan.protocol_version)
        != (config.hypothesis_id, config.protocol_version)
        or plan.period != config.period
        or plan.features != config.features
        or plan.source_families != protocol.source_families
        or (plan.feed, plan.adjustment) != (config.feed, config.adjustment)
        or config.horizons != (20, 60, 90)
        or (config.hypothesis_id, config.protocol_version)
        != (protocol.hypothesis_id, protocol.version)
        or set(config.features) != set(protocol.features)
        or set(config.horizons) != set(protocol.horizons)
        or (
            config.mode in ("discovery", "validation")
            and config.period
            != (protocol.discovery if config.mode == "discovery" else protocol.validation)
        )
        or ((config.mode == "synthetic") != (plan.purpose == "invented_engineering"))
    ):
        raise DurableError("archive_evaluation_plan_mismatch")


def _row_contract(rows: tuple[ResearchRow, ...], snapshot: Snapshot, events: set[UUID]) -> None:
    """Check the declared v1 record relationships, without deriving any outcome."""
    keys = {(row.event.event_id, row.horizon_sessions) for row in rows}
    if len(keys) != len(rows) or keys != {
        (event, horizon) for event in events for horizon in snapshot.config.horizons
    }:
        raise DurableError("archive_row_inventory_mismatch")
    for row in rows:
        if (
            row.snapshot_id != snapshot.snapshot_id
            or row.row_id
            != uuid5(snapshot.snapshot_id, f"row:{row.event.event_id}:{row.horizon_sessions}")
            or (row.status == "complete" and row.outcome is None)
            or (
                row.outcome is not None
                and (
                    row.outcome.event_id != row.event.event_id
                    or row.outcome.horizon_sessions != row.horizon_sessions
                    or row.outcome.status.value != row.status
                )
            )
        ):
            raise DurableError("archive_row_relationship_mismatch")


def _evaluation(
    value: Evaluation,
    root: Path,
    files: dict[str, bytes],
    records: dict[str, dict[str, Any]],
    attempt_approvals: dict[str, str],
) -> None:
    snapshot_path = f"snapshots/{value.snapshot_id}/snapshot.json"
    result_path = f"research/{value.snapshot_id}/result.json"
    plan_path = f"{PLANS}{value.plan_sha256}.json"
    if any(p not in files for p in (snapshot_path, result_path, plan_path)):
        raise DurableError("archive_evaluation_dependency_missing")
    snapshot = Snapshot.model_validate_json(files[snapshot_path])
    if (
        BuildConfig.model_validate_json(files[f"snapshots/{value.snapshot_id}/config.json"])
        != snapshot.config
    ):
        raise DurableError("archive_snapshot_configuration_mismatch")
    protocol = Protocol.model_validate_json(files[f"snapshots/{value.snapshot_id}/protocol.json"])
    _plan_matches(value.plan, snapshot, protocol)
    inputs = read_inputs(root / f"snapshots/{value.snapshot_id}")
    if any(
        any(bar.provider_namespace != value.plan.provider for bar in packet.batch.bars)
        or any(obs.provider_namespace != value.plan.provider for obs in packet.batch.observations)
        for packet in inputs.prices.packets
    ):
        raise DurableError("archive_evaluation_price_provider_mismatch")
    report = ResearchReport.model_validate_json(files[f"research/{value.snapshot_id}/report.json"])
    if (
        digest(files[snapshot_path]) != value.snapshot_sha256
        or digest(files[result_path]) != value.result_sha256
        or model_hash(value.plan) != value.plan_sha256
        or AnalysisPlan.model_validate_json(files[plan_path]) != value.plan
        or value.original_report != report
        or (
            value.protocol_sha256,
            value.source_code_sha256,
            value.dependency_lock_sha256,
            value.runtime_versions,
        )
        != (
            snapshot.protocol_sha256,
            snapshot.source_code_sha256,
            snapshot.dependency_lock_sha256,
            snapshot.runtime_versions,
        )
    ):
        raise DurableError("archive_evaluation_reference_mismatch")
    approval = None
    if value.approval_sha256 is not None:
        path = f"{APPROVALS}{value.approval_sha256}.json"
        if path not in files:
            raise DurableError("archive_evaluation_approval_missing")
        approval = AnalysisApproval.model_validate_json(files[path])
        if (
            model_hash(approval) != value.approval_sha256
            or (
                approval.protocol_sha256,
                approval.plan_sha256,
                approval.source_code_sha256,
                approval.dependency_lock_sha256,
                approval.snapshot_sha256,
                approval.result_scope_snapshot_id,
            )
            != (
                value.protocol_sha256,
                value.plan_sha256,
                value.source_code_sha256,
                value.dependency_lock_sha256,
                value.snapshot_sha256,
                value.snapshot_id,
            )
            or approval.origin_inventory_sha256
            != digest(files[f"snapshots/{value.snapshot_id}/origins.json"])
        ):
            raise DurableError("archive_approval_scope_mismatch")
    if snapshot.config.mode in ("discovery", "validation") and approval is None:
        raise DurableError("archive_real_evaluation_approval_missing")
    if snapshot.config.mode in ("discovery", "validation"):
        registration_path = f"research/registry/registrations/{snapshot.protocol_sha256}.json"
        if registration_path not in files:
            raise DurableError("archive_evaluation_registration_missing")
        registration = Registration.model_validate_json(files[registration_path])
        if (
            registration.protocol_sha256 != snapshot.protocol_sha256
            or registration.source_code_sha256 != snapshot.source_code_sha256
            or registration.origin_inventory_sha256
            != digest(files[f"snapshots/{value.snapshot_id}/origins.json"])
        ):
            raise DurableError("archive_evaluation_registration_mismatch")
    identity = digest(
        encoded(
            {
                "snapshot": model_hash(snapshot),
                "result": value.result_sha256,
                "plan": value.plan_sha256,
                "approval": value.approval_sha256,
            }
        )
    )
    if uuid5(NAMESPACE, identity) != value.evaluation_id:
        raise DurableError("archive_evaluation_identity_mismatch")
    rows = load_envelope_records(
        root / f"research/{value.snapshot_id}/research_rows.parquet",
        model_type=ResearchRow,
        id_field="row_id",
        dataset_kind="staging",
        model_schema_version="1.0.0",
    )
    rows = tuple(sorted(rows, key=lambda row: (row.horizon_sessions, str(row.event.event_id))))
    _row_contract(rows, snapshot, {event.event_id for event in inputs.get(Event)})
    if (
        len({(r.event.event_id, r.horizon_sessions) for r in rows}) != len(rows)
        or tuple(row.row for row in value.rows) != rows
        or tuple(costs(row) for row in rows) != value.rows
    ):
        raise DurableError("archive_evaluation_rows_or_costs_mismatch")
    # This existing helper summarizes supplied rows; it never assembles outcomes.
    if report != report_for(inputs, snapshot, rows, snapshot.config.mode == "validation"):
        raise DurableError("archive_report_summary_mismatch")
    if tuple(h.horizon for h in value.horizons) != (60, 20, 90):
        raise DurableError("archive_evaluation_horizons_mismatch")
    for horizon in value.horizons:
        selected = tuple(row for row in value.rows if row.row.horizon_sessions == horizon.horizon)
        if horizon.arms != {arm: arm_summary(selected, arm) for arm in ARMS}:
            raise DurableError("archive_evaluation_arm_summary_mismatch")
        boot = horizon.bootstrap
        if horizon.horizon != 60:
            if (
                boot is not None
                or horizon.conditional_verdict != "not_evaluated"
                or horizon.equal_cost_contrast_by_bps
            ):
                raise DurableError("archive_secondary_inference_forbidden")
        else:
            if boot is None:
                raise DurableError("archive_primary_summary_missing")
            count = sum(horizon.arms[a].complete for a in ARMS)
            cluster_ids = {key for a in ARMS for key in horizon.arms[a].issuer_event_counts}
            if (
                boot.draws != 5000
                or boot.valid_draws < 0
                or boot.missing_arm_draws < 0
                or boot.valid_draws + boot.missing_arm_draws != 5000
                or boot.clusters != len(cluster_ids)
                or boot.missing_arm_fraction != decimal(Fraction(boot.missing_arm_draws, 5000))
                or (boot.valid_draws == 0 and (boot.lower is not None or boot.upper is not None))
                or (boot.valid_draws > 0 and (boot.lower is None or boot.upper is None))
                or (boot.lower is not None and boot.upper is not None and boot.lower > boot.upper)
                or (count == 0 and boot.contrast is not None)
            ):
                raise DurableError("archive_bootstrap_summary_invalid")
            if horizon.equal_cost_contrast_by_bps != {str(b): boot.contrast for b in (10, 25, 50)}:
                raise DurableError("archive_cost_contrast_mismatch")
            means = [
                mean(
                    row.gross_excess
                    for row in selected
                    if row.row.event.event_type == arm
                    and row.row.selection == "selected"
                    and row.row.timing_eligible
                    and row.gross_excess is not None
                )
                for arm in ARMS
            ]
            expected = (
                decimal(means[0] - means[1])
                if means[0] is not None and means[1] is not None
                else None
            )
            if boot.contrast != expected:
                raise DurableError("archive_primary_contrast_mismatch")
            if snapshot.config.mode != "diagnostic":
                verdict, reasons = decide(
                    value.plan,
                    horizon.arms,
                    boot,
                    Fraction(boot.lower) if boot.lower is not None else None,
                    means[0] - Fraction(25, 10000) if means[0] is not None else None,
                )
                if horizon.conditional_verdict != verdict or horizon.reasons != (
                    reasons or ("all_proposed_conditions_met_conditional_only",)
                ):
                    raise DurableError("archive_conditional_summary_mismatch")
            elif horizon.conditional_verdict != "not_evaluated":
                raise DurableError("archive_diagnostic_inference_forbidden")
    if value.conditional_verdict != value.horizons[0].conditional_verdict:
        raise DurableError("archive_evaluation_verdict_mismatch")
    # A valid successful analysis must retain at least one corresponding scope/finish.
    matched = False
    for name, scope in records.items():
        if not name.endswith(".analysis.json") or scope != {
            "plan_sha256": value.plan_sha256,
            "result_sha256": value.result_sha256,
        }:
            continue
        stem = name.removesuffix(".analysis.json")
        started = records.get(stem + ".started.json", {})
        finished = records.get(stem + ".finished.json", {})
        if stem in attempt_approvals and attempt_approvals[stem] != value.approval_sha256:
            continue
        if started.get("snapshot_id") == str(value.snapshot_id) and finished.get("success") is True:
            matched = True
    if not matched:
        raise DurableError("archive_evaluation_inspection_history_missing")


def validate_archive(root: Path, files: dict[str, bytes], policy: CloudPolicy) -> set[str]:
    """Validate only the recognized archival extension; never execute historical research."""
    from ragged_claws.durable.validation import json_value, metadata_secrets

    special = {name for name in files if name.startswith((SEALS, PLANS, APPROVALS, ANALYSES))}
    sidecars = {
        name for name in files if name.startswith(ATTEMPTS) and name.endswith(".analysis.json")
    }
    if not special and not sidecars:
        return set()
    seals = [name for name in special if name.startswith(SEALS)]
    if not seals:
        raise DurableError("analysis_archive_seal_required")
    covered: set[str] = set()
    attempt_approvals: dict[str, str] = {}
    records = {
        name.removeprefix(ATTEMPTS): json_value(content)
        for name, content in files.items()
        if name.startswith(ATTEMPTS)
    }
    for name in sorted(special | sidecars):
        parts = name.split("/")
        if name.startswith(SEALS):
            parsed = json_value(files[name])
            metadata_secrets(parsed)
            seal = ArchiveSeal.model_validate_json(files[name])
            if (
                name != f"{SEALS}{model_hash(seal)}.json"
                or seal.review_reference != policy.review_reference
            ):
                raise DurableError("archive_seal_identity_or_policy_mismatch")
            for path, expected in seal.files.items():
                safe_path(path)
                if not archived_path(path) or path not in files or digest(files[path]) != expected:
                    raise DurableError("archive_inventory_hash_mismatch")
                covered.add(path)
            for attempt, approval_hash in seal.attempt_approvals.items():
                if (
                    str(UUID(attempt)) != attempt
                    or attempt + ".started.json" not in records
                    or f"{APPROVALS}{approval_hash}.json" not in files
                ):
                    raise DurableError("archive_attempt_approval_missing")
                if attempt in attempt_approvals and attempt_approvals[attempt] != approval_hash:
                    raise DurableError("archive_attempt_approval_conflict")
                attempt_approvals[attempt] = approval_hash
        elif name.startswith(ANALYSES):
            if len(parts) != 4 or parts[-1] not in ("evaluation.json", "evaluation.md"):
                raise DurableError("unsupported_analysis_archive_file")
            if str(UUID(parts[2])) != parts[2]:
                raise DurableError("archive_evaluation_path_mismatch")
        elif name.startswith((PLANS, APPROVALS)):
            if len(parts) != 4:
                raise DurableError("unsupported_analysis_archive_file")
            parsed = json_value(files[name])
            metadata_secrets(parsed)
            model = AnalysisPlan if name.startswith(PLANS) else AnalysisApproval
            artifact = model.model_validate_json(files[name])
            if parts[-1] != model_hash(artifact) + ".json":
                raise DurableError("archive_plan_or_approval_identity_mismatch")
            if isinstance(artifact, AnalysisApproval):
                if not (
                    PurePosixPath(artifact.registry_path).is_absolute()
                    or PureWindowsPath(artifact.registry_path).is_absolute()
                ):
                    raise DurableError("archive_approval_operator_path_invalid")
                for history, expected in artifact.preserved_history.items():
                    if (
                        Path(history).name != history
                        or f"{ATTEMPTS}{history}" not in files
                        or (digest(files[f"{ATTEMPTS}{history}"]) != expected)
                    ):
                        raise DurableError("archive_approval_preserved_history_missing")
    if covered != {name for name in files if archived_path(name)}:
        raise DurableError("archive_inventory_incomplete")
    journal_records(records, files)
    used_plans: set[str] = set()
    used_approvals: set[str] = set(attempt_approvals.values())
    evaluations: dict[tuple[str, str, str], list[Evaluation]] = {}
    for name in sorted(special):
        if not name.startswith(ANALYSES) or not name.endswith("evaluation.json"):
            continue
        parsed = json_value(files[name])
        metadata_secrets(parsed)
        value = Evaluation.model_validate_json(files[name])
        if name != f"{ANALYSES}{value.evaluation_id}/evaluation.json":
            raise DurableError("archive_evaluation_path_mismatch")
        md = name.removesuffix("json") + "md"
        if files.get(md) != render(value):
            raise DurableError("archive_evaluation_markdown_mismatch")
        _evaluation(value, root, files, records, attempt_approvals)
        evaluations.setdefault(
            (str(value.snapshot_id), value.plan_sha256, value.result_sha256), []
        ).append(value)
        used_plans.add(value.plan_sha256)
        if value.approval_sha256:
            used_approvals.add(value.approval_sha256)
    for name, scope in records.items():
        if name.endswith(".analysis.json") and scope.get("plan_sha256"):
            used_plans.add(scope["plan_sha256"])
        if not name.endswith(".analysis.json"):
            continue
        stem = name.removesuffix(".analysis.json")
        if (
            records.get(stem + ".finished.json", {}).get("success") is not True
            or scope["result_sha256"] is None
        ):
            continue  # Builder-only scope, denial or unfinished attempt; no Evaluation invented.
        matches = evaluations.get(
            (
                records[stem + ".started.json"]["snapshot_id"],
                scope["plan_sha256"],
                scope["result_sha256"],
            ),
            [],
        )
        if stem in attempt_approvals:
            matches = [v for v in matches if v.approval_sha256 == attempt_approvals[stem]]
        if len(matches) != 1:
            raise DurableError("successful_analysis_evaluation_missing_or_ambiguous")
    for name in special:
        if (
            name.startswith(ANALYSES)
            and name.endswith("evaluation.md")
            and name.removesuffix("md") + "json" not in files
        ):
            raise DurableError("archive_orphan_markdown")
        if (
            name.startswith(PLANS)
            and name.removeprefix(PLANS).removesuffix(".json") not in used_plans
        ):
            raise DurableError("archive_orphan_plan")
        if (
            name.startswith(APPROVALS)
            and name.removeprefix(APPROVALS).removesuffix(".json") not in used_approvals
        ):
            raise DurableError("archive_orphan_approval")
    return special | sidecars
