"""Pinned restore, complete validation, immutable upload and conditional authority publication."""

import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from ragged_claws.durable.models import (
    MAX_MANIFEST,
    CloudPolicy,
    DurableError,
    Generation,
    Pointer,
)
from ragged_claws.durable.objects import (
    ConditionalConflict,
    MissingObject,
    ObjectStore,
)
from ragged_claws.durable.validation import (
    Validated,
    compare_parent,
    entries,
    json_value,
    metadata_secrets,
    validate_layout,
)
from ragged_claws.research.snapshot import digest, encoded, environment, private_root
from ragged_claws.storage import DataLayout

POINTER_KEY = "authority/current.json"


@contextmanager
def _workspace(temporary_parent: Path | None) -> Iterator[Path]:
    parent = (temporary_parent or Path(tempfile.gettempdir())).resolve()
    try:
        private_root(parent)
    except ValueError:
        raise DurableError("private_runtime_workspace_required") from None
    workspace = tempfile.TemporaryDirectory(prefix="ragged-claws-state-", dir=parent, delete=False)
    owned = Path(workspace.name).resolve()
    try:
        yield owned
    except BaseException as exc:
        # Failed inspections must not disappear with their temporary layout. Never cloud-upload
        # possibly unapproved failure payloads or silently discard a failed research journal.
        (owned / "failure-receipt.json").write_bytes(
            encoded(
                {
                    "status": "UNPUBLISHED_OR_INDETERMINATE_REQUIRES_RECONCILIATION",
                    "inspection_history_may_be_unpublished": True,
                }
            )
        )
        if isinstance(exc, Exception):
            exc.add_note(f"Private failed workspace preserved at {owned}")
        raise
    else:
        if owned.is_symlink() or owned.resolve() != owned or not owned.is_relative_to(parent):
            raise DurableError("owned_workspace_location_changed")
        workspace.cleanup()  # Only the verified absolute, newly owned temporary directory.


def generation_id(generation: Generation) -> str:
    return digest(encoded(generation.model_dump(mode="json", exclude={"generation_id"})))


def head(store: ObjectStore) -> tuple[Pointer, str] | None:
    try:
        value = store.get(POINTER_KEY, limit=4096)
    except MissingObject:
        return None
    try:
        metadata_secrets(json_value(value.content))
        return Pointer.model_validate_json(value.content), value.etag
    except ValueError:
        raise DurableError("invalid_authority_pointer") from None


def load_generation(store: ObjectStore, identity: str) -> Generation:
    # Validate the caller's pinned identity before constructing any key.
    try:
        pointer = Pointer(generation_id=identity)
    except ValueError:
        raise DurableError("invalid_pinned_generation") from None
    value = store.get(f"generations/{pointer.generation_id}.json", limit=MAX_MANIFEST)
    try:
        metadata_secrets(json_value(value.content))
        generation = Generation.model_validate_json(value.content)
    except ValueError:
        raise DurableError("invalid_generation_manifest") from None
    if generation.generation_id != identity or generation_id(generation) != identity:
        raise DurableError("generation_manifest_identity_mismatch")
    return generation


@dataclass
class Restored:
    layout: DataLayout
    generation: Generation
    validated: Validated


@contextmanager
def restore(
    store: ObjectStore,
    identity: str,
    *,
    temporary_parent: Path | None = None,
) -> Iterator[Restored]:
    """Yield only a fully verified owned temporary layout; never install over caller data."""
    generation = load_generation(store, identity)
    ancestor = generation
    seen = {identity}
    manifest_bytes = len(encoded(generation))
    while ancestor.parent_id is not None:
        if ancestor.parent_id in seen or len(seen) >= 4096:
            raise DurableError("cyclic_or_excessive_generation_history")
        seen.add(ancestor.parent_id)
        ancestor = load_generation(store, ancestor.parent_id)
        manifest_bytes += len(encoded(ancestor))
        if manifest_bytes > 32 * 1024 * 1024 or ancestor.policy != generation.policy:
            raise DurableError("unsupported_generation_history")
    with _workspace(temporary_parent) as temp:
        layout = DataLayout(temp / "data")
        layout.root.mkdir()
        for entry in generation.files:
            value = store.get(f"blobs/{entry.sha256}", limit=entry.size)
            if len(value.content) != entry.size or digest(value.content) != entry.sha256:
                raise DurableError("object_size_or_hash_mismatch")
            destination = layout.root / entry.path
            if not destination.resolve().is_relative_to(layout.root.resolve()):
                raise DurableError("unsafe_restore_destination")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(value.content)
        validated = validate_layout(layout.root, generation.policy)
        if (entries(validated), validated.notices, validated.record_counts) != (
            generation.files,
            generation.license_notices,
            generation.record_counts,
        ):
            raise DurableError("generation_validation_metadata_mismatch")
        yield Restored(layout, generation, validated)


def _immutable(store: ObjectStore, key: str, content: bytes) -> None:
    try:
        store.put(key, content, expected_etag=None)
    except ConditionalConflict:
        previous = store.get(key, limit=len(content))
        if previous.content != content:
            raise DurableError("immutable_object_conflict") from None


@dataclass(frozen=True)
class Publication:
    generation: Generation
    no_op: bool


def publish(
    store: ObjectStore,
    layout: DataLayout,
    *,
    expected_parent: str | None,
    policy: CloudPolicy,
    temporary_parent: Path | None = None,
) -> Publication:
    authority = head(store)
    actual_parent = authority[0].generation_id if authority else None
    if actual_parent != expected_parent:
        raise DurableError("stale_expected_parent")
    candidate = validate_layout(layout.root, policy)
    parent_state = None
    if expected_parent is not None:
        with restore(store, expected_parent, temporary_parent=temporary_parent) as parent:
            if parent.generation.policy != policy:
                raise DurableError("cloud_policy_change_requires_separate_namespace_review")
            compare_parent(parent.validated, candidate)
            parent_state = parent.validated
            if parent.validated.files == candidate.files:
                if head(store) != authority:
                    raise DurableError("stale_expected_parent")
                return Publication(parent.generation, no_op=True)
    code, lock, runtime = environment()
    runtime = {**runtime, "boto3": version("boto3"), "botocore": version("botocore")}
    generation = Generation(
        generation_id="0" * 64,
        parent_id=expected_parent,
        policy=policy,
        code_sha256=code,
        dependency_lock_sha256=lock,
        runtime_versions=runtime,
        files=entries(candidate),
        license_notices=candidate.notices,
        record_counts=candidate.record_counts,
    )
    generation = generation.model_copy(update={"generation_id": generation_id(generation)})
    manifest = encoded(generation)
    if len(manifest) > MAX_MANIFEST:
        raise DurableError("generation_manifest_too_large")
    # All local parsing/lineage/rights/parent conflicts are checked before the first PUT.
    for entry in generation.files:
        _immutable(store, f"blobs/{entry.sha256}", candidate.files[entry.path])
    _immutable(store, f"generations/{generation.generation_id}.json", manifest)
    # A 2xx upload is not enough: restore every remote object before authority can advance.
    with restore(store, generation.generation_id, temporary_parent=temporary_parent) as remote:
        if remote.validated.files != candidate.files:
            raise DurableError("uploaded_candidate_differs")
        if parent_state is not None:
            # Recheck the actual read-back bytes, independent of mutable caller filesystem reads.
            compare_parent(parent_state, remote.validated)
    store.put(
        POINTER_KEY,
        encoded(Pointer(generation_id=generation.generation_id)),
        expected_etag=authority[1] if authority else None,
    )
    return Publication(generation, no_op=False)


def run_pipeline(
    store: ObjectStore,
    *,
    expected_parent: str | None,
    policy: CloudPolicy,
    operation: Callable[[DataLayout], None],
    temporary_parent: Path | None = None,
) -> Publication:
    """Existing ingestion/research works locally; any exception prevents publication."""
    authority = head(store)
    if (authority[0].generation_id if authority else None) != expected_parent:
        raise DurableError("stale_expected_parent")
    if expected_parent is not None:
        with restore(store, expected_parent, temporary_parent=temporary_parent) as restored:
            operation(restored.layout)
            return publish(
                store,
                restored.layout,
                expected_parent=expected_parent,
                policy=policy,
                temporary_parent=temporary_parent,
            )
    with _workspace(temporary_parent) as temp:
        layout = DataLayout(temp / "data")
        layout.create()
        operation(layout)
        return publish(
            store, layout, expected_parent=None, policy=policy, temporary_parent=temporary_parent
        )
