"""Source-specific contracts over canonical objects, never XML/SGML parsers.

A future canonical source implements PurchaseContract and registers it with CanonicalWatch.
The PIT filter, identity checks, economic-Event deduplication and clusters remain shared.
"""

import json
import re
from decimal import Decimal
from typing import Protocol

from ragged_claws.models import Event, FinancialValueKind, ObservationRole, SourceObservation
from ragged_claws.watch.models import ActorReference


class PurchaseContract(Protocol):
    venue: str
    attribution: str

    def supports(self, event: Event) -> bool: ...
    def supports_observation(self, observation: SourceObservation) -> bool: ...
    def actors(self, event: Event) -> tuple[ActorReference, ...]: ...
    def financial_facts(
        self, event: Event
    ) -> tuple[Decimal | None, Decimal | None, str | None]: ...


def attributes(event: Event) -> dict[str, str | bool | int | Decimal]:
    return {a.name: a.value for a in event.attributes}


def supported_purchase(event: Event) -> bool:
    attrs = attributes(event)
    return (
        event.event_type == "equity_purchase"
        and attrs.get("transaction_code") == "P"
        and isinstance(attrs.get("source_row"), str)
        and re.fullmatch(
            r"nonDerivativeTable/nonDerivativeTransaction\[[1-9][0-9]*\]", str(attrs["source_row"])
        )
        is not None
    )


class SecPurchaseContract:
    venue = "unknown_p_includes_open_market_or_private"
    attribution = "filing_reporting_owners_not_row_allocation"

    def supports(self, event: Event) -> bool:
        return supported_purchase(event)

    def supports_observation(self, observation: SourceObservation) -> bool:
        return (
            observation.lineage.observation_role is ObservationRole.PRIMARY_SOURCE
            and observation.lineage.source_family == "sec.ownership"
            and observation.adapter_version == "sec-form4/1.0.0"
        )

    def actors(self, event: Event) -> tuple[ActorReference, ...]:
        raw = attributes(event).get("reporting_owners")
        if not isinstance(raw, str):
            return ()
        owners = json.loads(raw)
        if not isinstance(owners, list):
            raise ValueError("invalid canonical reporting owner attribute")
        result: dict[str, ActorReference] = {}
        for owner in owners:
            if not isinstance(owner, dict):
                raise ValueError("invalid canonical reporting owner")
            cik = owner.get("cik")
            if not isinstance(cik, str) or re.fullmatch(r"[0-9]{10}", cik) is None:
                raise ValueError("invalid canonical reporting owner reference")
            actor = ActorReference(
                reference=f"sec_cik:{cik}",
                name=owner.get("name"),
                director=owner.get("director"),
                officer=owner.get("officer"),
                ten_percent_owner=owner.get("ten_percent_owner"),
                officer_title=owner.get("officer_title"),
            )
            if cik in result and result[cik] != actor:
                raise ValueError("contradictory canonical reporting owners")
            result[cik] = actor
        return tuple(result[k] for k in sorted(result))

    def financial_facts(self, event: Event) -> tuple[Decimal | None, Decimal | None, str | None]:
        attrs = attributes(event)
        shares = next(
            (
                v.value
                for v in event.financial_values
                if v.name == "transaction_shares"
                and v.kind is FinancialValueKind.QUANTITY
                and v.unit == "shares"
            ),
            None,
        )
        price = attrs.get("reported_price_per_share")
        price = price if isinstance(price, Decimal) and price.is_finite() else None
        reason = (
            "range_or_footnote_requires_exactness_review"
            if event.disclosed_ranges or attrs.get("footnote_ids", "[]") != "[]"
            else None
        )
        return shares, price, reason


DEFAULT_CONTRACTS: tuple[PurchaseContract, ...] = (SecPurchaseContract(),)
