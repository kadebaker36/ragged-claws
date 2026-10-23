"""Archive closure/history/rights probes. All evaluations and approvals are invented."""

import importlib
import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ragged_claws.durable.analysis_archive import PLANS, SEALS, seal_archive
from ragged_claws.durable.analysis_demo import POLICY, prepare_archive
from ragged_claws.durable.models import CloudPolicy, DurableError
from ragged_claws.durable.objects import (
    ConditionalConflict,
    IndeterminateWrite,
    MemoryObjects,
    ObjectValue,
)
from ragged_claws.durable.sync import POINTER_KEY, generation_id, publish, restore
from ragged_claws.durable.validation import capture_layout, validate_layout
from ragged_claws.research.analysis import render
from ragged_claws.research.analysis_models import AnalysisPlan, Evaluation
from ragged_claws.research.models import Period, Protocol
from ragged_claws.research.protocol import register
from ragged_claws.research.snapshot import (
    ResearchError,
    encoded,
    model_hash,
    verify_snapshot,
    write_once,
)
from ragged_claws.storage import DataLayout


@pytest.fixture(scope="module")
def archive(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    output = tmp_path_factory.mktemp("invented_archive")
    return prepare_archive(output)


def clone(archive: tuple[Path, dict[str, Any]], target: Path) -> tuple[Path, dict[str, Any]]:
    shutil.copytree(archive[0], target)
    return target, archive[1]


def test_byte_equal_restore_preserves_failed_crashed_header_and_operator_path(
    archive: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, detail = archive

    # No archive/restoration step can execute an outcome calculator or mark an inspection.
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("archive must not evaluate or start/finish a research inspection")

    for module, names in (
        ("ragged_claws.research.build", ("assemble",)),
        ("ragged_claws.research.analysis", ("evaluate",)),
        ("ragged_claws.research.protocol", ("start_attempt", "finish_attempt")),
    ):
        loaded = importlib.import_module(module)
        for name in names:
            monkeypatch.setattr(loaded, name, forbidden)
    before = capture_layout(root)
    objects = MemoryObjects()
    first = publish(objects, DataLayout(root), expected_parent=None, policy=POLICY)
    with restore(objects, first.generation.generation_id) as recovered:
        assert recovered.validated.files == before
        assert recovered.generation.format_version == "1.0.0"
        # Same underlying historical artifacts are preserved, not made executable.
        approval = next((recovered.layout.root / "research/registry/approvals").glob("*.json"))
        assert json.loads(approval.read_bytes())["registry_path"] == str(
            (root / "research/registry").resolve()
        )
        assert not recovered.layout.catalog.exists()
        attempts = recovered.layout.root / "research/registry/attempts"
        starts = list(attempts.glob("*.started.json"))
        assert len(starts) == 7
        assert (
            sum(
                not p.with_name(p.name.replace(".started.json", ".finished.json")).exists()
                for p in starts
            )
            == 1
        )
        finishes = [json.loads(p.read_bytes()) for p in attempts.glob("*.finished.json")]
        assert any(not x["success"] and x["outcome_inspection"] for x in finishes)
        assert any(not x["success"] and not x["outcome_inspection"] for x in finishes)
        assert any(
            json.loads(p.read_bytes()).get("phase") == "analysis_header_rejected" for p in starts
        )
        candidate = Protocol.model_validate_json(
            (
                recovered.layout.root / "snapshots" / detail["empty_snapshot"] / "protocol.json"
            ).read_bytes()
        ).model_copy(
            update={
                "hypothesis_id": "invented-new-name",
                "validation": Period.model_validate_json(
                    b'{"start":"2024-01-01","end":"2024-12-31"}'
                ),
            }
        )
        with pytest.raises(ResearchError, match="previously or potentially inspected"):
            register(
                candidate,
                recovered.layout.root / "snapshots" / detail["empty_snapshot"] / "origins.json",
                recovered.layout.root / "research/registry",
                approval_reference="fixture://INVENTED",
                attest_uninspected=True,
            )
        assert capture_layout(recovered.layout.root) == before
    assert capture_layout(root) == before


@pytest.mark.parametrize("kind", ["plan", "sidecar", "result", "finished", "approval", "markdown"])
def test_missing_dependency_rejected_before_writes_and_old_generation_restores(
    archive: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    kind: str,
) -> None:
    root, detail = clone(archive, tmp_path / "candidate")
    objects = MemoryObjects()
    first = publish(objects, DataLayout(root), expected_parent=None, policy=POLICY)
    previous = objects.get(POINTER_KEY, limit=4096)
    paths = {
        "plan": next((root / PLANS).glob("*.json")),
        "sidecar": next((root / "research/registry/attempts").glob("*.analysis.json")),
        "result": root / "research" / detail["snapshot"] / "result.json",
        "finished": next((root / "research/registry/attempts").glob("*.finished.json")),
        "approval": next((root / "research/registry/approvals").glob("*.json")),
        "markdown": root / "research/analyses" / detail["positive"] / "evaluation.md",
    }
    paths[kind].unlink()
    count = len(objects.values)
    with pytest.raises(DurableError):
        publish(
            objects, DataLayout(root), expected_parent=first.generation.generation_id, policy=POLICY
        )
    assert len(objects.values) == count and objects.get(POINTER_KEY, limit=4096) == previous
    with restore(objects, first.generation.generation_id) as old:
        assert paths[kind].relative_to(root).as_posix() in old.validated.files


@pytest.mark.parametrize(
    "mutation", ["summary", "row", "uuid", "markdown", "duplicate_json", "orphan", "path", "rights"]
)
def test_resealed_invalid_archive_is_not_accepted(
    archive: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    mutation: str,
) -> None:
    root, detail = clone(archive, tmp_path / "candidate")
    for p in (root / SEALS).glob("*.json"):
        p.unlink()  # Model a first publication whose local inventory was recomputed.
    path = root / "research/analyses" / detail["positive"] / "evaluation.json"
    raw = json.loads(path.read_bytes())
    if mutation == "summary":
        raw["horizons"][0]["arms"]["equity_purchase"]["complete"] = 999
    elif mutation == "row":
        raw["rows"][0]["net_excess_by_bps"]["25"] = "9"
    elif mutation == "uuid":
        raw["evaluation_id"] = str(uuid4())
    elif mutation == "markdown":
        path.with_suffix(".md").write_bytes(b"made-up positive")
    elif mutation == "duplicate_json":
        path.write_bytes(
            path.read_bytes().replace(
                b'"evaluation_id":', b'"evaluation_id":"duplicate","evaluation_id":', 1
            )
        )
    elif mutation == "orphan":
        (root / "research/registry/plans" / ("a" * 64 + ".json")).write_bytes(
            next((root / PLANS).glob("*.json")).read_bytes()
        )
    elif mutation == "path":
        (root / "research/analyses/unreviewed.csv").write_bytes(b"unknown")
    if mutation in ("summary", "row", "uuid"):
        path.write_bytes(encoded(raw))
        value = Evaluation.model_validate_json(path.read_bytes())
        path.with_suffix(".md").write_bytes(render(value))
    if mutation == "rights":
        # A declared policy cannot launder the actual invented source namespace.
        wrong = CloudPolicy(review_reference=POLICY.review_reference)
    else:
        wrong = POLICY
    seal_archive(root, wrong, absolute_paths_reviewed=True)
    with pytest.raises(DurableError):
        validate_layout(root, wrong)


@pytest.mark.parametrize("change", ["deletion", "mutation"])
def test_parent_immutable_seals_prevent_resealing_history_change(
    archive: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    change: str,
) -> None:
    root, _ = clone(archive, tmp_path / "candidate")
    objects = MemoryObjects()
    first = publish(objects, DataLayout(root), expected_parent=None, policy=POLICY)
    original = objects.get(POINTER_KEY, limit=4096)
    # Remove all old local seals, then reseal a mutated/deleted legitimate unfinished history.
    for p in (root / SEALS).glob("*.json"):
        p.unlink()
    starts = root / "research/registry/attempts"
    crash = next(
        p
        for p in starts.glob("*.started.json")
        if not p.with_name(p.name.replace(".started.json", ".finished.json")).exists()
    )
    if change == "deletion":
        crash.unlink()
    else:
        data = json.loads(crash.read_bytes())
        data["started_at"] = "2026-10-23T00:00:00Z"
        crash.write_bytes(encoded(data))
    seal_archive(root, POLICY, absolute_paths_reviewed=True)
    with pytest.raises(DurableError, match="parent_state_removed|immutable_history_conflict"):
        publish(
            objects, DataLayout(root), expected_parent=first.generation.generation_id, policy=POLICY
        )
    assert objects.get(POINTER_KEY, limit=4096) == original


class FailingObjects:
    def __init__(self, objects: MemoryObjects, mode: str) -> None:
        self.objects, self.mode = objects, mode
        self.puts = 0
        self.readback = False

    def get(self, key: str, *, limit: int) -> ObjectValue:
        value = self.objects.get(key, limit=limit)
        if self.readback and self.mode == "readback" and key.startswith("blobs/"):
            return ObjectValue(b"corrupt", value.etag)
        return value

    def put(self, key: str, content: bytes, *, expected_etag: str | None) -> str:
        self.puts += 1
        if self.mode == "upload" and self.puts == 2:
            raise IndeterminateWrite()
        if key == POINTER_KEY and self.mode == "cas":
            raise ConditionalConflict()
        result = self.objects.put(key, content, expected_etag=expected_etag)
        if key.startswith("generations/"):
            self.readback = True
        return result


@pytest.mark.parametrize("mode", ["upload", "readback", "cas"])
def test_failure_preserves_old_authority_and_complete_restore(
    archive: tuple[Path, dict[str, Any]],
    tmp_path: Path,
    mode: str,
) -> None:
    root, detail = clone(archive, tmp_path / "candidate")
    objects = MemoryObjects()
    first = publish(objects, DataLayout(root), expected_parent=None, policy=POLICY)
    original = objects.get(POINTER_KEY, limit=4096)
    # Append a genuine reduced-header pre-read denial and append-only inventory.
    identity = str(uuid4())
    write_once(
        root / f"research/registry/attempts/{identity}.started.json",
        encoded({"mode": "diagnostic", "phase": "analysis_header_rejected"}),
    )
    seal_archive(root, POLICY, absolute_paths_reviewed=True)
    with pytest.raises(DurableError):
        publish(
            FailingObjects(objects, mode),
            DataLayout(root),
            expected_parent=first.generation.generation_id,
            policy=POLICY,
        )
    assert objects.get(POINTER_KEY, limit=4096) == original
    with restore(objects, first.generation.generation_id) as old:
        assert f"research/analyses/{detail['insufficient']}/evaluation.json" in old.validated.files


def test_private_archive_review_is_explicit(archive: tuple[Path, dict[str, Any]]) -> None:
    with pytest.raises(DurableError, match="path_review"):
        seal_archive(archive[0], POLICY, absolute_paths_reviewed=False)
    with pytest.raises(DurableError, match="policy"):
        validate_layout(archive[0], POLICY.model_copy(update={"review_reference": "unreviewed"}))


def test_append_restore_and_forged_child_cannot_remove_parent_history(
    archive: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    root, _ = clone(archive, tmp_path / "candidate")
    objects = MemoryObjects()
    first = publish(objects, DataLayout(root), expected_parent=None, policy=POLICY)
    path = root / f"research/registry/attempts/{uuid4()}.started.json"
    write_once(path, encoded({"mode": "diagnostic", "phase": "analysis_header_rejected"}))
    seal_archive(root, POLICY, absolute_paths_reviewed=True)
    second = publish(
        objects, DataLayout(root), expected_parent=first.generation.generation_id, policy=POLICY
    )
    with restore(objects, second.generation.generation_id) as recovered:
        assert recovered.validated.files == capture_layout(root)
    # Rehashing a forged child manifest cannot hide a parent journal deletion.
    forged = second.generation.model_copy(
        update={
            "parent_id": second.generation.generation_id,
            "files": tuple(
                e for e in second.generation.files if e.path != path.relative_to(root).as_posix()
            ),
        }
    )
    forged = forged.model_copy(update={"generation_id": generation_id(forged)})
    objects.put(f"generations/{forged.generation_id}.json", encoded(forged), expected_etag=None)
    with (
        pytest.raises(DurableError, match="immutable_parent_history"),
        restore(objects, forged.generation_id),
    ):
        pytest.fail("must reject before restoring a forged child")
    with restore(objects, first.generation.generation_id) as old:
        assert path.relative_to(root).as_posix() not in old.validated.files


@pytest.mark.parametrize(
    "mutation", ["future", "header", "real_success", "truncated", "naive", "secret", "scope"]
)
def test_journal_and_extension_contracts_fail_closed(
    archive: tuple[Path, dict[str, Any]], tmp_path: Path, mutation: str
) -> None:
    root, detail = clone(archive, tmp_path / "candidate")
    if mutation == "future":
        seal = next((root / SEALS).glob("*.json"))
        raw = json.loads(seal.read_bytes())
        raw["format_version"] = "analysis-archive/2.0.0"
        seal.write_bytes(encoded(raw))
    else:
        attempts = root / "research/registry/attempts"
        if mutation in ("header", "secret"):
            start = next(
                p for p in attempts.glob("*.started.json") if "phase" in json.loads(p.read_bytes())
            )
        elif mutation == "scope":
            start = next(
                p
                for p in attempts.glob("*.started.json")
                if p.with_name(p.name.replace("started", "analysis")).exists()
            )
        else:
            start = next(
                p
                for p in attempts.glob("*.started.json")
                if json.loads(p.read_bytes()).get("snapshot_id") == detail["empty_snapshot"]
                and p.with_name(p.name.replace("started", "finished")).exists()
            )
        path = start.with_name(
            start.name.replace("started", "analysis" if mutation == "scope" else "finished")
        )
        raw = json.loads(path.read_bytes())
        if mutation == "header":
            raw["outcome_inspection"] = True
        elif mutation == "real_success":
            raw.update(success=True, outcome_inspection=False)
        elif mutation == "truncated":
            raw["inspection_period"]["end"] = "2019-12-31"
        elif mutation == "naive":
            raw["finished_at"] = "2026-10-23T00:00:00"
        elif mutation == "secret":
            raw["token"] = "INVENTED-NONSECRET-MARKER"
        else:
            raw["result_sha256"] = "a" * 64
        path.write_bytes(encoded(raw))
        for seal in (root / SEALS).glob("*.json"):
            seal.unlink()
        seal_archive(root, POLICY, absolute_paths_reviewed=True)
    with pytest.raises(DurableError):
        validate_layout(root, POLICY)


def test_historical_extension_restore_does_not_grant_current_execution(
    archive: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, detail = archive
    snapshot_module = importlib.import_module("ragged_claws.research.snapshot")
    original = snapshot_module.environment()
    monkeypatch.setattr(
        snapshot_module, "environment", lambda: ("0" * 64, original[1], original[2])
    )
    objects = MemoryObjects()
    published = publish(objects, DataLayout(root), expected_parent=None, policy=POLICY)
    with restore(objects, published.generation.generation_id) as recovered:
        assert recovered.validated.files == capture_layout(root)
        with pytest.raises(ResearchError, match="environment|code|runtime"):
            verify_snapshot(recovered.layout.root / "snapshots" / detail["snapshot"])


@pytest.mark.parametrize("mutation", ["provider", "purpose", "protocol", "period"])
def test_evaluation_plan_contract_is_checked_before_identity(
    archive: tuple[Path, dict[str, Any]], tmp_path: Path, mutation: str
) -> None:
    root, detail = clone(archive, tmp_path / "candidate")
    path = root / "research/analyses" / detail["insufficient"] / "evaluation.json"
    raw = json.loads(path.read_bytes())
    if mutation == "provider":
        raw["plan"]["provider"] = "synthetic.different-provider"
    elif mutation == "purpose":
        raw["plan"]["purpose"] = "proposed_validation"
    elif mutation == "protocol":
        raw["plan"]["hypothesis_id"] = "invented-other-protocol"
    else:
        raw["plan"]["period"]["end"] = "2024-12-30"
    plan = AnalysisPlan.model_validate_json(encoded(raw["plan"]))
    raw["plan_sha256"] = model_hash(plan)
    write_once(root / PLANS / f"{model_hash(plan)}.json", encoded(plan))
    path.write_bytes(encoded(raw))
    path.with_suffix(".md").write_bytes(render(Evaluation.model_validate_json(path.read_bytes())))
    for seal in (root / SEALS).glob("*.json"):
        seal.unlink()
    seal_archive(root, POLICY, absolute_paths_reviewed=True)
    with pytest.raises(DurableError, match="price_provider|plan_mismatch"):
        validate_layout(root, POLICY)
