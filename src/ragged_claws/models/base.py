"""Shared strict-model configuration and canonical scalar types."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

MODEL_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Slug = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[a-z][a-z0-9_.-]*$"),
]
JsonScalar = None | bool | int | Decimal | str


class CanonicalModel(BaseModel):
    """Base for immutable canonical values that reject undeclared source fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class VersionedModel(CanonicalModel):
    """Base for versioned canonical records and independently serialized claims."""

    schema_version: Literal["1.0.0"] = MODEL_SCHEMA_VERSION
