"""Versioned synchronization artifacts, separate from canonical analytical schemas."""

import re
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from ragged_claws.models.base import CanonicalModel, NonEmptyStr
from ragged_claws.models.evidence import Sha256Hex

MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILES = 4096
MAX_MANIFEST = 2 * 1024 * 1024
ROOTS = frozenset({"raw", "staging", "curated", "research", "snapshots"})


class DurableError(ValueError):
    """Safe countable rejection; never includes a payload, SDK error or credential value."""

    def __init__(self, reason: str, count: int = 1) -> None:
        self.reasons = {reason: count}
        super().__init__(reason)


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 512
        or path.is_absolute()
        or path.as_posix() != value
        or "\\" in value
        or ":" in value
        or any(
            not re.fullmatch(r"[A-Za-z0-9_.-]+", p)
            or p in {".", ".."}
            or p.startswith(".")
            or p.endswith(".")
            or p.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10)),
            }
            for p in path.parts
        )
    ):
        raise DurableError("unsafe_relative_path")
    return value


class CloudPolicy(CanonicalModel):
    version: Literal["1.0.0"] = "1.0.0"
    scope: Literal["public_sec", "invented_engineering"] = "public_sec"
    review_reference: NonEmptyStr
    allow_littlesis: bool = False
    invented_attestation: bool = False

    @model_validator(mode="after")
    def explicit_scope(self) -> Self:
        if (self.scope == "invented_engineering") != self.invented_attestation:
            raise ValueError("invented export requires explicit engineering attestation")
        if self.allow_littlesis and self.scope != "public_sec":
            raise ValueError("share-alike scope must be reviewed separately from invented data")
        return self


class FileEntry(CanonicalModel):
    path: str
    sha256: Sha256Hex
    size: int = Field(ge=0, le=MAX_FILE)

    @field_validator("path")
    @classmethod
    def valid_path(cls, value: str) -> str:
        safe_path(value)
        if PurePosixPath(value).parts[0] not in ROOTS:
            raise DurableError("outside_durable_allowlist")
        return value


class Generation(CanonicalModel):
    format_version: Literal["1.0.0"] = "1.0.0"
    generation_id: Sha256Hex
    parent_id: Sha256Hex | None
    policy: CloudPolicy
    code_sha256: Sha256Hex
    dependency_lock_sha256: Sha256Hex
    canonical_schema_version: Literal["1.0.0"] = "1.0.0"
    runtime_versions: dict[str, str]
    files: tuple[FileEntry, ...] = Field(max_length=MAX_FILES)
    license_notices: tuple[str, ...] = ()
    record_counts: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded_unique_files(self) -> Self:
        names = [f.path.casefold() for f in self.files]
        if len(set(names)) != len(names) or sum(f.size for f in self.files) > MAX_TOTAL:
            raise DurableError("duplicate_paths_or_generation_too_large")
        if tuple(sorted(self.files, key=lambda item: item.path)) != self.files:
            raise DurableError("generation_files_not_sorted")
        return self


class Pointer(CanonicalModel):
    format_version: Literal["1.0.0"] = "1.0.0"
    generation_id: Sha256Hex
