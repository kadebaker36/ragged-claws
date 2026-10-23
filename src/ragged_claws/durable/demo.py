"""Reproducible public SEC recovery rehearsal with an explicitly local fake object boundary."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ragged_claws.durable.models import CloudPolicy, DurableError
from ragged_claws.durable.objects import IndeterminateWrite, LocalObjects, ObjectStore, ObjectValue
from ragged_claws.durable.sync import POINTER_KEY, head, publish, restore, run_pipeline
from ragged_claws.ingestion.sec import SecForm4Adapter
from ragged_claws.research.snapshot import digest, encoded, write_once
from ragged_claws.storage import DataLayout, query_catalog, rebuild_catalog

PUBLIC_SEC = CloudPolicy(review_reference="docs/19-durable-state.md#public-sec-scope")


def ingest_recorded_sec(layout: DataLayout, *, local_replay_at: datetime | None = None) -> None:
    root = Path(__file__).resolve().parents[3]
    metadata = json.loads((root / "tests/fixtures/sec/provenance.json").read_bytes())
    content = (root / "tests/fixtures/sec/0000950170-24-105263.txt").read_bytes()
    if digest(content) != "5eb55738b2b6e3a2e76cb6ffcbfb6e415dbc5c7af763c9c6ced9e30e7171e732":
        raise DurableError("recorded_public_fixture_hash_mismatch")
    SecForm4Adapter(layout).ingest(
        content,
        accession=metadata["accession"],
        source_locator=metadata["source_url"],
        # Original acquisition metadata is replayed exactly; a later local file read records
        # its real current clock, never a fictional future SEC collection date.
        retrieved_at=local_replay_at or datetime.fromisoformat(metadata["retrieved_at"]),
        acceptance_timezone="America/New_York",
    )


class InterruptManifest:
    """Inject a single transport failure, preserving all real validation and parent checks."""

    def __init__(self, objects: ObjectStore) -> None:
        self.objects = objects

    def get(self, key: str, *, limit: int) -> ObjectValue:
        return self.objects.get(key, limit=limit)

    def put(self, key: str, content: bytes, *, expected_etag: str | None) -> str:
        if key.startswith("generations/"):
            raise IndeterminateWrite()
        return self.objects.put(key, content, expected_etag=expected_etag)


def recovery_demo(output: Path) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise DurableError("demo_requires_new_owned_output_directory")
    output.mkdir(parents=True)
    objects = LocalObjects(output / "objects")
    empty = run_pipeline(objects, expected_parent=None, policy=PUBLIC_SEC, operation=lambda _: None)
    first = run_pipeline(
        objects,
        expected_parent=empty.generation.generation_id,
        policy=PUBLIC_SEC,
        operation=ingest_recorded_sec,
    )
    repeat = run_pipeline(
        objects,
        expected_parent=first.generation.generation_id,
        policy=PUBLIC_SEC,
        operation=ingest_recorded_sec,
    )
    assert repeat.no_op
    appended = run_pipeline(
        objects,
        expected_parent=first.generation.generation_id,
        policy=PUBLIC_SEC,
        operation=lambda layout: ingest_recorded_sec(layout, local_replay_at=datetime.now(UTC)),
    )
    prior_pointer = objects.get(POINTER_KEY, limit=4096)

    def failed_research(layout: DataLayout) -> None:
        ingest_recorded_sec(layout, local_replay_at=datetime.now(UTC))
        raise DurableError("invented_research_failure_before_publication")

    failures = []
    try:
        run_pipeline(
            objects,
            expected_parent=appended.generation.generation_id,
            policy=PUBLIC_SEC,
            operation=failed_research,
        )
    except DurableError as exc:
        failures.append(exc.reasons)
    if objects.get(POINTER_KEY, limit=4096) != prior_pointer:
        raise DurableError("demo_authority_changed_after_pipeline_failure")
    try:
        run_pipeline(
            InterruptManifest(objects),
            expected_parent=appended.generation.generation_id,
            policy=PUBLIC_SEC,
            operation=lambda layout: ingest_recorded_sec(layout, local_replay_at=datetime.now(UTC)),
        )
    except IndeterminateWrite as exc:
        failures.append(exc.reasons)
    if objects.get(POINTER_KEY, limit=4096) != prior_pointer:
        raise DurableError("demo_authority_changed_after_upload_failure")
    with restore(objects, appended.generation.generation_id) as clean:
        catalog_absent = not clean.layout.catalog.exists()
        rebuild_catalog(clean.layout)
        event_count = query_catalog(clean.layout.catalog, "select count(*) from event")[0][0]
        assert publish(
            objects,
            clean.layout,
            expected_parent=appended.generation.generation_id,
            policy=PUBLIC_SEC,
        ).no_op
        for name, content in clean.validated.files.items():
            destination = output / "recovered" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        restored_hashes = {name: digest(content) for name, content in clean.validated.files.items()}
    with restore(objects, first.generation.generation_id) as old:
        old_recoverable = old.validated.record_counts["Event"] == 3
    current = head(objects)
    assert current is not None
    result = {
        "format_version": "1.0.0",
        "boundary": "LOCAL_FAKE_OBJECTS_NOT_REAL_R2",
        "source": "previously_recorded_public_SEC_fixture_no_network",
        "capture_context": (
            "original acquisition replay plus current local file replays; no fresh SEC requests"
        ),
        "source_sha256": "5eb55738b2b6e3a2e76cb6ffcbfb6e415dbc5c7af763c9c6ced9e30e7171e732",
        "generations": [
            g.model_dump(mode="json")
            for g in (empty.generation, first.generation, appended.generation)
        ],
        "authoritative_generation": current[0].generation_id,
        "authoritative_pointer_sha256": digest(prior_pointer.content),
        "no_op_repeat": repeat.no_op,
        "failure_injections": failures,
        "pointer_unchanged_after_failures": True,
        "previous_generation_recoverable": old_recoverable,
        "restored_event_count": event_count,
        "duckdb_absent_on_restore": catalog_absent,
        "duckdb_rebuild_event_count": event_count,
        "restored_file_sha256": restored_hashes,
        "protocol_registered": False,
        "real_R2_access_validated": False,
    }
    write_once(output / "recovery.json", encoded(result))
    return result
