"""Separate reviewed analysis scope and persistent inspection-history attestation."""

import json
from pathlib import Path

from ragged_claws.research.analysis_models import AnalysisApproval, AnalysisPlan
from ragged_claws.research.models import Protocol, Snapshot
from ragged_claws.research.protocol import check_configuration, require_registration
from ragged_claws.research.snapshot import (
    Inputs,
    ResearchError,
    digest,
    encoded,
    model_hash,
    private_root,
    write_once,
)


def check_price_contract(inputs: Inputs, plan: AnalysisPlan) -> None:
    if any(
        any(bar.provider_namespace != plan.provider for bar in packet.batch.bars)
        or any(obs.provider_namespace != plan.provider for obs in packet.batch.observations)
        for packet in inputs.prices.packets
    ):
        raise ResearchError("analysis price provider differs from plan")


def check_plan(snapshot: Snapshot, protocol: Protocol, plan: AnalysisPlan) -> None:
    config = snapshot.config
    check_configuration(protocol, config)
    if (
        plan.protocol_sha256 != snapshot.protocol_sha256
        or plan.protocol_sha256 != model_hash(protocol)
        or (plan.hypothesis_id, plan.protocol_version) != (protocol.hypothesis_id, protocol.version)
        or plan.period != config.period
        or plan.features != config.features
        or plan.source_families != protocol.source_families
        or (plan.feed, plan.adjustment) != (config.feed, config.adjustment)
        or config.horizons != (20, 60, 90)
        or ((config.mode == "synthetic") != (plan.purpose == "invented_engineering"))
    ):
        raise ResearchError("analysis plan/protocol/window/features/feed/adjustment/mode mismatch")


def journal_scope(attempt: Path, plan: AnalysisPlan | None, result_hash: str | None) -> None:
    write_once(
        attempt.with_name(attempt.name.replace(".started.json", ".analysis.json")),
        encoded({"plan_sha256": model_hash(plan) if plan else None, "result_sha256": result_hash}),
    )


def require_analysis_approval(
    snapshot: Snapshot,
    protocol: Protocol,
    root: Path,
    registry: Path,
    plan: AnalysisPlan | None,
    approval: AnalysisApproval | None,
    attempt: Path,
) -> None:
    require_registration(snapshot, protocol, root, registry)
    if plan is None or approval is None:
        raise ResearchError("real validation requires separate supervisor analysis approval/plan")
    check_plan(snapshot, protocol, plan)
    # This is intentionally limited to persistent operator workspaces. Ephemeral
    # production cannot assert durability with a quarantined directory (#15).
    private_root(registry)
    if (
        approval.protocol_sha256 != snapshot.protocol_sha256
        or approval.plan_sha256 != model_hash(plan)
        or approval.source_code_sha256 != snapshot.source_code_sha256
        or approval.dependency_lock_sha256 != snapshot.dependency_lock_sha256
        or approval.origin_inventory_sha256 != digest((root / "origins.json").read_bytes())
        or approval.snapshot_sha256 != digest((root / "snapshot.json").read_bytes())
        or approval.result_scope_snapshot_id != snapshot.snapshot_id
        or Path(approval.registry_path).resolve() != registry.resolve()
    ):
        raise ResearchError("supervisor analysis approval does not match exact input/result scope")
    directory = registry / "attempts"
    current = {p.name: p for p in directory.iterdir() if p.is_file()}
    for name, expected in approval.preserved_history.items():
        if (
            Path(name).name != name
            or name not in current
            or digest(current[name].read_bytes()) != expected
        ):
            raise ResearchError("preserved inspection history is missing or changed")
    # An approval cannot erase older inspections by supplying an empty inventory.
    # New attempts must be for this already approved frozen scope and carry its plan.
    for name, path in current.items():
        if name in approval.preserved_history or path == attempt:
            continue
        stem = name.split(".")[0]
        started = directory / f"{stem}.started.json"
        sidecar = directory / f"{stem}.analysis.json"
        if not started.is_file() or not sidecar.is_file():
            raise ResearchError("unreconciled inspection history requires fresh supervisor review")
        record = json.loads(started.read_bytes())
        scope = json.loads(sidecar.read_bytes())
        if (
            record.get("snapshot_id") != str(snapshot.snapshot_id)
            or record.get("protocol_sha256") != snapshot.protocol_sha256
            or scope.get("plan_sha256") != model_hash(plan)
        ):
            raise ResearchError("unreconciled inspection history requires fresh supervisor review")
