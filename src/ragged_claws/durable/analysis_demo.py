"""Local fake archive rehearsal over invented/empty inputs only; no cloud factory."""

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ragged_claws.durable.analysis_archive import APPROVALS, PLANS, seal_archive
from ragged_claws.durable.models import CloudPolicy, DurableError
from ragged_claws.durable.objects import LocalObjects
from ragged_claws.durable.sync import publish, restore
from ragged_claws.research.analysis import evaluate
from ragged_claws.research.analysis_demo import prepare_demo
from ragged_claws.research.analysis_models import AnalysisApproval
from ragged_claws.research.build import build
from ragged_claws.research.models import (
    Controls,
    OriginInventory,
    PriceInputs,
)
from ragged_claws.research.protocol import register, start_attempt
from ragged_claws.research.snapshot import (
    ResearchError,
    digest,
    encoded,
    freeze,
    model_hash,
    write_once,
)
from ragged_claws.storage import DataLayout

POLICY = CloudPolicy(
    scope="invented_engineering",
    invented_attestation=True,
    review_reference="fixture://PRIVATE-LOCAL-ARCHIVE-PATH-DISCLOSURE-REVIEW-ONLY",
)


def prepare_archive(output: Path) -> tuple[Path, dict[str, Any]]:
    """One invented result, two predeclared engineering gates; no real hypothesis search."""
    repo = Path(__file__).resolve().parents[3]
    prepared = output / "prepared"
    plan = prepare_demo(prepared, repo / "research/hypotheses/sec-p-s-v2.json", "positive")
    # Fixed inadequate-sample case retains the production sample floors, still invented.
    insufficient = plan.model_copy(
        update={
            "plan_id": "invented-insufficient-sample",
            "minimum_complete_per_arm": 1000,
            "minimum_issuers_per_arm": 200,
        }
    )
    (output / "insufficient-plan.json").write_bytes(encoded(insufficient))
    frozen = output / "frozen"
    snapshot = freeze(prepared, frozen)
    root = output / "archive"
    registry = root / "research/registry"
    result_root = root / "research"
    build(frozen, result_root, registry)
    approval = AnalysisApproval(
        supervisor_reference="fixture://INVENTED-ONLY-NOT-REAL-METHOD-ACCEPTANCE",
        protocol_sha256=snapshot.protocol_sha256,
        plan_sha256=model_hash(plan),
        source_code_sha256=snapshot.source_code_sha256,
        dependency_lock_sha256=snapshot.dependency_lock_sha256,
        origin_inventory_sha256=digest((frozen / "origins.json").read_bytes()),
        snapshot_sha256=digest((frozen / "snapshot.json").read_bytes()),
        result_scope_snapshot_id=snapshot.snapshot_id,
        registry_path=str(registry.resolve()),
        preserved_history={
            p.name: digest(p.read_bytes()) for p in (registry / "attempts").iterdir()
        },
        preserved_history_review_reference="fixture://INVENTED-LOCAL-HISTORY",
        reconciled_unpublished_inspections=True,
        execution_context="persistent_operator_workspace",
        calendar_dependence_review="fixture://INVENTED-NOT-ACCEPTANCE",
        multiplicity_review="fixture://INVENTED-NOT-ACCEPTANCE",
        availability_and_coverage_review="fixture://INVENTED-NOT-ACCEPTANCE",
    )
    approval_path = root / APPROVALS / f"{model_hash(approval)}.json"
    write_once(approval_path, encoded(approval))
    for declared in (plan, insufficient):
        write_once(root / PLANS / f"{model_hash(declared)}.json", encoded(declared))
    positive = evaluate(
        frozen,
        result_root / str(snapshot.snapshot_id),
        output / "analysis-plan.json",
        root / "research/analyses",
        registry,
        approval_path,
    )
    inadequate = evaluate(
        frozen,
        result_root / str(snapshot.snapshot_id),
        output / "insufficient-plan.json",
        root / "research/analyses",
        registry,
    )
    assert (
        positive.conditional_verdict == "positive"
        and inadequate.conditional_verdict == "insufficient"
    )
    shutil.copytree(frozen, root / "snapshots" / str(snapshot.snapshot_id))
    # Genuine pre-read missing-plan denial: optional scope is absent, finish is retained.
    try:
        evaluate(
            frozen,
            result_root / str(snapshot.snapshot_id),
            output / "absent-plan.json",
            root / "research/analyses",
            registry,
        )
    except OSError:
        pass
    else:
        raise AssertionError("expected invented absent-plan denial")
    bad = output / "bad-header"
    bad.mkdir()
    (bad / "snapshot.json").write_bytes(b"{}")
    try:
        evaluate(
            bad,
            result_root / str(snapshot.snapshot_id),
            output / "analysis-plan.json",
            root / "research/analyses",
            registry,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected reduced header denial")
    # Empty invented discovery request: no actual source events, outcomes or approval.
    inputs = output / "empty-prepared"
    inputs.mkdir()
    protocol = json.loads((frozen / "protocol.json").read_bytes())
    config = snapshot.config.model_copy(
        update={
            "mode": "discovery",
            "period": snapshot.config.period.model_copy(
                update={"start": date(2016, 1, 1), "end": date(2019, 12, 31)}
            ),
            "as_of": datetime(2024, 6, 28, 19, tzinfo=UTC),
            "benchmark_security_id": None,
            "benchmark_listing_id": None,
        }
    )
    for name, value in (
        ("config", config),
        ("protocol", protocol),
        ("controls", Controls()),
        ("prices", PriceInputs()),
        ("origins", OriginInventory(records=())),
    ):
        write_once(inputs / f"{name}.json", encoded(value))
    empty = output / "empty-frozen"
    empty_snapshot = freeze(inputs, empty)
    try:
        build(empty, output / "must-not-publish", registry)
    except ResearchError:
        pass
    else:
        raise AssertionError("expected post-read uncompleted-coverage failure")
    start_attempt(registry, empty_snapshot)  # Legitimate interrupted/potentially inspected attempt.
    shutil.copytree(empty, root / "snapshots" / str(empty_snapshot.snapshot_id))
    seal = seal_archive(root, POLICY, absolute_paths_reviewed=True)
    return root, {
        "positive": str(positive.evaluation_id),
        "insufficient": str(inadequate.evaluation_id),
        "snapshot": str(snapshot.snapshot_id),
        "empty_snapshot": str(empty_snapshot.snapshot_id),
        "archive_seal": seal,
        "approval_sha256": model_hash(approval),
    }


def archive_demo(output: Path) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise DurableError("archive_demo_requires_new_external_directory")
    output.mkdir(parents=True)
    root, detail = prepare_archive(output)
    objects = LocalObjects(output / "objects")
    first = publish(objects, DataLayout(root), expected_parent=None, policy=POLICY)
    with restore(objects, first.generation.generation_id) as restored:
        for name, content in restored.validated.files.items():
            if (root / name).read_bytes() != content:
                raise DurableError("archive_restore_bytes_differ")
        separate = output / "recovered"
        shutil.copytree(restored.layout.root, separate)
    # The restored crash/post-read discovery span still forbids an overlapping new name.
    from ragged_claws.research.models import Period, Protocol

    protocol = Protocol.model_validate_json(
        (separate / "snapshots" / detail["empty_snapshot"] / "protocol.json").read_bytes()
    )
    candidate = protocol.model_copy(
        update={
            "hypothesis_id": "invented-renamed-after-restore",
            "validation": Period(start=date(2024, 1, 1), end=date(2024, 12, 31)),
        }
    )
    try:
        register(
            candidate,
            separate / "snapshots" / detail["empty_snapshot"] / "origins.json",
            separate / "research/registry",
            approval_reference="fixture://INVENTED-ONLY",
            attest_uninspected=True,
        )
    except ResearchError:
        blocked = True
    else:
        raise AssertionError("restored potential inspection cannot recover untouched status")
    result = {
        "boundary": "LOCAL_FAKE_ONLY_NOT_CLOUD_OR_WRITE_AHEAD_AUDIT",
        **detail,
        "generation": first.generation.generation_id,
        "files": len(first.generation.files),
        "byte_equal_restore": True,
        "renamed_untouched_registration_blocked": blocked,
        "approval_operator_path_preserved_not_relocated": True,
        "failure_audit_gate": "UNPUBLISHED_EPHEMERAL_READS_STILL_NOT_DURABLE",
    }
    write_once(output / "archive-demo.json", encoded(result))
    return result
