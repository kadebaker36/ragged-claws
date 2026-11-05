"""Official daily master-index discovery, canonical ingestion and resumable accounting.

Index metadata never supplies transaction/public/actionable time or instrument identity.
"""

import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from ragged_claws.ingestion.sec import SecForm4Adapter
from ragged_claws.ingestion.sec_http import (
    SecBoundedAccessError,
    SecFilingClient,
    fetch_watch_resource,
)
from ragged_claws.ingestion.sec_parser import SecParseError
from ragged_claws.models import RetentionClass
from ragged_claws.models.base import CanonicalModel, UtcDatetime
from ragged_claws.storage import (
    CanonicalParquetStore,
    DataLayout,
    capture_raw_bytes,
    load_manifest,
    raw_object_path,
)
from ragged_claws.temporal import normalize_utc
from ragged_claws.watch.contracts import supported_purchase
from ragged_claws.watch.ledger import CanonicalWatch
from ragged_claws.watch.models import DiscoveryCompleteness

VERSION = "sec-forward-discovery/1.0.0"
HEADER = "CIK|Company Name|Form Type|Date Filed|File Name"


class FilingReference(CanonicalModel):
    filing_date: date
    filing_date_raw: str
    form_type: str
    filer_cik: str
    filer_name: str
    archive_path: str
    accession: str


class FilingProgress(CanonicalModel):
    accession: str
    references: tuple[FilingReference, ...]
    selected_archive_path: str
    state: Literal["unprocessed", "ingested", "rejected"] = "unprocessed"
    reason: str | None = None
    event_ids: tuple[UUID, ...] = ()
    p_event_ids: tuple[UUID, ...] = ()
    processed_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> "FilingProgress":
        if (self.state == "unprocessed") != (self.processed_at is None):
            raise ValueError("processing state requires its observation clock")
        if not set(self.p_event_ids) <= set(self.event_ids):
            raise ValueError("purchase Events outside ingested filing")
        if self.state != "ingested" and (self.event_ids or self.p_event_ids):
            raise ValueError("non-ingested filing has canonical Events")
        return self


class DiscoveryScan(CanonicalModel):
    format_version: Literal["sec-forward-discovery/1.0.0"] = "sec-forward-discovery/1.0.0"
    index_day: date
    index_capture_id: UUID
    retrieved_at: UtcDatetime
    filings: tuple[FilingProgress, ...]
    cursor: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def consistent_cursor(self) -> "DiscoveryScan":
        if self.cursor > len(self.filings):
            raise ValueError("cursor outside scan")
        keys = [f.accession for f in self.filings]
        if keys != sorted(set(keys)):
            raise ValueError("scan filings must be unique and accession sorted")
        if any(f.state == "unprocessed" for f in self.filings[: self.cursor]):
            raise ValueError("cursor skipped an unprocessed filing")
        if any(f.state != "unprocessed" for f in self.filings[self.cursor :]):
            raise ValueError("processed filing after cursor")
        clocks = [f.processed_at for f in self.filings[: self.cursor] if f.processed_at is not None]
        if clocks and (clocks != sorted(clocks) or clocks[0] < self.retrieved_at):
            raise ValueError("processing clocks precede capture or are out of order")
        return self

    def completeness(self, layout: DataLayout, *, as_of: datetime) -> DiscoveryCompleteness:
        as_of = normalize_utc(as_of)
        if self.retrieved_at > as_of:
            raise ValueError("index was not observed by report as-of time")
        visible = [
            f for f in self.filings if f.processed_at is not None and f.processed_at <= as_of
        ]
        cursor = len(visible)
        watch = CanonicalWatch(CanonicalParquetStore(layout, read_only=True))
        event_map = {e.event_id: e for e in watch.events}
        qualifying = unresolved = 0
        for eid in {e for f in visible if f.state == "ingested" for e in f.p_event_ids}:
            if eid not in event_map:
                raise ValueError("scan references missing canonical event")
            row, _ = watch.candidate(event_map[eid], as_of)
            if row is not None:
                if row.status == "qualifying_common_stock":
                    qualifying += 1
                else:
                    unresolved += 1
        return DiscoveryCompleteness(
            index_day=self.index_day,
            capture_id=self.index_capture_id,
            discovered_form4_count=len(self.filings),
            processed_filing_count=cursor,
            remaining_unprocessed_count=len(self.filings) - cursor,
            rejected_count=sum(f.state == "rejected" for f in visible),
            successfully_ingested_count=sum(f.state == "ingested" for f in visible),
            qualifying_p_event_count=qualifying,
            unresolved_p_event_count=unresolved,
            cursor=cursor,
            index_processing_complete=cursor == len(self.filings),
        )


def index_url(day: date) -> str:
    return (
        f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/"
        f"QTR{(day.month - 1) // 3 + 1}/master.{day:%Y%m%d}.idx"
    )


def _parse_index(content: bytes, day: date) -> tuple[FilingProgress, ...]:
    if len(content) > 2 * 1024**2:
        raise ValueError("index_size_bound")
    lines = content.decode("utf-8-sig").splitlines()
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    expected = f"{months[day.month - 1]} {day.day}, {day.year}"
    received = [
        re.sub(r"\s+", " ", line.partition(":")[2].strip())
        for line in lines
        if line.startswith("Last Data Received:")
    ]
    padded = f"{months[day.month - 1]} {day.day:02}, {day.year}"
    if (received not in ([expected], [padded])) or lines.count(HEADER) != 1:
        raise ValueError("index_header_mismatch")
    start = lines.index(HEADER) + 1
    if start >= len(lines) or re.fullmatch(r"-+", lines[start]) is None:
        raise ValueError("index_separator_missing")
    groups: dict[str, list[FilingReference]] = defaultdict(list)
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 5:
            raise ValueError("malformed_index_row")
        cik, name, form, filed_raw, path = fields
        match = re.fullmatch(r"edgar/data/([0-9]{1,10})/([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt", path)
        if (
            match is None
            or re.fullmatch(r"[0-9]{1,10}", cik) is None
            or int(match[1]) != int(cik)
            or not name.strip()
            or not form.strip()
        ):
            raise ValueError("unsafe_or_contradictory_index_reference")
        filed = date.fromisoformat(filed_raw)
        if filed > day:
            raise ValueError("future_index_filing_date")
        groups[match[2]].append(
            FilingReference(
                filing_date=filed,
                filing_date_raw=filed_raw,
                form_type=form,
                filer_cik=cik,
                filer_name=name,
                archive_path=path,
                accession=match[2],
            )
        )
    result = []
    for accession, refs in sorted(groups.items()):
        if not any(r.form_type == "4" for r in refs):
            continue
        if len({r.form_type for r in refs}) > 1 or len({r.filing_date for r in refs}) > 1:
            # Keep all contradictory references in the scan. Rejection consumes its cursor slot.
            reason = "conflicting_index_form_or_date"
        else:
            reason = None
        # Different filer paths can reference one accession. Retain all, choose one literal
        # reference deterministically, never claim alias byte equivalence or try substitutes.
        selected = min(refs, key=lambda r: (int(r.filer_cik), r.archive_path)).archive_path
        result.append(
            FilingProgress(
                accession=accession,
                references=tuple(refs),
                selected_archive_path=selected,
                reason=reason,
            )
        )
    return tuple(result)


def capture_index(
    layout: DataLayout, content: bytes, *, day: date, retrieved_at: datetime
) -> DiscoveryScan:
    manifest = capture_raw_bytes(
        layout,
        content,
        provider_namespace="sec.edgar",
        source_family="sec.daily_master_index",
        source_native_id=day.isoformat(),
        source_locator=index_url(day),
        retrieved_at=retrieved_at,
        observed_at=retrieved_at,
        adapter_version=VERSION,
        parser_version=VERSION,
        retention_class=RetentionClass.PUBLIC,
        license_name="sec-public-filings",
    )
    return DiscoveryScan(
        index_day=day,
        index_capture_id=manifest.capture_id,
        retrieved_at=manifest.retrieved_at,
        filings=_parse_index(content, day),
    )


def save_scan(scan: DiscoveryScan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(scan.model_dump(mode="json"), sort_keys=True, indent=2) + "\n").encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_scan(layout: DataLayout, path: Path) -> DiscoveryScan:
    scan = DiscoveryScan.model_validate_json(path.read_bytes())
    manifest = load_manifest(layout, scan.index_capture_id)
    raw = raw_object_path(layout, manifest.content_hash.value).read_bytes()
    if (
        hashlib.sha256(raw).hexdigest() != manifest.content_hash.value
        or manifest.source_family != "sec.daily_master_index"
        or manifest.source_locator != index_url(scan.index_day)
        or manifest.retrieved_at != scan.retrieved_at
    ):
        raise ValueError("scan_capture_mismatch")
    initial = _parse_index(raw, scan.index_day)
    if len(initial) != len(scan.filings) or any(
        a.accession != b.accession
        or a.references != b.references
        or a.selected_archive_path != b.selected_archive_path
        for a, b in zip(initial, scan.filings, strict=True)
    ):
        raise ValueError("scan_reference_mismatch")
    return scan


def process_scan(
    layout: DataLayout,
    scan: DiscoveryScan,
    *,
    checkpoint: Path,
    fetch: Callable[[str], bytes],
    limit: int,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    acceptance_timezone: str | None = None,
) -> DiscoveryScan:
    if not 1 <= limit <= 1000:
        raise ValueError("filing limit must be between 1 and 1000")
    adapter = SecForm4Adapter(layout)
    save_scan(scan, checkpoint)
    for index in range(scan.cursor, min(len(scan.filings), scan.cursor + limit)):
        filing = scan.filings[index]
        if filing.reason is not None:
            updated = filing.model_copy(update={"state": "rejected"})
        else:
            url = "https://www.sec.gov/Archives/" + filing.selected_archive_path
            try:
                content = fetch(url)
            except SecBoundedAccessError as exc:
                capture_raw_bytes(
                    layout,
                    exc.content,
                    provider_namespace="sec.edgar",
                    source_family="sec.watch_failed_response",
                    source_native_id=filing.accession,
                    source_locator=url,
                    retrieved_at=now(),
                    adapter_version=VERSION,
                    request_parameters={"failure": str(exc), "http_status": exc.status},
                    retention_class=RetentionClass.PUBLIC,
                )
                # Cursor stays on this filing; a later explicit invocation can retry it.
                raise
            try:
                bundle = adapter.ingest(
                    content,
                    accession=filing.accession,
                    source_locator=url,
                    retrieved_at=now(),
                    acceptance_timezone=acceptance_timezone,
                )
                if bundle.filing.form_type != "4":
                    updated = filing.model_copy(
                        update={"state": "rejected", "reason": "body_form_not_4"}
                    )
                else:
                    updated = filing.model_copy(
                        update={
                            "state": "ingested",
                            "event_ids": tuple(e.event_id for e in bundle.events),
                            "p_event_ids": tuple(
                                e.event_id for e in bundle.events if supported_purchase(e)
                            ),
                        }
                    )
            except SecParseError:
                updated = filing.model_copy(
                    update={"state": "rejected", "reason": "canonical_adapter_rejected"}
                )
        updated = updated.model_copy(update={"processed_at": normalize_utc(now())})
        # Revalidate model_copy values before serializing a resumable checkpoint.
        updated = FilingProgress.model_validate_json(updated.model_dump_json())
        filings = list(scan.filings)
        filings[index] = updated
        scan = DiscoveryScan(
            index_day=scan.index_day,
            index_capture_id=scan.index_capture_id,
            retrieved_at=scan.retrieved_at,
            filings=tuple(filings),
            cursor=index + 1,
        )
        save_scan(scan, checkpoint)
    return scan


def fetch_index(
    layout: DataLayout,
    client: SecFilingClient,
    *,
    day: date,
    retrieved_at: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> DiscoveryScan:
    url = index_url(day)
    try:
        content = fetch_watch_resource(client, url, max_bytes=2 * 1024**2)
    except SecBoundedAccessError as exc:
        capture_raw_bytes(
            layout,
            exc.content,
            provider_namespace="sec.edgar",
            source_family="sec.watch_failed_response",
            source_native_id=day.isoformat(),
            source_locator=url,
            retrieved_at=retrieved_at(),
            adapter_version=VERSION,
            request_parameters={"failure": str(exc), "http_status": exc.status},
            retention_class=RetentionClass.PUBLIC,
        )
        raise
    return capture_index(layout, content, day=day, retrieved_at=retrieved_at())
