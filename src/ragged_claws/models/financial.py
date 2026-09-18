"""Exact canonical financial values and disclosed ranges."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import StringConstraints, model_validator

from ragged_claws.models.base import NonEmptyStr, VersionedModel

CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class FinancialValueKind(StrEnum):
    MONETARY_AMOUNT = "monetary_amount"
    UNIT_PRICE = "unit_price"
    QUANTITY = "quantity"
    PERCENTAGE = "percentage"


class FinancialValue(VersionedModel):
    """An exact numeric value whose kind determines currency/unit requirements."""

    financial_value_id: UUID
    kind: FinancialValueKind
    value: Decimal
    currency: CurrencyCode | None = None
    unit: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_units(self) -> Self:
        if self.kind is FinancialValueKind.MONETARY_AMOUNT:
            if self.currency is None or self.unit is not None:
                raise ValueError("monetary amounts require currency and forbid unit")
        elif self.kind is FinancialValueKind.UNIT_PRICE:
            if self.currency is None or self.unit is None:
                raise ValueError("unit prices require currency and unit")
        elif self.kind is FinancialValueKind.QUANTITY:
            if self.currency is not None or self.unit is None:
                raise ValueError("quantities require unit and forbid currency")
        elif self.currency is not None or self.unit is not None:
            raise ValueError("percentages forbid currency and unit")
        return self


class DisclosedRange(VersionedModel):
    """A disclosed range that preserves raw text and never invents a midpoint."""

    disclosed_range_id: UUID
    raw_text: NonEmptyStr
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None
    currency: CurrencyCode | None = None
    unit: NonEmptyStr | None = None
    parser_version: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("lower_bound cannot exceed upper_bound")
        return self
