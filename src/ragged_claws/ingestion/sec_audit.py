"""Fixed two-day, outcome-blind audit. No research/price engine or network on regeneration."""

import argparse
import hashlib
import json
import platform
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any

import exchange_calendars as xcals  # type: ignore[import-untyped]

from ragged_claws.ingestion.sec import ADAPTER_VERSION, PARSER_VERSION, SecForm4Adapter
from ragged_claws.ingestion.sec_parser import SecParseError
from ragged_claws.models import RetentionClass
from ragged_claws.storage import DataLayout, capture_raw_bytes

SCOPE_SHA256 = "eb21d709277f968f1dbe8932d6ea0f0325f8b2a8251765c84bda9c51dc741634"
DECLARATION_COMMIT = "744a6f22ed52dfa8f971e0e4cfb302d3a5cd45f4"
AUDIT_VERSION = "sec-population-timing/1.0.0"
INDEX_URLS = tuple(
    f"https://www.sec.gov/Archives/edgar/daily-index/2024/QTR3/master.202409{day}.idx"
    for day in (10, 11)
)
HEADER = "CIK|Company Name|Form Type|Date Filed|Filename"


class AuditError(ValueError):
    """Invalid evidence; never infer absent population or substitute a filing."""


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()


def load_scope(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    if digest(content) != SCOPE_SHA256:
        raise AuditError("scope differs from committed pre-acquisition declaration")
    result: dict[str, Any] = json.loads(content)
    return result


@dataclass(frozen=True)
class IndexRow:
    index_cik: str
    index_name: str
    form: str
    filed: str
    filename: str
    accession: str

    @property
    def url(self) -> str:
        return "https://www.sec.gov/Archives/" + self.filename


def filing_path(filename: str, accession: str | None = None) -> str:
    """Validate the literal documented index path, without URL normalization/guessing."""
    match = re.fullmatch(r"edgar/data/([0-9]{1,10})/([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt", filename)
    if match is None or (accession is not None and match[2] != accession):
        raise AuditError("unsafe or contradictory SEC index filing path")
    return match[2]


def parse_index(content: bytes, day: str) -> tuple[list[IndexRow], int]:
    """All forms retained; duplicates count, conflicting accession metadata fails closed."""
    if len(content) > 2 * 1024**2:
        raise AuditError("oversize index")
    try:
        lines = content.decode("utf-8-sig").splitlines()
    except UnicodeError as exc:
        raise AuditError("index encoding unsupported") from exc
    if lines.count(HEADER) != 1:
        raise AuditError("missing or ambiguous index columns")
    start = lines.index(HEADER) + 1
    if start >= len(lines) or not re.fullmatch(r"-+", lines[start]):
        raise AuditError("missing index separator")
    rows: list[IndexRow] = []
    by_accession: dict[str, IndexRow] = {}
    duplicates = 0
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 5:
            raise AuditError("malformed index row")
        cik, name, form, filed, filename = fields
        accession = filing_path(filename)
        if (
            not re.fullmatch(r"[0-9]{1,10}", cik)
            or not name.strip()
            or not form.strip()
            or filed != day
            or int(filename.split("/")[2]) != int(cik)
            or accession[11:13] != day[2:4]
        ):
            raise AuditError("index date/type/filer/path metadata contradiction")
        row = IndexRow(cik, name, form, filed, filename, accession)
        previous = by_accession.get(accession)
        if previous is not None:
            if previous != row:
                raise AuditError("conflicting accession/path metadata")
            duplicates += 1
        else:
            by_accession[accession] = row
        rows.append(row)
    return rows, duplicates


def select_four(rows: list[IndexRow]) -> list[IndexRow]:
    unique = {r.accession: r for r in rows if r.form == "4"}
    return [unique[a] for a in sorted(unique)[:4]]


def timestamp(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        raise AuditError("naive retrieval clock")
    return value.astimezone(UTC)


def potential_interval(entry: datetime | None) -> dict[str, Any]:
    if entry is None:
        return {"status": "unknown_public_timing", "entry": None, "exit": None}
    calendar = xcals.get_calendar(
        "XNYS", start=entry.date() - timedelta(days=7), end=entry.date() + timedelta(days=200)
    )
    session = calendar.date_to_session(entry.date())
    if calendar.session_open(session).to_pydatetime() != entry:
        raise AuditError("potential entry is not XNYS open")
    exit_at = calendar.session_close(calendar.session_offset(session, 60)).to_pydatetime()
    return {
        "status": "hypothetical_public_label_only",
        "entry": entry.isoformat(),
        "exit": exit_at.isoformat(),
    }


def overlap(intervals: list[dict[str, Any]]) -> dict[str, Any]:
    """Closed [open, close] support; starts precede ends at equal instants."""
    boundaries = []
    issuers: Counter[str] = Counter()
    active = peak = peak_issuers = repeat_peak = 0
    known = [i for i in intervals if i["entry"] is not None]
    for i in known:
        if timestamp(i["exit"]) < timestamp(i["entry"]):
            raise AuditError("reversed potential interval")
        boundaries.extend([(i["entry"], 0, i["issuer"]), (i["exit"], 1, i["issuer"])])
    for _, kind, issuer in sorted(boundaries):
        delta = 1 if kind == 0 else -1
        active += delta
        issuers[issuer] += delta
        peak = max(peak, active)
        peak_issuers = max(peak_issuers, sum(n > 0 for n in issuers.values()))
        repeat_peak = max(repeat_peak, sum(max(0, n - 1) for n in issuers.values()))
    return {
        "known_intervals": len(known),
        "unknown_intervals": len(intervals) - len(known),
        "peak_event_supports": peak,
        "peak_distinct_issuers": peak_issuers,
        "peak_repeat_issuer_excess_supports": repeat_peak,
        "convention": "closed endpoints; opens before closes at equal timestamps; entry=0, exit=60",
    }


def read_object(root: Path, record: dict[str, Any], limit: int) -> bytes:
    sha = record.get("sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise AuditError("invalid capture hash")
    path = root / "objects" / sha
    if path.is_symlink() or path.stat().st_size > limit:
        raise AuditError("unsafe/oversize captured object")
    content = path.read_bytes()
    if digest(content) != sha or len(content) != record["size_bytes"]:
        raise AuditError("capture size/hash mismatch")
    timestamp(record["retrieved_at"])
    return content


def validate_capture(records: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    """Validate attempt accounting independently of the acquisition implementation."""
    states = {
        "unattempted",
        "interrupted",
        "captured",
        "oversize",
        "denied",
        "non200",
        "challenge",
        "transport_error",
    }
    attempted = 0
    retained = 0
    failed = False
    previous: datetime | None = None
    # Actual order is both indexes, then selected bodies, exactly as serialized.
    for record in records:
        state = record["state"]
        if state not in states:
            raise AuditError("unknown acquisition state")
        if state == "unattempted":
            if any(k in record for k in ("sha256", "retrieved_at", "http_status", "attempted_at")):
                raise AuditError("unattempted resource has response metadata")
            continue
        if failed:
            raise AuditError("attempt after global stop")
        start = timestamp(record["attempted_at"])
        if previous is not None and (start - previous).total_seconds() < 1:
            raise AuditError("request spacing violates declared limit")
        previous = start
        attempted += 1
        if state != "interrupted":
            if timestamp(record["retrieved_at"]) < start:
                raise AuditError("retrieval precedes request")
            status = record["http_status"]
            if state == "captured" and (status != 200 or not record["complete_body"]):
                raise AuditError("captured resource lacks complete HTTP200")
            if state == "denied" and status not in (401, 403, 429):
                raise AuditError("invalid access-denial status")
            if state == "non200" and (status is None or status == 200):
                raise AuditError("invalid non200 status")
            retained += record["size_bytes"]
        failed = state != "captured" or "index_parse_error" in record
    if attempted != manifest["requests_attempted"] or retained != manifest["bytes_retained"]:
        raise AuditError("request/byte accounting mismatch")
    if attempted > 10 or sum(r["kind"] == "index" for r in records) != 2:
        raise AuditError("resource budget violated")
    if sum(r["kind"] == "submission" for r in records) > 8:
        raise AuditError("submission budget violated")
    if failed and manifest["stop_reason"] is None:
        raise AuditError("failed acquisition lacks stop reason")


def regenerate(scope: Path, captures: Path, output: Path) -> dict[str, Any]:
    """Fresh output only; evidence failures cannot masquerade as a complete acquisition."""
    declaration = load_scope(scope)
    if output.exists() or output.resolve().is_relative_to(captures.resolve()):
        raise AuditError("require fresh output outside captured input")
    manifest_bytes = (captures / "manifest.json").read_bytes()
    if len(manifest_bytes) > 2 * 1024**2:
        raise AuditError("oversize audit manifest")
    manifest: dict[str, Any] = json.loads(manifest_bytes)
    if manifest["scope_sha256"] != SCOPE_SHA256 or manifest["format_version"] != AUDIT_VERSION:
        raise AuditError("capture scope/format mismatch")
    records: list[dict[str, Any]] = manifest["resources"]
    validate_capture(records, manifest)
    if [r["url"] for r in records[:2]] != list(INDEX_URLS):
        raise AuditError("index resource order/scope mismatch")
    by_url = {r["url"]: r for r in records}
    if len(by_url) != len(records):
        raise AuditError("duplicate acquisition resource")
    output.mkdir(parents=True)
    layout = DataLayout(output / "data")
    adapter = SecForm4Adapter(layout)
    frames: list[dict[str, Any]] = []
    selected: list[IndexRow] = []
    seen: dict[str, IndexRow] = {}
    allowed = set(INDEX_URLS)
    for url, day in zip(INDEX_URLS, declaration["index_dates"], strict=True):
        if url not in by_url:
            raise AuditError("missing index acquisition status")
        record = by_url[url]
        if record["kind"] != "index":
            raise AuditError("index kind mismatch")
        frame: dict[str, Any] = {
            "url": url,
            "day": day,
            "capture_status": record["state"],
            "rows": None,
            "unique_form4": None,
            "references": [],
        }
        if record.get("sha256") is not None:
            content = read_object(captures, record, declaration["max_index_bytes"])
            capture_raw_bytes(
                layout,
                content,
                provider_namespace="sec.edgar",
                source_family="sec.daily_master_index",
                source_native_id=url,
                source_locator=url,
                retrieved_at=timestamp(record["retrieved_at"]),
                adapter_version=AUDIT_VERSION,
                parser_version=AUDIT_VERSION,
                retention_class=RetentionClass.PUBLIC,
                license_name="sec-public-filings",
            )
            if record["state"] == "captured":
                try:
                    rows, duplicate_count = parse_index(content, day)
                    for row in rows:
                        if row.accession in seen and seen[row.accession] != row:
                            raise AuditError("cross-index accession conflict")
                        seen[row.accession] = row
                    chosen = select_four(rows)
                    selected.extend(chosen)
                    allowed.update(r.url for r in chosen)
                    unique = {r.accession: r for r in rows}
                    frame.update(
                        rows=len(rows),
                        exact_duplicate_rows=duplicate_count,
                        forms=dict(sorted(Counter(r.form for r in rows).items())),
                        unique_form4=sum(r.form == "4" for r in unique.values()),
                        selected=len(chosen),
                        references=[
                            {
                                **asdict(r),
                                "selection": "selected"
                                if r in chosen
                                else "uncollected"
                                if r.form == "4"
                                else "other_form",
                            }
                            for r in sorted(unique.values(), key=lambda r: r.accession)
                        ],
                    )
                except AuditError as exc:
                    frame["parse_error"] = str(exc)
        frames.append(frame)
    if set(by_url) != allowed:
        raise AuditError("capture resources differ from deterministic declared selection")
    filings: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for row in selected:
        record = by_url[row.url]
        if (
            record["kind"] != "submission"
            or record["accession"] != row.accession
            or record["index_day"] != row.filed
            or record["index_filename"] != row.filename
        ):
            raise AuditError("selected submission metadata mismatch")
        result: dict[str, Any] = {
            **asdict(row),
            "acquisition_state": record["state"],
            "events": None,
            "parse_state": "not_available",
        }
        if record.get("sha256") is not None:
            content = read_object(captures, record, declaration["max_submission_bytes"])
            captured = adapter.capture(
                content,
                accession=row.accession,
                retrieved_at=timestamp(record["retrieved_at"]),
                source_locator=row.url,
            )
            result["raw_manifest_id"] = str(captured.capture_id)
            if record["state"] == "captured":
                try:
                    bundle = adapter.ingest(
                        content,
                        accession=row.accession,
                        source_locator=row.url,
                        retrieved_at=timestamp(record["retrieved_at"]),
                        acceptance_timezone="America/New_York",
                        form_type="4",
                        filed_as_of=date.fromisoformat(row.filed),
                    )
                    filing = bundle.filing
                    result.update(
                        parse_state="parsed",
                        events=len(bundle.events),
                        no_qualifying_events=not bundle.events,
                        body_issuer_cik=filing.issuer_cik,
                        issuer_id=str(bundle.events[0].issuer_entity_id)
                        if bundle.events
                        else str(bundle.entities[0].entity_id),
                        owners=[o.model_dump(mode="json") for o in filing.owners],
                        unresolved_owner_ciks=list(bundle.unresolved_owner_ciks),
                        rows=[r.model_dump(mode="json") for r in filing.rows],
                        filing_exclusion=filing.exclusion_reason,
                        acceptance_raw=filing.acceptance_raw,
                        public_time=filing.acceptance_time.model_dump(mode="json")
                        if filing.acceptance_time
                        else None,
                        timing_reason=filing.timing_reason,
                        policy=bundle.availability_policy.model_dump(mode="json"),
                        actionability=bundle.actionability.model_dump(mode="json")
                        if bundle.actionability
                        else None,
                    )
                    for event in bundle.events:
                        attrs = {a.name: a.value for a in event.attributes}
                        interval = potential_interval(event.actionable_at)
                        events.append(
                            {
                                "event_id": str(event.event_id),
                                "accession": row.accession,
                                "code": attrs["transaction_code"],
                                "index_day": row.filed,
                                "issuer": str(event.issuer_entity_id),
                                "transaction_time": event.occurrence_time.model_dump(mode="json")
                                if event.occurrence_time
                                else None,
                                "retrieved_at": record["retrieved_at"],
                                "first_ever_public_at": None,
                                "first_ever_collector_receipt": None,
                                "historical_decision_availability": "unknown",
                                "actual_decision_at": None,
                                "actual_policy_entry": None,
                                "security_status": "unresolved",
                                "listing_status": "unresolved",
                                "receipt_status": "current_capture_not_historical_eligibility",
                                "evidence_ids": [str(e) for e in event.event_evidence_ids],
                                **interval,
                            }
                        )
                except SecParseError as exc:
                    result.update(parse_state="malformed", parse_error=str(exc))
        filings.append(result)
    ids = [e["event_id"] for e in events]
    if len(set(ids)) != len(ids):
        raise AuditError("duplicate economic events")
    report: dict[str, Any] = {
        "format_version": AUDIT_VERSION,
        "scope_sha256": SCOPE_SHA256,
        "pre_acquisition_commit": DECLARATION_COMMIT,
        "capture_manifest_sha256": digest(manifest_bytes),
        "acquisition": manifest,
        "index_frames": frames,
        "selected_filings": filings,
        "events": events,
        "counts": {
            "selected_filings": len(selected),
            "submission_states": dict(
                sorted(Counter(f["acquisition_state"] for f in filings).items())
            ),
            "parse_states": dict(sorted(Counter(f["parse_state"] for f in filings).items())),
            "selected_no_events": sum(f.get("no_qualifying_events", False) for f in filings),
            "unique_ps_events": len(events),
            "reporting_owner_occurrences": sum(len(f.get("owners", [])) for f in filings),
            "unresolved_owner_occurrences": sum(
                len(f.get("unresolved_owner_ciks", [])) for f in filings
            ),
            "row_exclusion_reasons": dict(
                sorted(
                    Counter(
                        r["exclusion_reason"]
                        for f in filings
                        for r in f.get("rows", [])
                        if r["exclusion_reason"] is not None
                    ).items()
                )
            ),
            "events_by_code_day_issuer": dict(
                sorted(
                    Counter(f"{e['code']}|{e['index_day']}|{e['issuer']}" for e in events).items()
                )
            ),
            "events_unresolved_security": len(events),
            "events_unresolved_listing": len(events),
        },
        "potential_overlap": overlap(events),
        "complete_declared_acquisition": all(r["state"] == "captured" for r in records)
        and all("parse_error" not in f for f in frames)
        and all(f["parse_state"] == "parsed" for f in filings),
        "runtime": {
            "python": platform.python_version(),
            "exchange_calendars": version("exchange-calendars"),
            "adapter": ADAPTER_VERSION,
            "parser": PARSER_VERSION,
        },
        "code_sha256": {
            p.name: digest(p.read_bytes())
            for p in (
                Path(__file__),
                Path(__file__).with_name("sec_audit_capture.py"),
                Path(__file__).with_name("sec.py"),
                Path(__file__).with_name("sec_parser.py"),
            )
        },
        "lock_sha256": digest((Path(__file__).parents[3] / "uv.lock").read_bytes()),
        "limitations": [
            "2026 archival version, not historical completeness or first-public evidence",
            "Two dates and lexical four/day: biased diagnostic, not census/random sample",
            "Unselected references are uncollected, not zero-event filings",
            "No actual decisions/fills; hypothetical intervals are not positions/dollar capacity",
            "No prices/outcomes/inference/registration/paper start; validation not evaluated",
        ],
        "single_next_dependency": "Review acquisition/identity/timing gaps before more acquisition",
    }
    (output / "report.json").write_bytes(encoded(report))
    (output / "report.md").write_text(render_report(report), encoding="utf-8")
    inventory = {
        p.relative_to(output).as_posix(): digest(p.read_bytes())
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    (output / "output-hashes.json").write_bytes(encoded(inventory))
    return report


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "# Bounded SEC population/timing diagnostic",
        "",
        f"Complete declared acquisition: **{report['complete_declared_acquisition']}**.",
        "",
        "## Filing-frame denominators",
        "",
    ]
    for f in report["index_frames"]:
        lines.append(
            f"- {f['day']}: {f['capture_status']}; rows={f['rows']}; "
            f"unique Form4={f['unique_form4']}; selected={f.get('selected', 'unknown')}; "
            f"forms={f.get('forms', 'unknown')}; error={f.get('parse_error', 'none')}."
        )
    lines.extend(
        [
            "",
            "## Selected body subset (not frame event totals)",
            "",
            "```json",
            json.dumps(report["counts"], indent=2),
            "```",
            "",
            "## Hypothetical public-label supports only",
            "",
            "```json",
            json.dumps(report["potential_overlap"], indent=2),
            "```",
            "",
        ]
    )
    for f in report["selected_filings"]:
        lines.append(
            f"- {f['accession']}: {f['acquisition_state']}/{f['parse_state']}; "
            f"events={f['events']}; error={f.get('parse_error', 'none')}."
        )
    lines.extend(
        [
            "",
            *["- " + s for s in report["limitations"]],
            "",
            "Exact references, exclusions, clocks, raw hashes and lineage are in report.json.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = regenerate(args.scope, args.captures, args.output)
    print(
        json.dumps(
            {
                "complete_declared_acquisition": report["complete_declared_acquisition"],
                "counts": report["counts"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
