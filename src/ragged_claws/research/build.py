"""Canonical-only assembly around the existing forward engine, with complete denominators."""

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid5

import exchange_calendars as xcals  # type: ignore[import-untyped]

from ragged_claws.ingestion.quiver_models import QuiverBundle
from ragged_claws.lineage import independent_primary_families
from ragged_claws.market_data.listings import listing_bounds
from ragged_claws.models import (
    DerivationKind,
    Entity,
    Event,
    EventEvidence,
    FeatureSnapshot,
    FeatureValue,
    FinancialValueKind,
    Listing,
    ObservationRole,
    Outcome,
    Provenance,
    Relationship,
    Security,
    SourceObservation,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.models.base import JsonScalar
from ragged_claws.outcomes import ForwardOutcomeEngine, OutcomeCalculationError
from ragged_claws.outcomes.engine import RETURN_CONTEXT
from ragged_claws.research.analysis_gate import (
    check_price_contract,
    journal_scope,
    require_analysis_approval,
)
from ragged_claws.research.analysis_models import AnalysisApproval, AnalysisPlan
from ragged_claws.research.models import (
    Distribution,
    HorizonReport,
    Protocol,
    ResearchReport,
    ResearchRow,
    Snapshot,
)
from ragged_claws.research.protocol import (
    check_configuration,
    finish_attempt,
    require_registration,
    start_attempt,
)
from ragged_claws.research.snapshot import (
    Inputs,
    ResearchError,
    digest,
    encoded,
    output_rights,
    private_root,
    read_inputs,
    verify_snapshot,
    write_once,
)
from ragged_claws.storage import CanonicalParquetStore, DataLayout, persist_envelope_records
from ragged_claws.temporal import (
    ActionableTimeError,
    ActionableTimeResolver,
    apply_availability_policy,
    evaluate_eligibility,
    validate_feature_snapshot,
)

STATUSES = (
    "complete",
    "right_censored",
    "unresolved_security",
    "missing_price",
    "terminal_delisted",
    "excluded",
    "rejected",
)
INTERPRETATION = (
    "Descriptive gross daily-open/close research assumptions, not realized fills. "
    "Returns are Decimal fractions, not percentage-formatted values. "
    "Costs/slippage and clustered inference are not evaluated here. "
    "Correlated issuer rows are not IID. "
    "Unknown context is not absence. No alpha, signal-success, "
    "untouched-evidence or funding-readiness claim. "
    "Officer/director cuts, USD size buckets, inferred political owners "
    "and sector comparisons are unavailable "
    "without supported canonical facts/knowledge/currency/classification."
)


def calendar_day(value: TemporalValue) -> date | None:
    if value.timestamp is not None:
        return value.timestamp.astimezone(UTC).date()
    partial = value.partial_date
    if value.precision is TemporalPrecision.DAY and partial is not None:
        assert partial.year is not None and partial.month is not None and partial.day is not None
        return date(partial.year, partial.month, partial.day)
    return None


def completed_coverage(snapshot: Snapshot) -> None:
    config = snapshot.config
    cal = xcals.get_calendar(
        "XNYS",
        start=config.coverage_through - timedelta(days=7),
        end=config.coverage_through + timedelta(days=7),
    )
    if not cal.is_session(config.coverage_through):
        raise ResearchError("coverage cutoff must be a regular session")
    close = cast(datetime, cal.session_close(config.coverage_through).to_pydatetime())
    if close > config.as_of:
        raise ResearchError("coverage session has not completed at the declared as-of time")


def features_for(
    inputs: Inputs, event: Event, snapshot_id: UUID
) -> tuple[tuple[FeatureValue, ...], dict[str, str]]:
    if event.actionable_at is None or event.public_time is None:
        return (), {name: "no_defensible_decision_time" for name in inputs.config.features}
    at = event.actionable_at
    # Derived feature availability at the existing decision instant; not invented source precision.
    known = TemporalValue(
        raw_value=at.isoformat(),
        precision=TemporalPrecision.SECOND,
        timestamp=at,
        source_timezone="UTC",
    )
    ids = {
        o
        for e in inputs.get(EventEvidence)
        if e.event_id == event.event_id
        for o in e.source_observation_ids
    }
    result: list[FeatureValue] = []
    missing: dict[str, str] = {}
    for name in inputs.config.features:
        value: JsonScalar
        sources = set(ids)
        if name == "event_type":
            value = event.event_type
        elif name == "reported_shares":
            candidates = [
                item
                for item in event.financial_values
                if item.name == "transaction_shares"
                and item.unit == "shares"
                and item.kind is FinancialValueKind.QUANTITY
            ]
            if len(candidates) != 1:
                missing[name] = "canonical_share_quantity_not_available"
                continue
            value = candidates[0].value
        else:
            subjects = {p.entity_id for p in (*event.actors, *event.economic_units)}
            if event.issuer_entity_id is not None:
                subjects.add(event.issuer_entity_id)
            matches = [
                r
                for r in inputs.get(Relationship)
                if any(
                    ref.subject_type.value == "entity" and ref.subject_id in subjects
                    for ref in (r.source, r.target)
                )
            ]
            eligible = [
                r
                for r in matches
                if evaluate_eligibility(
                    snapshot_at=at,
                    known_from=r.known_from,
                    known_to=r.known_to,
                    valid_at=at,
                    valid_from=r.valid_from,
                    valid_to=r.valid_to,
                    observed_at=r.observed_at,
                ).eligible
            ]
            if not eligible:
                missing[name] = "unknown_or_not_historically_eligible_not_zero"
                continue
            value = len(eligible)
            sources.update(o for r in eligible for o in r.source_observation_ids)
        result.append(
            FeatureValue(
                feature_value_id=uuid5(snapshot_id, f"feature:{event.event_id}:{name}"),
                name=name,
                value=value,
                known_from=known,
                source_observation_ids=tuple(sorted(sources, key=str)),
            )
        )
    feature_snapshot = FeatureSnapshot(
        feature_snapshot_id=uuid5(snapshot_id, f"features:{event.event_id}"),
        event_id=event.event_id,
        snapshot_at=at,
        feature_version="research-features/1.0.0",
        features=tuple(result),
        provenance_id=event.provenance_id,
    )
    validate_feature_snapshot(feature_snapshot)
    return feature_snapshot.features, missing


def assemble(
    inputs: Inputs, snapshot: Snapshot
) -> tuple[tuple[ResearchRow, ...], tuple[Provenance, ...]]:
    config, protocol = inputs.config, inputs.protocol
    observed = {o.source_observation_id: o for o in inputs.get(SourceObservation)}
    securities = {s.security_id: s for s in inputs.get(Security)}
    listings = {item.listing_id: item for item in inputs.get(Listing)}
    entities = {item.entity_id: item for item in inputs.get(Entity)}
    controls = {c.event_id: c for c in inputs.controls.events}
    bindings = {b.event_id: b for b in inputs.controls.bindings}
    engine = None
    benchmark_prov: set[UUID] = set()
    if config.benchmark_security_id is not None and config.benchmark_listing_id is not None:
        benchmark_security = securities.get(config.benchmark_security_id)
        benchmark_listing = listings.get(config.benchmark_listing_id)
        if (
            benchmark_security is None
            or benchmark_listing is None
            or benchmark_listing.symbol != "SPY"
            or benchmark_security.security_type.value != "fund_share"
        ):
            raise ResearchError(
                "SPY benchmark requires explicit source-backed fund-share/listing identity"
            )
        engine = ForwardOutcomeEngine(
            methodology_id=uuid5(snapshot.snapshot_id, "outcome-methodology"),
            methodology_version="research-build/1.0.0",
            adjustment=config.adjustment,
            benchmark_security=benchmark_security,
            benchmark_listing=benchmark_listing,
            feed=config.feed,
        )
        benchmark_prov.update((benchmark_security.provenance_id, benchmark_listing.provenance_id))
        if benchmark_security.issuer_entity_id in entities:
            benchmark_prov.add(entities[benchmark_security.issuer_entity_id].provenance_id)
    all_bars = tuple(bar for packet in inputs.prices.packets for bar in packet.batch.bars)
    rows: list[ResearchRow] = []
    provenance_rows: list[Provenance] = []
    for event in sorted(inputs.get(Event), key=lambda e: str(e.event_id)):
        evidence = tuple(e for e in inputs.get(EventEvidence) if e.event_id == event.event_id)
        source_ids = {o for item in evidence for o in item.source_observation_ids}
        families = independent_primary_families(
            event.event_id, evidence, inputs.get(SourceObservation)
        )
        anchor = [
            observed[o]
            for o in source_ids
            if observed[o].lineage.observation_role is ObservationRole.PRIMARY_SOURCE
            and observed[o].lineage.source_family in protocol.source_families
        ]
        selection: Literal["selected", "excluded", "unknown"] = "selected"
        reason = None
        if event.event_type not in protocol.event_types or not anchor:
            selection, reason = "excluded", "outside_declared_event_population"
        public_date = calendar_day(event.public_time) if event.public_time else None
        if selection == "selected":
            if public_date is None:
                selection, reason = "unknown", "sample_period_unknown"
            elif not config.period.start <= public_date <= config.period.end:
                selection, reason = "excluded", "outside_declared_sample_period"
        timing_reason = None
        if event.actionable_at is None:
            timing_reason = "missing_actionable_time"
        elif event.public_time is None:
            timing_reason = "missing_public_time"
        else:
            policies = [
                p
                for p in protocol.availability_policies
                for o in anchor
                if p.source_family == o.lineage.source_family and o.public_time == event.public_time
            ]
            if not policies:
                timing_reason = "missing_matching_source_public_policy"
            else:
                try:
                    if any(
                        ActionableTimeResolver()
                        .resolve(apply_availability_policy(event.public_time, p))
                        .actionable_at
                        != event.actionable_at
                        for p in policies
                    ):
                        timing_reason = "actionable_time_disagrees_with_declared_policy"
                    elif not evaluate_eligibility(
                        snapshot_at=config.as_of, known_from=event.public_time
                    ).eligible:
                        timing_reason = "event_public_time_after_analysis_cutoff"
                except (ValueError, ActionableTimeError):
                    timing_reason = "unsupported_public_precision_or_calendar_for_policy"
        feature_values, unavailable = (
            features_for(inputs, event, snapshot.snapshot_id)
            if timing_reason is None
            else ((), {str(n): timing_reason for n in config.features})
        )
        binding = bindings.get(event.event_id)
        security_id = binding.security_id if binding else event.security_id
        listing_id = binding.listing_id if binding else event.listing_id
        security = securities.get(security_id) if security_id else None
        listing = listings.get(listing_id) if listing_id else None
        history = tuple(listings[item] for item in binding.listing_history_ids) if binding else ()
        identity_error = None
        if (security is None) != (listing is None):
            identity_error = "partial_security_listing_resolution"
        elif (
            security is not None
            and listing is not None
            and (
                listing.security_id != security.security_id
                or (
                    event.issuer_entity_id is not None
                    and event.issuer_entity_id != security.issuer_entity_id
                )
                or (event.security_id is not None and event.security_id != security.security_id)
                or (event.listing_id is not None and event.listing_id != listing.listing_id)
                or any(
                    item.security_id != security.security_id
                    or item.exchange_mic != listing.exchange_mic
                    for item in history
                )
            )
        ):
            identity_error = "contradictory_source_backed_identity_binding"
        if listing is not None and event.actionable_at is not None and identity_error is None:
            try:
                start, end = listing_bounds(listing)
                entry_day = event.actionable_at.astimezone(UTC).date()
                if (start is not None and entry_day < start) or (
                    end is not None and entry_day >= end
                ):
                    identity_error = "entry_outside_source_backed_listing_interval"
            except ValueError:
                identity_error = "unsupported_source_backed_listing_interval"
        identity_prov = set(binding.provenance_ids if binding else ())
        identity_prov.update(benchmark_prov)
        identity_prov.update(
            item.provenance_id for item in (security, listing, *history) if item is not None
        )
        if event.issuer_entity_id in entities:
            identity_prov.add(entities[event.issuer_entity_id].provenance_id)
        for horizon in sorted(config.horizons):
            status: Literal[
                "complete",
                "right_censored",
                "unresolved_security",
                "missing_price",
                "terminal_delisted",
                "excluded",
                "rejected",
            ] = "rejected"
            row_reason = reason or timing_reason
            outcome = None
            control = controls.get(event.event_id)
            row_id = uuid5(snapshot.snapshot_id, f"row:{event.event_id}:{horizon}")
            derived_id = uuid5(snapshot.snapshot_id, f"provenance:{event.event_id}:{horizon}")
            if identity_error is not None:
                status, row_reason = "rejected", identity_error
            elif selection == "excluded":
                status = "excluded"
            elif timing_reason is not None or selection == "unknown":
                status = "rejected"
            elif control is not None and control.exclusion_reason:
                status, row_reason = "excluded", control.exclusion_reason
            elif security is None and listing is None:
                status, row_reason = (
                    "unresolved_security",
                    "no_source_backed_security_listing_binding",
                )
            elif config.mode == "diagnostic":
                status, row_reason = "rejected", "diagnostic_mode_does_not_evaluate_returns"
            elif engine is None:
                status, row_reason = "rejected", "spy_identity_unresolved"
            else:
                try:
                    assert event.actionable_at is not None
                    entry, exit_day, _, _ = engine.session_bounds(event.actionable_at, horizon)
                    if entry > config.coverage_through:
                        status, row_reason = (
                            "right_censored",
                            "entry_session_not_completed_no_outcome_fabricated",
                        )
                    else:
                        terminal = (
                            control is not None
                            and control.terminal_date is not None
                            and control.terminal_date <= min(exit_day, config.coverage_through)
                        )
                        outcome = engine.calculate(
                            event=event,
                            horizon_sessions=horizon,
                            security=security,
                            listing=listing,
                            listing_history=history,
                            security_bars=tuple(
                                b
                                for b in all_bars
                                if b.security_id == security_id
                                and b.session_date in (entry, exit_day)
                                and b.listing_id
                                in {
                                    item.listing_id
                                    for item in (listing, *history)
                                    if item is not None
                                }
                            ),
                            benchmark_bars=tuple(
                                b
                                for b in all_bars
                                if b.security_id == config.benchmark_security_id
                                and b.session_date in (entry, exit_day)
                            ),
                            coverage_through=config.coverage_through,
                            provenance_id=derived_id,
                            terminal_delisted=terminal,
                        )
                        status = outcome.status.value
                        row_reason = outcome.exclusion_reason or (
                            None if status == "complete" else status
                        )
                except (OutcomeCalculationError, ValueError):
                    status, row_reason = (
                        "rejected",
                        "outcome_engine_identity_price_or_calendar_rejection",
                    )
            sources = set(source_ids)
            sources.update(o for feature in feature_values for o in feature.source_observation_ids)
            if outcome is not None:
                sources.update(outcome.methodology.price_source_observation_ids)
            if control is not None and control.terminal_observation_id is not None:
                sources.add(control.terminal_observation_id)
            for provenance in inputs.get(Provenance):
                if provenance.provenance_id in identity_prov:
                    sources.update(provenance.source_observation_ids)
            provenance_rows.append(
                Provenance(
                    provenance_id=derived_id,
                    source_observation_ids=tuple(sorted(sources, key=str)),
                    parent_provenance_ids=tuple(
                        sorted({event.provenance_id, *identity_prov}, key=str)
                    ),
                    derivation_kind=DerivationKind.NORMALIZATION,
                    derived_at=max(
                        (config.as_of, *(observed[item].observed_at for item in sources))
                    ),
                    transform_version="research-build/1.0.0",
                )
            )
            rows.append(
                ResearchRow(
                    row_id=row_id,
                    snapshot_id=snapshot.snapshot_id,
                    event=event,
                    horizon_sessions=horizon,
                    selection=selection,
                    status=status,
                    reason=row_reason,
                    timing_eligible=timing_reason is None,
                    source_observation_ids=tuple(sorted(sources, key=str)),
                    event_evidence_ids=tuple(
                        sorted((e.event_evidence_id for e in evidence), key=str)
                    ),
                    primary_families=families,
                    normalized_vendor_observations=sum(
                        observed[o].lineage.observation_role is ObservationRole.VENDOR_NORMALIZED
                        for o in source_ids
                    ),
                    features=feature_values,
                    unavailable_features=unavailable,
                    listing_history_ids=tuple(item.listing_id for item in history),
                    identity_provenance_ids=tuple(sorted(identity_prov, key=str)),
                    outcome=outcome,
                )
            )
    return tuple(rows), tuple(provenance_rows)


def distribution(values: list[Decimal]) -> Distribution:
    if not values:
        return Distribution(n=0)
    ordered = sorted(values)
    n = len(ordered)
    with localcontext(RETURN_CONTEXT):
        median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
        return Distribution(
            n=n,
            mean=sum(ordered, Decimal(0)) / n,
            median=median,
            minimum=ordered[0],
            maximum=ordered[-1],
            p10_nearest_rank=ordered[(n + 9) // 10 - 1],
            p90_nearest_rank=ordered[(9 * n + 9) // 10 - 1],
            positive_fraction=Decimal(sum(v > 0 for v in ordered)) / n,
        )


def ratio(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    with localcontext(RETURN_CONTEXT):
        return Decimal(numerator) / denominator


def report_for(
    inputs: Inputs, snapshot: Snapshot, rows: tuple[ResearchRow, ...], registered: bool
) -> ResearchReport:
    summaries: list[HorizonReport] = []
    for horizon in sorted(inputs.config.horizons):
        selected = [r for r in rows if r.horizon_sessions == horizon]
        complete = [r for r in selected if r.outcome is not None and r.status == "complete"]

        def values(kind: str, subset: list[ResearchRow] = complete) -> list[Decimal]:
            return [
                value
                for r in subset
                if r.outcome is not None and isinstance(value := getattr(r.outcome, kind), Decimal)
            ]

        counts: Counter[str] = Counter(r.status for r in selected)
        source_groups = {"+".join(r.primary_families) or "unanchored" for r in selected}
        summaries.append(
            HorizonReport(
                horizon_sessions=horizon,
                denominator=len(selected),
                qualifying_denominator=sum(r.selection == "selected" for r in selected),
                actionable_qualifying_denominator=sum(
                    r.selection == "selected" and r.timing_eligible for r in selected
                ),
                complete_coverage_fraction=ratio(
                    len(complete),
                    sum(r.selection == "selected" and r.timing_eligible for r in selected),
                ),
                counts={status: counts[status] for status in STATUSES},
                reasons=dict(sorted(Counter(r.reason for r in selected if r.reason).items())),
                by_source={
                    family: {
                        "denominator": sum(
                            ("+".join(r.primary_families) or "unanchored") == family
                            for r in selected
                        ),
                        **{
                            status: sum(
                                r.status == status
                                and ("+".join(r.primary_families) or "unanchored") == family
                                for r in selected
                            )
                            for status in STATUSES
                        },
                    }
                    for family in sorted(source_groups)
                },
                security_return=distribution(values("security_return")),
                spy_return=distribution(values("benchmark_return")),
                spy_excess=distribution(values("excess_return")),
                by_event_type_excess={
                    kind: distribution(
                        values("excess_return", [r for r in complete if r.event.event_type == kind])
                    )
                    for kind in sorted({r.event.event_type for r in selected})
                },
            )
        )
    first = [r for r in rows if r.horizon_sessions == min(inputs.config.horizons)]
    issuers = Counter(
        str(r.event.issuer_entity_id) for r in first if r.event.issuer_entity_id is not None
    )
    vendors = [
        item
        for item in inputs.records.get("quiver_snapshot_mapping", ())
        if isinstance(item, QuiverBundle)
    ]
    fingerprints = Counter(
        (v.endpoint, v.rows[m.row_index].fact_hash)
        for v in vendors
        for m in v.mappings
        if m.event_id is None
    )
    return ResearchReport(
        snapshot_id=snapshot.snapshot_id,
        mode=inputs.config.mode,
        protocol_status="registered" if registered else "proposal_unregistered",
        input_events=len(first),
        qualifying_events=sum(r.selection == "selected" for r in first),
        unknown_selection_events=sum(r.selection == "unknown" for r in first),
        distinct_known_issuers=len(issuers),
        qualifying_distinct_issuers=len(
            {
                r.event.issuer_entity_id
                for r in first
                if r.selection == "selected" and r.event.issuer_entity_id is not None
            }
        ),
        unknown_issuer_events=sum(r.event.issuer_entity_id is None for r in first),
        issuer_event_counts=dict(sorted(issuers.items())),
        primary_snapshot_event_counts=dict(
            sorted(
                Counter(
                    str(identity)
                    for r in first
                    for identity in {
                        source
                        for evidence in inputs.get(EventEvidence)
                        if evidence.event_id == r.event.event_id
                        for source in evidence.source_observation_ids
                    }
                    if any(
                        o.source_observation_id == identity
                        and o.lineage.observation_role is ObservationRole.PRIMARY_SOURCE
                        for o in inputs.get(SourceObservation)
                    )
                ).items()
            )
        ),
        distinct_explicit_economic_units=len(
            {p.entity_id for r in first for p in r.event.economic_units}
        ),
        unresolved_vendor_source_rows=sum(m.event_id is None for v in vendors for m in v.mappings),
        vendor_snapshot_versions=len(vendors),
        possible_repeated_vendor_rows=sum(
            count - 1 for count in fingerprints.values() if count > 1
        ),
        horizons=tuple(summaries),
        interpretation=(
            "INVENTED engineering prices/identities; not a real investment result. "
            if inputs.config.mode == "synthetic"
            else ""
        )
        + INTERPRETATION,
    )


def markdown(report: ResearchReport) -> bytes:
    lines = [
        f"# Research snapshot {report.snapshot_id}",
        "",
        f"Mode: {report.mode}; protocol: {report.protocol_status}.",
        "",
        report.interpretation,
        "",
        (
            f"Input canonical events: {report.input_events}; "
            f"qualifying: {report.qualifying_events}; "
            f"known issuers: {report.distinct_known_issuers}."
        ),
        "",
        (
            "| Horizon (sessions) | All-event denominator | Complete | Censored | "
            "Unresolved | Missing | "
            "Terminal | Excluded | Rejected | Mean SPY excess | Median SPY excess |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in report.horizons:
        values = [
            str(item.horizon_sessions),
            str(item.denominator),
            *(str(item.counts[k]) for k in STATUSES),
            str(item.spy_excess.mean) if item.spy_excess.mean is not None else "unavailable",
            str(item.spy_excess.median) if item.spy_excess.median is not None else "unavailable",
        ]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend(
        (
            "",
            (
                "Exact Decimal absolute/SPY/excess distributions, reasons, source denominators "
                "and issuer dependence are in report.json."
            ),
            (
                f"Unresolved vendor source rows/versions: {report.unresolved_vendor_source_rows}/"
                f"{report.vendor_snapshot_versions}; these are not known unique events."
            ),
            "",
        )
    )
    return "\n".join(lines).encode()


def build(
    root: Path,
    output: Path,
    registry: Path,
    *,
    analysis_plan: AnalysisPlan | None = None,
    analysis_approval: AnalysisApproval | None = None,
) -> ResearchReport:
    snapshot = Snapshot.model_validate_json((root / "snapshot.json").read_bytes())
    if snapshot.config.output_rights == "private_only":
        private_root(registry)
    frozen_root = root.resolve()
    for destination in ((output / str(snapshot.snapshot_id)).resolve(), registry.resolve()):
        if destination.is_relative_to(frozen_root) or frozen_root.is_relative_to(destination):
            raise ResearchError("output/registry must not overlap frozen inputs")
    attempt = start_attempt(registry, snapshot)
    inspected = False
    try:
        if snapshot.config.mode == "validation":
            protocol = Protocol.model_validate_json((root / "protocol.json").read_bytes())
            require_registration(snapshot, protocol, root, registry)
            journal_scope(attempt, analysis_plan, None)
            require_analysis_approval(
                snapshot, protocol, root, registry, analysis_plan, analysis_approval, attempt
            )
        # Verification/parsing can expose prices even when a later gate fails.
        # Both real phases must retain that potential inspection; authorization
        # denials above remain uninspected because they precede this boundary.
        inspected = snapshot.config.mode in ("discovery", "validation")
        snapshot = verify_snapshot(root)
        inputs = read_inputs(root)
        if analysis_plan is not None:
            check_price_contract(inputs, analysis_plan)
        output_rights(inputs.config, inputs.get(SourceObservation), output)
        output_rights(inputs.config, inputs.get(SourceObservation), registry)
        check_configuration(inputs.protocol, inputs.config)
        completed_coverage(snapshot)
        registered = False
        if inputs.config.mode == "validation":
            registered = True
        rows, provenance = assemble(inputs, snapshot)
        report = report_for(inputs, snapshot, rows, registered)
        target = output / str(snapshot.snapshot_id)
        target.mkdir(parents=True, exist_ok=True)
        persist_envelope_records(
            target / "research_rows.parquet",
            model_type=ResearchRow,
            id_field="row_id",
            records=rows,
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
        store = CanonicalParquetStore(DataLayout(target))
        store.persist(Outcome, tuple(r.outcome for r in rows if r.outcome is not None))
        store.persist(Provenance, provenance)
        write_once(target / "report.json", encoded(report))
        write_once(target / "report.md", markdown(report))
        write_once(target / "snapshot.json", encoded(snapshot))
        paths = sorted(p for p in target.rglob("*") if p.is_file() and p.name != "result.json")
        write_once(
            target / "result.json",
            encoded(
                {
                    "snapshot_id": str(snapshot.snapshot_id),
                    "files": {
                        p.relative_to(target).as_posix(): digest(p.read_bytes()) for p in paths
                    },
                }
            ),
        )
        inspection_dates = [
            date.fromisoformat(value.astimezone(UTC).date().isoformat())
            for row in rows
            if row.outcome is not None
            for value in (row.outcome.entry_at, row.outcome.exit_at)
            if value is not None
        ]
        inspection_period = type(inputs.config.period)(
            start=min((inputs.config.period.start, *inspection_dates)),
            end=max((inputs.config.period.end, *inspection_dates)),
        )
        finish_attempt(
            attempt, inspected=inspected, success=True, inspection_period=inspection_period
        )
        return report
    except Exception:
        potential = type(snapshot.config.period)(
            start=snapshot.config.period.start,
            end=max(snapshot.config.period.end, snapshot.config.coverage_through),
        )
        finish_attempt(
            attempt,
            inspected=inspected,
            success=False,
            inspection_period=potential if inspected else None,
        )
        raise
