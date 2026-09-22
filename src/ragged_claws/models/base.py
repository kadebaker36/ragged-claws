"""Shared strict-model configuration and canonical scalar types."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, StringConstraints

MODEL_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Slug = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[a-z][a-z0-9_.-]*$"),
]
JsonScalar = None | bool | int | Decimal | str


def _normalize_aware_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_normalize_aware_utc)]


class CanonicalModel(BaseModel):
    """Base for immutable canonical values that reject undeclared source fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class VersionedModel(CanonicalModel):
    """Base for versioned canonical records and independently serialized claims."""

    schema_version: Literal["1.0.0"] = MODEL_SCHEMA_VERSION
