"""Strict documented API-v2 subset, exact values and honest partial-date precision."""

import calendar
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ragged_claws.ingestion.littlesis_models import LittleSisResource, LittleSisSnapshot
from ragged_claws.models import PartialDate, TemporalPrecision, TemporalValue

LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"


class LittleSisError(ValueError):
    """Source structure, semantics or access cannot be defended."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LittleSisError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(content: str | bytes) -> Any:
    try:
        return json.loads(
            content,
            parse_float=Decimal,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _invalid_number(),
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise LittleSisError("invalid or ambiguous LittleSis JSON") from exc


def _invalid_number() -> None:
    raise LittleSisError("non-finite source number")


def exact_json(value: Any) -> str:
    """Deterministic JSON preserving Decimal numeric tokens, not binary floats."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise LittleSisError("non-finite source number")
        return str(value)
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(json.dumps(k) + ":" + exact_json(v) for k, v in sorted(value.items()))
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(exact_json(v) for v in value) + "]"
    return json.dumps(value, allow_nan=False, ensure_ascii=True)


def source_id(value: Any) -> int:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return int(value)
    raise LittleSisError("source ID must be a positive integer")


def partial_date(value: Any) -> TemporalValue | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise LittleSisError("source date must be text or null")
    match = re.fullmatch(r"([0-9]{4})(?:-([0-9]{2})(?:-([0-9]{2}))?)?", value)
    if match is None:
        raise LittleSisError("unsupported source date syntax")
    year = int(match[1])
    month = int(match[2] or 0) or None
    day = int(match[3] or 0) or None
    if not 1000 <= year <= 3000 or (day is not None and month is None):
        raise LittleSisError("invalid source partial date")
    precision = (
        TemporalPrecision.DAY
        if day
        else (TemporalPrecision.MONTH if month else TemporalPrecision.YEAR)
    )
    try:
        partial = PartialDate(raw_value=value, precision=precision, year=year, month=month, day=day)
        return TemporalValue(raw_value=value, precision=precision, partial_date=partial)
    except ValueError as exc:
        raise LittleSisError("invalid source calendar date") from exc


def _date_bounds(value: TemporalValue) -> tuple[date, date]:
    partial = value.partial_date
    if partial is None or partial.year is None:
        raise LittleSisError("unsupported effective precision")
    year, month, day = partial.year, partial.month, partial.day
    if month is None:
        return date(year, 1, 1), date(year, 12, 31)
    if day is None:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    return date(year, month, day), date(year, month, day)


def parse_snapshot(content: bytes, *, observation_id: UUID) -> LittleSisSnapshot:
    if len(content) > 5_000_000:
        raise LittleSisError("snapshot exceeds the narrow parser size limit")
    payload = load_json(content)
    if not isinstance(payload, dict) or "errors" in payload:
        raise LittleSisError("expected successful LittleSis response object")
    meta = payload.get("meta")
    if (
        not isinstance(meta, dict)
        or meta.get("license") != LICENSE_URL
        or meta.get("apiVersion") != "2.0"
        or not isinstance(meta.get("copyright"), str)
        or not meta["copyright"].strip()
    ):
        raise LittleSisError("unsupported or missing API/database attribution metadata")
    data = payload.get("data")
    if isinstance(data, dict):
        data = [data]
    included = payload.get("included", [])
    if not isinstance(data, list) or not isinstance(included, list):
        raise LittleSisError("data/included must contain resource objects")
    resources: dict[tuple[str, int], LittleSisResource] = {}
    for item in (*data, *included):
        if not isinstance(item, dict) or item.get("type") not in ("entities", "relationships"):
            raise LittleSisError("unsupported resource type")
        kind, identity = item["type"], source_id(item.get("id"))
        attributes = item.get("attributes")
        if not isinstance(attributes, dict) or source_id(attributes.get("id")) != identity:
            raise LittleSisError("resource/attribute ID contradiction")
        start = partial_date(attributes.get("start_date"))
        end = partial_date(attributes.get("end_date"))
        if start is not None and end is not None and _date_bounds(start)[0] > _date_bounds(end)[1]:
            raise LittleSisError("effective start provably follows effective end")
        updated = attributes.get("updated_at")
        curated = None
        if updated is not None:
            if not isinstance(updated, str):
                raise LittleSisError("updated_at must be an aware source timestamp")
            try:
                curated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                if curated.tzinfo is None or curated.utcoffset() is None:
                    raise ValueError
            except ValueError as exc:
                raise LittleSisError("updated_at must be an aware source timestamp") from exc
        if kind == "entities":
            if not isinstance(attributes.get("name"), str) or not attributes["name"].strip():
                raise LittleSisError("entity requires a source name")
        else:
            source_id(attributes.get("entity1_id"))
            source_id(attributes.get("entity2_id"))
            category = attributes.get("category_id")
            if type(category) is not int:
                raise LittleSisError("relationship category must be an integer")
            if (
                attributes.get("is_current") is not None
                and type(attributes["is_current"]) is not bool
            ):
                raise LittleSisError("is_current must be boolean or unknown")
        # Only this resource's fields affect its semantic fingerprint. Curation is audit metadata.
        semantic = {
            **item,
            "attributes": {k: v for k, v in attributes.items() if k != "updated_at"},
        }
        urls = [item.get(k) for k in ("self", "entity", "related")]
        links = item.get("links", {})
        if not isinstance(links, dict):
            raise LittleSisError("resource links must be an object")
        urls.extend(links.values())
        resource = LittleSisResource(
            source_type=kind,
            source_id=identity,
            payload_json=exact_json(item),
            semantic_hash=hashlib.sha256(exact_json(semantic).encode()).hexdigest(),
            valid_from=start,
            valid_to=end,
            updated_at_raw=updated,
            curated_at=curated,
            source_urls=tuple(sorted({url for url in urls if isinstance(url, str)})),
        )
        key = (kind, identity)
        if key in resources and resources[key] != resource:
            raise LittleSisError("conflicting duplicate source resource")
        resources[key] = resource
    return LittleSisSnapshot(
        source_version_id=observation_id,
        resources=tuple(resources[key] for key in sorted(resources)),
        copyright=meta["copyright"],
        license_url=meta["license"],
        api_version=meta["apiVersion"],
        metadata_json=exact_json(meta),
    )
