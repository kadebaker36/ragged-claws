"""Canonical-only PIT purchase ledger and descriptive issuer clusters."""

import json
from collections import Counter
from datetime import datetime, timedelta
from decimal import localcontext
from importlib.metadata import version
from pathlib import Path
from typing import cast
from uuid import UUID

import exchange_calendars as xcals  # type: ignore[import-untyped]

from ragged_claws.market_data.listings import listing_bounds
from ragged_claws.models import (
    Entity,
    Event,
    EventEvidence,
    ExternalIdentifier,
    Listing,
    Provenance,
    Security,
    SecurityType,
    SourceObservation,
)
from ragged_claws.storage import CanonicalParquetStore, DataLayout
from ragged_claws.temporal import evaluate_eligibility, normalize_utc
from ragged_claws.watch.contracts import DEFAULT_CONTRACTS, PurchaseContract
from ragged_claws.watch.models import (
    ActorReference,
    DiscoveryCompleteness,
    PurchaseCandidate,
    PurchaseCluster,
    WatchReport,
)


class CanonicalWatch:
    def __init__(
        self,
        store: CanonicalParquetStore,
        *,
        contracts: tuple[PurchaseContract, ...] = DEFAULT_CONTRACTS,
    ) -> None:
        self.contracts = contracts
        self.events = store.load(Event)
        self.evidence = {e.event_evidence_id: e for e in store.load(EventEvidence)}
        self.observations = {o.source_observation_id: o for o in store.load(SourceObservation)}
        self.provenance = {p.provenance_id: p for p in store.load(Provenance)}
        self.identifiers = store.load(ExternalIdentifier)
        self.entities = {e.entity_id: e for e in store.load(Entity)}
        self.securities = {s.security_id: s for s in store.load(Security)}
        self.listings = {s.listing_id: s for s in store.load(Listing)}

    def provenance_visible(
        self, identity: UUID, as_of: datetime, visiting: frozenset[UUID] = frozenset()
    ) -> bool:
        if identity in visiting:
            raise ValueError("cyclic provenance")
        item = self.provenance.get(identity)
        return bool(
            item is not None
            and item.derived_at <= as_of
            and all(
                (obs := self.observations.get(oid)) is not None
                and max(obs.observed_at, obs.retrieved_at) <= as_of
                for oid in item.source_observation_ids
            )
            and all(
                self.provenance_visible(p, as_of, visiting | {identity})
                for p in item.parent_provenance_ids
            )
        )

    def candidate(self, event: Event, as_of: datetime) -> tuple[PurchaseCandidate | None, str]:
        contracts = [contract for contract in self.contracts if contract.supports(event)]
        if not contracts:
            return None, "outside_supported_p_population"
        if event.actionable_at is None or event.public_time is None:
            return None, "unknown_public_or_actionable_time"
        if event.actionable_at > as_of:
            return None, "not_yet_actionable"
        if not evaluate_eligibility(snapshot_at=as_of, known_from=event.public_time).eligible:
            return None, "public_time_not_eligible"
        if not self.provenance_visible(event.provenance_id, as_of):
            return None, "mapping_not_observed_as_of"
        links = []
        for eid in event.event_evidence_ids:
            link = self.evidence.get(eid)
            if link is None or link.event_id != event.event_id:
                raise ValueError("missing or contradictory event evidence")
            if self.provenance_visible(link.provenance_id, as_of):
                links.append(link)
        observations = {
            oid: self.observations[oid]
            for link in links
            for oid in link.source_observation_ids
            if oid in self.observations
            and max(self.observations[oid].observed_at, self.observations[oid].retrieved_at)
            <= as_of
        }
        supported = [
            (contract, [o for o in observations.values() if contract.supports_observation(o)])
            for contract in contracts
        ]
        supported = [
            (contract, observations) for contract, observations in supported if observations
        ]
        if len(supported) > 1:
            raise ValueError("ambiguous canonical purchase contract")
        primary = supported[0][1] if supported else []
        if not primary:
            return None, "no_visible_primary_form4_support"
        contract = supported[0][0]
        security = self.securities.get(event.security_id) if event.security_id else None
        listing = self.listings.get(event.listing_id) if event.listing_id else None
        if security and security.issuer_entity_id != event.issuer_entity_id:
            raise ValueError("event/security issuer contradiction")
        if listing and listing.security_id != event.security_id:
            raise ValueError("event/listing security contradiction")
        reasons = []
        if security is None:
            reasons.append("unresolved_security")
        elif not self.provenance_visible(security.provenance_id, as_of):
            reasons.append("security_evidence_not_observed_as_of")
        elif security.security_type is not SecurityType.COMMON_STOCK:
            return None, "resolved_non_common_stock"
        if listing is None:
            reasons.append("unresolved_listing")
        elif not self.provenance_visible(listing.provenance_id, as_of):
            reasons.append("listing_evidence_not_observed_as_of")
        else:
            try:
                lower, upper = listing_bounds(listing)
                day = event.actionable_at.date()
                if lower is None or day < lower or (upper is not None and day >= upper):
                    reasons.append("listing_validity_not_supported_at_actionability")
            except ValueError:
                reasons.append("listing_validity_not_supported_at_actionability")
        owners = self._link_actors(event, contract.actors(event), as_of)
        if not owners:
            return None, "missing_source_backed_reporting_actors"
        shares, price, exactness_reason = contract.financial_facts(event)
        unknown = None
        value = None
        if shares is None:
            unknown = "missing_exact_shares"
        elif price is None:
            unknown = "missing_exact_price"
        elif exactness_reason:
            unknown = exactness_reason
        elif not shares.is_finite() or shares < 0 or not price.is_finite() or price < 0:
            unknown = "unsupported_financial_value"
        else:
            with localcontext() as context:
                context.prec = max(28, len(shares.as_tuple().digits) + len(price.as_tuple().digits))
                value = shares * price
        issuer = self.entities.get(event.issuer_entity_id) if event.issuer_entity_id else None
        issuer_name = (
            issuer.display_name
            if issuer and self.provenance_visible(issuer.provenance_id, as_of)
            else None
        )
        security_ok = not any(r.startswith(("unresolved_security", "security_")) for r in reasons)
        listing_ok = not any(r.startswith(("unresolved_listing", "listing_")) for r in reasons)
        return PurchaseCandidate(
            event_id=event.event_id,
            issuer_entity_id=event.issuer_entity_id,
            issuer_name=issuer_name,
            security_id=event.security_id,
            listing_id=event.listing_id,
            actors=owners,
            occurrence_time=event.occurrence_time,
            public_time=event.public_time,
            actionable_at=event.actionable_at,
            first_observed_at=min(o.observed_at for o in primary),
            shares=shares,
            reported_price_per_share=price,
            exact_transaction_value=value,
            value_unknown_reason=unknown,
            status="qualifying_common_stock" if security_ok else "unresolved",
            identity_status="resolved_common_stock" if security_ok else "unresolved",
            listing_status="resolved" if listing_ok else "unresolved",
            unresolved_reasons=tuple(reasons),
            source_observation_ids=tuple(sorted(observations, key=str)),
            evidence_ids=tuple(sorted((e.event_evidence_id for e in links), key=str)),
            provenance_ids=tuple(
                sorted(
                    {
                        event.provenance_id,
                        *(e.provenance_id for e in links),
                        *([security.provenance_id] if security_ok and security else []),
                        *([listing.provenance_id] if listing_ok and listing else []),
                    },
                    key=str,
                )
            ),
            underlying_source_families=tuple(
                sorted(
                    {
                        o.lineage.underlying_source_family or o.lineage.source_family
                        for o in observations.values()
                    }
                )
            ),
            filing_references=tuple(sorted({o.source_native_id for o in primary})),
            venue=contract.venue,
            attribution=contract.attribution,
        ), "included"

    def _link_actors(
        self, event: Event, actors: tuple[ActorReference, ...], as_of: datetime
    ) -> tuple[ActorReference, ...]:
        result = []
        for actor in actors:
            ids = set()
            for party in event.actors:
                entity = self.entities.get(party.entity_id)
                if party.role != "reporting_owner" or entity is None:
                    continue
                if not self.provenance_visible(entity.provenance_id, as_of):
                    continue
                if any(
                    f"{c.identifier_type.value}:{c.value}" == actor.reference
                    for c in (*entity.external_identifiers, *self.identifiers)
                    if c.subject_id == entity.entity_id
                    and c.observed_at <= as_of
                    and self.provenance_visible(c.provenance_id, as_of)
                ):
                    ids.add(entity.entity_id)
            if len(ids) > 1:
                raise ValueError("conflicting canonical reporting actor identity")
            result.append(
                actor.model_copy(
                    update={
                        "entity_id": next(iter(ids), None),
                        "entity_resolution_status": "resolved" if ids else "source_reference_only",
                    }
                )
            )
        return tuple(result)


def build_report(
    layout: DataLayout,
    *,
    as_of: datetime,
    lookback_sessions: int = 5,
    discovery: tuple[DiscoveryCompleteness, ...] = (),
) -> WatchReport:
    as_of = normalize_utc(as_of)
    if not 1 <= lookback_sessions <= 252:
        raise ValueError("lookback_sessions must be between 1 and 252")
    cal = xcals.get_calendar(
        "XNYS", start=as_of.date() - timedelta(days=800), end=as_of.date() + timedelta(days=10)
    )
    session = cal.date_to_session(as_of.date(), direction="previous")
    if cal.session_open(session).to_pydatetime() > as_of:
        session = cal.previous_session(session)
    first = cal.session_offset(session, -(lookback_sessions - 1))
    window_start = cast(datetime, cal.session_open(first).to_pydatetime())
    watch = CanonicalWatch(CanonicalParquetStore(layout, read_only=True))
    candidates = []
    counts: Counter[str] = Counter()
    for event in watch.events:
        candidate, reason = watch.candidate(event, as_of)
        if candidate is not None and candidate.actionable_at < window_start:
            candidate, reason = None, "outside_recent_session_window"
        if candidate is not None:
            candidates.append(candidate)
        else:
            counts[reason] += 1
    candidates.sort(key=lambda c: (c.actionable_at, str(c.event_id)))
    clusters = []
    for issuer in sorted(
        {c.issuer_entity_id for c in candidates if c.issuer_entity_id is not None}, key=str
    ):
        rows = [
            c
            for c in candidates
            if c.issuer_entity_id == issuer and c.status == "qualifying_common_stock"
        ]
        if not rows:
            continue
        actors = tuple(sorted({a.reference for c in rows for a in c.actors}))
        filings = {f for c in rows for f in c.filing_references}
        clusters.append(
            PurchaseCluster(
                issuer_entity_id=issuer,
                event_ids=tuple(c.event_id for c in rows),
                purchase_event_count=len(rows),
                distinct_reporting_actor_count=len(actors),
                actor_references=actors,
                first_actionable_at=min(c.actionable_at for c in rows),
                latest_actionable_at=max(c.actionable_at for c in rows),
                filing_count=len(filings),
                multiple_filings=len(filings) > 1,
            )
        )
    return WatchReport(
        as_of=as_of,
        lookback_sessions=lookback_sessions,
        window_start=window_start,
        calendar_version=version("exchange-calendars"),
        candidates=tuple(candidates),
        clusters=tuple(clusters),
        excluded_counts=dict(sorted(counts.items())),
        discovery=discovery,
        discovery_status="captured_index_scope_only_market_coverage_unknown"
        if discovery
        else "not_supplied_market_coverage_unknown",
    )


def encoded(report: WatchReport) -> bytes:
    return (json.dumps(report.model_dump(mode="json"), sort_keys=True, indent=2) + "\n").encode()


def render_markdown(report: WatchReport) -> str:
    def cell(value: object) -> str:
        return str(value if value is not None else "unknown").replace("|", "\\|").replace("\n", " ")

    lines = [
        "# Forward insider purchase evidence",
        "",
        report.interpretation,
        "",
        f"As of: {report.as_of.isoformat()}; recent window: {report.lookback_sessions} "
        f"XNYS sessions from {report.window_start.isoformat()}.",
        "",
        f"Discovery: {report.discovery_status}. No complete-market statement.",
        "",
        "| Event / issuer | Reporting actors | Shares | Reported price / exact value "
        "(currency unknown) | Actionable UTC | Identity / Listing | Evidence |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in report.candidates:
        lines.append(
            "| "
            + " | ".join(
                map(
                    cell,
                    (
                        f"{c.event_id} / {c.issuer_name or c.issuer_entity_id}",
                        "; ".join(f"{a.name or 'unknown'} ({a.reference})" for a in c.actors),
                        c.shares,
                        f"{cell(c.reported_price_per_share)} / {cell(c.exact_transaction_value)}",
                        c.actionable_at.isoformat(),
                        f"{c.identity_status} / {c.listing_status}; "
                        f"{', '.join(c.unresolved_reasons)}",
                        ", ".join(map(str, c.evidence_ids)),
                    ),
                )
            )
            + " |"
        )
    if not report.candidates:
        lines.extend(["", "No visible candidates in this canonical state/window."])
    lines.extend(["", "## Source references", ""])
    for candidate in report.candidates:
        lines.append(
            f"- Event {candidate.event_id}: filings {', '.join(candidate.filing_references)}; "
            f"observations {', '.join(map(str, candidate.source_observation_ids))}; "
            f"provenance {', '.join(map(str, candidate.provenance_ids))}; "
            f"public {cell(candidate.public_time.timestamp or candidate.public_time.raw_value)}; "
            f"first observed {candidate.first_observed_at.isoformat()}; "
            f"value unknown reason {cell(candidate.value_unknown_reason)}."
        )
    lines.extend(["", "## Descriptive issuer clusters", ""])
    for cluster in report.clusters:
        lines.append(
            f"- {cluster.issuer_entity_id}: {cluster.purchase_event_count} Events, "
            f"{cluster.distinct_reporting_actor_count} reporting actors, "
            f"{cluster.filing_count} filings; "
            f"actionable {cluster.first_actionable_at.isoformat()} to "
            f"{cluster.latest_actionable_at.isoformat()}."
        )
    lines.extend(["", "## Discovery accounting", ""])
    for d in report.discovery:
        lines.append(
            f"- {d.index_day}: discovered {d.discovered_form4_count}, processed "
            f"{d.processed_filing_count}, remaining {d.remaining_unprocessed_count}, "
            f"rejected {d.rejected_count}, ingested {d.successfully_ingested_count}, "
            f"common-stock P Events {d.qualifying_p_event_count}, unresolved P Events "
            f"{d.unresolved_p_event_count}; cursor {d.cursor}; "
            f"index processing complete={d.index_processing_complete}."
        )
    lines.extend(
        [
            "",
            "Full observation/provenance/source references and unknown reasons: watch.json.",
            "",
            "Excluded/withheld: " + json.dumps(report.excluded_counts, sort_keys=True),
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: WatchReport, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, content in (
        ("watch.json", encoded(report)),
        ("watch.md", render_markdown(report).encode()),
    ):
        target = output / name
        if target.exists() and target.read_bytes() != content:
            raise ValueError("different watch output already exists; choose a fresh output")
        target.write_bytes(content)
