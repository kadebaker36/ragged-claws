"""Reviewed Quiver OpenAPI subset. Unknown values stay out of canonical feature facts."""

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ragged_claws.ingestion.quiver_models import Endpoint, QuiverRow
from ragged_claws.models import (
    DisclosedRange,
    EventAttribute,
    EventAttributeType,
    FinancialValue,
    FinancialValueKind,
    PartialDate,
    TemporalPrecision,
    TemporalValue,
)

PARSER_VERSION = "quiver-reviewed-json/1.0.0"
SCHEMA_SHA256 = "72b5c480c44494371c318c88072319795bf8440600998d81d297b5cd3de17af2"
PATHS: dict[Endpoint, str] = {
    "congress_v1": "/beta/live/congresstrading",
    "congress_v2": "/beta/bulk/congresstrading",
    "contracts": "/beta/live/govcontractsall",
    "lobbying": "/beta/live/lobbying",
}
FAMILIES: dict[Endpoint, str] = {
    "congress_v1": "us.congress.disclosures",
    "congress_v2": "us.congress.disclosures",
    "contracts": "us.government.procurement",
    "lobbying": "us.government.lobbying_disclosures",
}
# Explicit allowlists, including audit-only fields. No prefix/substring exclusion heuristic.
FIELDS: dict[Endpoint, frozenset[str]] = {
    "congress_v1": frozenset(
        [
            "Representative",
            "BioGuideID",
            "ReportDate",
            "TransactionDate",
            "Ticker",
            "Transaction",
            "Range",
            "District",
            "House",
            "Amount",
            "Party",
            "last_modified",
            "TickerType",
            "Description",
        ]
    ),
    "congress_v2": frozenset(
        [
            "Ticker",
            "TickerType",
            "Company",
            "Traded",
            "Transaction",
            "Trade_Size_USD",
            "Status",
            "Subholding",
            "Description",
            "Name",
            "BioGuideID",
            "Filed",
            "Party",
            "District",
            "Chamber",
            "Comments",
            "Quiver_Upload_Time",
            "State",
            "last_modified",
        ]
    ),
    "contracts": frozenset(["Ticker", "Date", "Description", "Agency", "Amount", "action_date"]),
    "lobbying": frozenset(
        ["Date", "Amount", "Client", "Issue", "Specific_Issue", "Registrant", "Ticker"]
    ),
}
REQUIRED: dict[Endpoint, tuple[str, ...]] = {
    "congress_v1": ("Representative", "Party"),
    "congress_v2": ("Traded", "Name", "BioGuideID", "Filed", "Party", "Chamber"),
    "contracts": ("Ticker", "Date", "action_date"),
    "lobbying": ("Date", "Registrant", "Ticker"),
}
ASSERTIONS: dict[str, str] = {
    "Party": "quiver_party",
    "House": "quiver_chamber",
    "Chamber": "quiver_chamber",
    "District": "quiver_district",
    "State": "quiver_state",
    "TickerType": "quiver_asset_type",
    "Status": "quiver_position_status",
    "Subholding": "quiver_subholding",
    "Issue": "quiver_lobbying_issue",
    "Specific_Issue": "quiver_lobbying_specific_issue",
}


class QuiverError(ValueError):
    """Input/access cannot be supported; messages never contain source row values or secrets."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise QuiverError("duplicate JSON field")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise QuiverError("non-finite JSON number")


def load_json(content: bytes) -> Any:
    try:
        return json.loads(
            content, parse_float=Decimal, object_pairs_hook=_object, parse_constant=_constant
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise QuiverError("invalid or ambiguous JSON response") from exc


def exact_json(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(json.dumps(k) + ":" + exact_json(v) for k, v in sorted(value.items()))
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(exact_json(v) for v in value) + "]"
    return json.dumps(value, allow_nan=False)


def text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise QuiverError("expected documented text field")
    return value


def day(value: str | None) -> TemporalValue | None:
    if value is None:
        return None
    # Field documentation promises calendar dates, not an intraday dissemination instant.
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            parsed = date.fromisoformat(value)
        elif re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        else:
            raise ValueError
    except ValueError as exc:
        raise QuiverError("invalid source calendar date") from exc
    return TemporalValue(
        raw_value=value,
        precision=TemporalPrecision.DAY,
        partial_date=PartialDate(
            raw_value=value,
            precision=TemporalPrecision.DAY,
            year=parsed.year,
            month=parsed.month,
            day=parsed.day,
        ),
    )


def clock(value: str | None) -> TemporalValue | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QuiverError("invalid vendor audit timestamp") from exc
    if parsed.tzinfo is None or parsed.microsecond:
        # Preserve unsupported clock precision; never assume the machine's timezone.
        return TemporalValue(
            raw_value=value,
            precision=TemporalPrecision.UNKNOWN,
            partial_date=PartialDate(raw_value=value, precision=TemporalPrecision.UNKNOWN),
        )
    return TemporalValue(
        raw_value=value,
        precision=TemporalPrecision.SECOND,
        timestamp=parsed,
        source_timezone="explicit-source-offset",
    )


def money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if type(value) not in (str, int, Decimal):
        raise QuiverError("invalid monetary representation")
    raw = str(value)
    if not re.fullmatch(r"-?\$?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", raw):
        raise QuiverError("unsupported monetary representation")
    try:
        result = Decimal(raw.replace("$", "").replace(",", ""))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except InvalidOperation as exc:
        raise QuiverError("invalid monetary representation") from exc


def parse_rows(content: bytes, endpoint: Endpoint, *, limit: int) -> tuple[QuiverRow, ...]:
    if len(content) > 5_000_000:
        raise QuiverError("response exceeds bounded parser size")
    payload = load_json(content)
    if not isinstance(payload, list) or len(payload) > limit:
        raise QuiverError("expected bounded documented response array")
    result: list[QuiverRow] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict) or any(key not in row for key in REQUIRED[endpoint]):
            raise QuiverError("response row lacks required documented fields")
        # Unknown fields, including every known or future performance field, never reach facts.
        allowed = {key: value for key, value in row.items() if key in FIELDS[endpoint]}
        quarantine = {key: value for key, value in row.items() if key not in FIELDS[endpoint]}
        for key in allowed:
            if key != "Amount" or endpoint != "contracts":
                text(allowed, key)
        is_trade = endpoint.startswith("congress")
        transaction_key, report_key = (
            ("Traded", "Filed") if endpoint == "congress_v2" else ("TransactionDate", "ReportDate")
        )
        occurrence = day(text(allowed, transaction_key if is_trade else "action_date"))
        reported = day(text(allowed, report_key if is_trade else "Date"))
        if occurrence is not None and reported is not None:
            assert occurrence.partial_date is not None and reported.partial_date is not None
            start = occurrence.partial_date
            end = reported.partial_date
            if (start.year, start.month, start.day) > (end.year, end.month, end.day):
                raise QuiverError("occurrence follows reported calendar date")
        uploaded = clock(text(allowed, "Quiver_Upload_Time"))
        modified = clock(text(allowed, "last_modified"))
        transaction = text(allowed, "Transaction")
        kind = (
            {"purchase": "equity_purchase", "sale": "equity_sale"}.get(transaction.casefold())
            if is_trade and transaction
            else None
        )
        if not is_trade:
            kind = "government_contract" if endpoint == "contracts" else "lobbying_disclosure"
        reason = "unsupported_transaction_classification" if is_trade and kind is None else None
        identifier = text(allowed, "BioGuideID")
        if identifier is not None and re.fullmatch(r"[A-Z][0-9]{6}", identifier) is None:
            raise QuiverError("invalid BioGuide identifier representation")
        values: tuple[FinancialValue, ...] = ()
        ranges: tuple[DisclosedRange, ...] = ()
        notes = ["native_row_id_not_documented", "economic_ownership_not_documented"]
        if occurrence is None:
            notes.append("occurrence_time_not_supplied")
        if reported is None:
            notes.append("reported_date_not_supplied")
        amount_key = "Trade_Size_USD" if endpoint == "congress_v2" else "Amount"
        amount = money(allowed.get(amount_key))
        if is_trade:
            if amount is not None and amount < 0:
                raise QuiverError("negative disclosed trade lower bound")
            raw_range = text(allowed, "Range")
            lower, upper = amount, None
            if raw_range:
                match = re.fullmatch(
                    r"(\$?[\d,]+(?:\.\d+)?)\s*-\s*(\$?[\d,]+(?:\.\d+)?)", raw_range
                )
                if match:
                    lower, upper = money(match[1]), money(match[2])
                    if amount is not None and lower != amount:
                        raise QuiverError("disclosed range contradicts supplied lower bound")
                    if lower is not None and upper is not None and lower > upper:
                        raise QuiverError("inverted disclosed range")
                else:
                    notes.append("range_text_not_parsed")
            raw_amount = str(allowed.get(amount_key, ""))
            if raw_range or amount is not None:
                ranges = (
                    DisclosedRange(
                        name="disclosed_transaction_amount",
                        raw_text=raw_range or raw_amount,
                        lower_bound=lower,
                        upper_bound=upper,
                        currency="USD",
                        parser_version=PARSER_VERSION,
                    ),
                )
        elif amount is not None:
            values = (
                FinancialValue(
                    name="contract_obligated_amount"
                    if endpoint == "contracts"
                    else "reported_lobbying_spend",
                    kind=FinancialValueKind.MONETARY_AMOUNT,
                    value=amount,
                    currency="USD",
                ),
            )
        assertions = tuple(
            EventAttribute(
                name=name, value_type=EventAttributeType.TEXT, value=value, raw_value=value
            )
            for key, name in ASSERTIONS.items()
            if (value := text(allowed, key)) is not None
        )
        # This hash is for comparison/reconciliation only; NEVER a permanent event ID/dedupe key.
        facts = {
            k: v for k, v in allowed.items() if k not in ("last_modified", "Quiver_Upload_Time")
        }
        notes.append("public_availability_requires_primary_evidence")
        result.append(
            QuiverRow(
                row_index=index,
                fact_hash=hashlib.sha256(exact_json(facts).encode()).hexdigest(),
                event_type=kind,
                occurrence_time=occurrence,
                reported_time=reported,
                uploaded_time=uploaded,
                modified_time=modified,
                actionability=None,
                person_identifier=identifier,
                person_name=text(
                    allowed, "Name" if endpoint == "congress_v2" else "Representative"
                ),
                ticker_hint=text(allowed, "Ticker"),
                subholding_assertion=text(allowed, "Subholding"),
                financial_values=values,
                disclosed_ranges=ranges,
                vendor_assertions=assertions,
                quarantined_json=exact_json(quarantine),
                normalization_notes=tuple(notes),
                reason=reason,
            )
        )
    return tuple(result)
