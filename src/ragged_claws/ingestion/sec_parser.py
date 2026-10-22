"""Fail-closed parsing of complete EDGAR submissions and explicit ownership XML."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid5
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from ragged_claws.ingestion.sec_models import OwnershipRow, ReportingOwner, SecFiling
from ragged_claws.models import TemporalPrecision, TemporalValue
from ragged_claws.resolution import normalize_cik

FILING_NAMESPACE = UUID("c4915726-7a86-43f8-960b-aa0f8df3f041")
ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")


class SecParseError(ValueError):
    """Source evidence is contradictory or unsupported; raw capture is retained."""


def parse_acceptance(
    raw: str | None,
    *,
    timezone: str | None,
) -> tuple[TemporalValue | None, str | None]:
    if not raw:
        return None, "missing_acceptance"
    if not re.fullmatch(r"[0-9]{14}", raw):
        return None, "malformed_acceptance"
    try:
        naive = datetime.strptime(raw, "%Y%m%d%H%M%S")
    except ValueError:
        return None, "malformed_acceptance"
    if timezone != "America/New_York":
        return None, "acceptance_timezone_unconfirmed"
    zone = ZoneInfo(timezone)
    instants = {
        candidate.astimezone(UTC)
        for fold in (0, 1)
        if (candidate := naive.replace(tzinfo=zone, fold=fold))
        .astimezone(UTC)
        .astimezone(zone)
        .replace(tzinfo=None)
        == naive
    }
    if len(instants) != 1:
        return None, "ambiguous_or_nonexistent_acceptance"
    return TemporalValue(
        raw_value=raw,
        precision=TemporalPrecision.SECOND,
        timestamp=instants.pop(),
        source_timezone=timezone,
    ), None


def parse_filing(
    content: bytes,
    *,
    accession: str,
    source_version_id: UUID,
    acceptance_timezone: str | None = None,
    document_name: str | None = None,
    form_type: str | None = None,
    filed_as_of: date | None = None,
    acceptance_raw: str | None = None,
) -> SecFiling:
    """Bare XML requires explicit accession/document/form; timing is never inferred."""
    if not ACCESSION.fullmatch(accession):
        raise SecParseError("invalid accession")
    if len(content) > 5_000_000:
        raise SecParseError("filing exceeds the narrow parser size limit")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SecParseError("ownership input must be UTF-8") from exc
    header: str | None = None
    sequence = "1"
    if text.lstrip().startswith("<SEC-DOCUMENT>"):
        if (
            text.count("<DOCUMENT>") != text.count("</DOCUMENT>")
            or text.count("<SEC-HEADER>") != 1
            or text.count("</SEC-HEADER>") != 1
            or not text.rstrip().endswith("</SEC-DOCUMENT>")
        ):
            raise SecParseError("incomplete or ambiguous SEC submission wrapper")
        header_match = re.search(r"<SEC-HEADER>(.*?)</SEC-HEADER>", text, re.S)
        if header_match is None:
            raise SecParseError("missing SEC header")
        header = header_match[1]
        header_accession = _header(header, "ACCESSION NUMBER")
        root_accession = re.search(r"<SEC-DOCUMENT>([^\s]+)", text)
        if (
            header_accession != accession
            or root_accession is None
            or (root_accession[1] != f"{accession}.txt")
        ):
            raise SecParseError("caller/header/submission accession contradiction")
        header_form = _header(header, "CONFORMED SUBMISSION TYPE")
        if form_type is not None and form_type != header_form:
            raise SecParseError("caller/header form contradiction")
        form_type = header_form
        header_date = _header(header, "FILED AS OF DATE", required=False)
        parsed_date = _date(header_date, compact=True) if header_date else None
        if filed_as_of is not None and filed_as_of != parsed_date:
            raise SecParseError("caller/header filed-as-of contradiction")
        filed_as_of = parsed_date
        acceptance_values = re.findall(r"<ACCEPTANCE-DATETIME>([^\r\n<]*)", header)
        if len(acceptance_values) > 1:
            raise SecParseError("multiple acceptance timestamps")
        header_acceptance = acceptance_values[0].strip() if acceptance_values else None
        if acceptance_raw is not None and acceptance_raw != header_acceptance:
            raise SecParseError("caller/header acceptance contradiction")
        acceptance_raw = header_acceptance
        candidates: list[tuple[str, str, str]] = []
        for block in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", text, re.S):
            match = re.search(r"<XML>\s*(.*?)\s*</XML>", block, re.S)
            if match is None:
                continue
            root = _xml(match[1])
            if root.tag != "ownershipDocument":
                continue
            kind = _tag(block, "TYPE")
            if kind != form_type:
                raise SecParseError("header/document form contradiction")
            candidates.append((_tag(block, "FILENAME"), _tag(block, "SEQUENCE"), match[1]))
        if len(candidates) != 1:
            raise SecParseError("submission requires exactly one ownership XML document")
        name, sequence, text = candidates[0]
        if document_name is not None and document_name != name:
            raise SecParseError("caller/document name contradiction")
        document_name = name
    if not document_name or not form_type:
        raise SecParseError("bare XML requires explicit document name and form type")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", document_name):
        raise SecParseError("unsafe document name")
    root = _xml(text)
    if root.tag != "ownershipDocument" or _text(root, "documentType", required=True) != form_type:
        raise SecParseError("header/metadata/XML form contradiction")
    xml_accession = _text(root, "accessionNumber")
    if xml_accession and xml_accession != accession:
        raise SecParseError("caller/XML accession contradiction")
    xml_issuer = normalize_cik(_text(root, "issuer/issuerCik", required=True))
    if header is not None:
        issuer_sections = re.findall(r"ISSUER:(.*?)(?=\n[A-Z][A-Z -]*:|\Z)", header, re.S)
        if len(issuer_sections) != 1:
            raise SecParseError("missing or ambiguous header issuer")
        cik = re.search(r"CENTRAL INDEX KEY:\s*([0-9]+)", issuer_sections[0])
        if cik is None or normalize_cik(cik[1]) != xml_issuer:
            raise SecParseError("header/XML issuer contradiction")
    owners = tuple(_owner(owner) for owner in root.findall("reportingOwner"))
    if not owners or len({owner.cik for owner in owners}) != len(owners):
        raise SecParseError("missing or duplicate reporting owners")
    if header is not None:
        owner_sections = re.findall(
            r"REPORTING-OWNER:(.*?)(?=\n[A-Z][A-Z -]*:|\Z)",
            header,
            re.S,
        )
        header_owners = []
        for section in owner_sections:
            cik = re.search(r"CENTRAL INDEX KEY:\s*([0-9]+)", section)
            if cik is None:
                raise SecParseError("header owner has no CIK")
            header_owners.append(normalize_cik(cik[1]))
        if set(header_owners) != {owner.cik for owner in owners}:
            raise SecParseError("header/XML reporting-owner contradiction")
    notes: dict[str, str] = {}
    for note in root.findall("footnotes/footnote"):
        key = note.get("id")
        if not key or key in notes:
            raise SecParseError("missing or duplicate footnote ID")
        notes[key] = "".join(note.itertext()).strip()
    rows = tuple(
        _row(row, table, index, form_type)
        for table in ("nonDerivativeTable", "derivativeTable")
        for index, row in enumerate(root.findall(f"{table}/*"), 1)
    )
    for row in rows:
        if not set(row.footnote_ids) <= notes.keys():
            raise SecParseError("row references an absent footnote")
    acceptance, timing_reason = parse_acceptance(acceptance_raw, timezone=acceptance_timezone)
    return SecFiling(
        source_version_id=source_version_id,
        filing_group_id=uuid5(FILING_NAMESPACE, f"sec_accession:{accession}"),
        accession=accession,
        document_name=document_name,
        document_sequence=sequence,
        form_type=form_type,
        exclusion_reason=f"unsupported_form:{form_type}" if form_type != "4" else None,
        filed_as_of=filed_as_of,
        acceptance_raw=acceptance_raw,
        acceptance_time=acceptance,
        timing_reason=timing_reason,
        issuer_cik=xml_issuer,
        issuer_name=_text(root, "issuer/issuerName", required=True),
        issuer_symbol=_text(root, "issuer/issuerTradingSymbol") or None,
        owners=owners,
        rows=rows,
        footnotes=notes,
    )


def _xml(text: str) -> ET.Element:
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", text, re.I):
        raise SecParseError("XML DTD/entity declarations are unsupported")
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise SecParseError("invalid ownership XML") from exc


def _header(text: str, key: str, *, required: bool = True) -> str | None:
    values = re.findall(rf"^{re.escape(key)}:\s*([^\r\n]+)", text, re.M)
    if len(values) > 1 or (required and not values):
        raise SecParseError(f"missing or duplicate header {key}")
    return values[0].strip() if values else None


def _tag(text: str, key: str) -> str:
    values: list[str] = re.findall(rf"<{key}>([^\r\n<]+)", text)
    if len(values) != 1:
        raise SecParseError(f"missing or duplicate document {key}")
    return values[0].strip()


def _text(root: ET.Element, path: str, *, required: bool = False) -> str:
    nodes = root.findall(path)
    if len(nodes) > 1:
        raise SecParseError(f"duplicate XML field {path}")
    value = (nodes[0].text or "").strip() if nodes else ""
    if required and not value:
        raise SecParseError(f"missing XML field {path}")
    return value


def _date(raw: str, *, compact: bool = False) -> date:
    try:
        pattern = r"[0-9]{8}" if compact else r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
        if not re.fullmatch(pattern, raw):
            raise ValueError
        return datetime.strptime(raw, "%Y%m%d" if compact else "%Y-%m-%d").date()
    except ValueError as exc:
        raise SecParseError("invalid source date") from exc


def _owner(root: ET.Element) -> ReportingOwner:
    roles: dict[str, bool | None] = {}
    for name, tag in (
        ("director", "isDirector"),
        ("officer", "isOfficer"),
        ("ten_percent_owner", "isTenPercentOwner"),
        ("other", "isOther"),
    ):
        raw = _text(root, f"reportingOwnerRelationship/{tag}")
        if raw not in ("", "0", "1", "true", "false"):
            raise SecParseError("invalid reporting-owner relationship flag")
        roles[name] = None if not raw else raw in ("1", "true")
    return ReportingOwner(
        cik=normalize_cik(_text(root, "reportingOwnerId/rptOwnerCik", required=True)),
        name=_text(root, "reportingOwnerId/rptOwnerName", required=True),
        director=roles["director"],
        officer=roles["officer"],
        ten_percent_owner=roles["ten_percent_owner"],
        other=roles["other"],
        officer_title=_text(root, "reportingOwnerRelationship/officerTitle") or None,
        other_text=_text(root, "reportingOwnerRelationship/otherText") or None,
    )


def _row(root: ET.Element, table: str, index: int, form: str) -> OwnershipRow:
    code = _text(root, "transactionCoding/transactionCode") or None
    reason = None
    if form != "4":
        reason = f"unsupported_form:{form}"
    elif table != "nonDerivativeTable":
        reason = "derivative_table"
    elif root.tag != "nonDerivativeTransaction":
        reason = "non_transaction_holding"
    elif code not in ("P", "S"):
        reason = f"unsupported_code:{code or 'missing'}"
    elif (row_form := _text(root, "transactionCoding/transactionFormType")) not in ("", "4"):
        reason = f"unsupported_transaction_form:{row_form}"
    raw_date = _text(root, "transactionDate/value")
    raw_shares = _text(root, "transactionAmounts/transactionShares/value")
    raw_price = _text(root, "transactionAmounts/transactionPricePerShare/value")
    if reason is None and not raw_date:
        reason = "missing_transaction_date"
    direct = _text(root, "ownershipNature/directOrIndirectOwnership/value") or None
    acquired = _text(root, "transactionAmounts/transactionAcquiredDisposedCode/value") or None
    if direct not in (None, "D", "I") or acquired not in (None, "A", "D"):
        raise SecParseError("unsupported ownership/acquisition flag")
    if reason is None and acquired not in (None, "A" if code == "P" else "D"):
        raise SecParseError("transaction code contradicts acquired/disposed flag")
    return OwnershipRow(
        coordinate=f"{table}/{root.tag}[{index}]",
        table=table,
        kind=root.tag,
        code=code,
        security_title=_text(root, "securityTitle/value") or None,
        transaction_date=_date(raw_date) if raw_date else None,
        shares=_decimal(raw_shares),
        price=_decimal(raw_price),
        acquired_disposed=acquired,
        direct_indirect=direct,
        nature_of_ownership=_text(root, "ownershipNature/natureOfOwnership/value") or None,
        footnote_ids=tuple(sorted({node.get("id", "") for node in root.iter("footnoteId")})),
        exclusion_reason=reason,
    )


def _decimal(raw: str) -> Decimal | None:
    if not raw:
        return None
    try:
        if not re.fullmatch(r"\+?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", raw):
            raise ValueError
        value = Decimal(raw)
        if not value.is_finite() or value < 0:
            raise ValueError
        return value
    except (InvalidOperation, ValueError) as exc:
        raise SecParseError("invalid source numeric value") from exc
