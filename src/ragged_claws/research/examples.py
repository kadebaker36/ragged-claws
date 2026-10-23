"""Bounded local preparation examples: recorded SEC coverage, or explicitly invented prices."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import exchange_calendars as xcals  # type: ignore[import-untyped]

from ragged_claws.ingestion.quiver import QuiverAdapter
from ragged_claws.ingestion.sec import SecForm4Adapter
from ragged_claws.market_data import DailyBar, DailyBarRequest, MarketDataBatch
from ragged_claws.models import (
    DerivationKind,
    Entity,
    EntityType,
    Event,
    EventAttribute,
    EventAttributeType,
    EventEvidence,
    EventPartyReference,
    FinancialValue,
    FinancialValueKind,
    Listing,
    ObservationRole,
    PriceAdjustment,
    Provenance,
    Relationship,
    RetentionClass,
    Security,
    SecurityType,
    SourceLineage,
    SourceObservation,
    SubjectReference,
    SubjectType,
    TemporalPrecision,
    TemporalValue,
)
from ragged_claws.outcomes import ForwardOutcomeEngine
from ragged_claws.research.models import (
    BuildConfig,
    Controls,
    EventControl,
    IdentityBinding,
    OriginInventory,
    Period,
    PriceInputs,
    PricePacket,
    Protocol,
)
from ragged_claws.research.snapshot import (
    ResearchError,
    digest,
    encoded,
    inventory_for,
    read_inputs,
    write_once,
)
from ragged_claws.resolution import day_value
from ragged_claws.storage import (
    CanonicalParquetStore,
    DataLayout,
    capture_raw_bytes,
    deterministic_source_observation_id,
)
from ragged_claws.temporal import (
    ActionableTimeResolver,
    AvailabilityPolicy,
    apply_availability_policy,
)


def ident(number: int) -> UUID:
    return UUID(int=number)


def timestamp(value: datetime) -> TemporalValue:
    return TemporalValue(
        raw_value=value.isoformat(),
        precision=TemporalPrecision.SECOND,
        timestamp=value,
        source_timezone="UTC",
    )


def finish_preparation(
    root: Path,
    config: BuildConfig,
    protocol: Protocol,
    controls: Controls,
    prices: PriceInputs,
    *,
    invented: bool,
) -> None:
    for name, value in (
        ("config", config),
        ("protocol", protocol),
        ("controls", controls),
        ("prices", prices),
    ):
        write_once(root / f"{name}.json", encoded(value))
    origin_path = root / "origins.json"
    existed = origin_path.exists()
    if not existed:
        write_once(origin_path, encoded(OriginInventory(records=())))
    inventory = inventory_for(
        read_inputs(root),
        "synthetic" if invented else "recorded_public",
        "Explicitly invented engineering fixture, not research evidence."
        if invented
        else (
            "Recorded public SEC submission; exact fixture SHA is pinned by prepare_sec. "
            "Canonical adapter normalization only; no invented identity/prices."
        ),
    )
    if existed:
        write_once(origin_path, encoded(inventory))
    else:
        origin_path.write_bytes(
            encoded(inventory)
        )  # prepared metadata, not immutable raw source state


def latest_completed(as_of: datetime) -> date:
    probe = as_of.astimezone(UTC).date()
    calendar = xcals.get_calendar(
        "XNYS", start=probe - timedelta(days=14), end=probe + timedelta(days=2)
    )
    session = calendar.date_to_session(probe, direction="previous")
    if cast(datetime, calendar.session_close(session).to_pydatetime()) > as_of:
        session = calendar.previous_session(session)
    return cast(date, session.date())


def prepare_sec(
    root: Path, source: Path, metadata: Path, protocol_path: Path, *, as_of: datetime
) -> None:
    content = source.read_bytes()
    expected = "5eb55738b2b6e3a2e76cb6ffcbfb6e415dbc5c7af763c9c6ced9e30e7171e732"
    if digest(content) != expected:
        raise ResearchError("recorded SEC example requires the exact reviewed public fixture")
    provenance = json.loads(metadata.read_bytes())
    if provenance["sha256"] != expected:
        raise ResearchError("fixture acquisition metadata/hash disagreement")
    protocol = Protocol.model_validate_json(protocol_path.read_bytes())
    SecForm4Adapter(DataLayout(root / "data")).ingest(
        content,
        accession=provenance["accession"],
        retrieved_at=datetime.fromisoformat(provenance["retrieved_at"]),
        source_locator=provenance["source_url"],
        acceptance_timezone="America/New_York",
    )
    config = BuildConfig(
        mode="diagnostic",
        hypothesis_id=protocol.hypothesis_id,
        protocol_version=protocol.version,
        period=Period(start=date(2024, 9, 1), end=date(2024, 9, 30)),
        as_of=as_of,
        coverage_through=latest_completed(as_of),
        features=protocol.features,
        horizons=protocol.horizons,
        feed="iex",
        adjustment=PriceAdjustment.ALL,
    )
    finish_preparation(root, config, protocol, Controls(), PriceInputs(), invented=False)


def prepare_synthetic(
    root: Path, protocol_path: Path, *, coverage: date = date(2024, 6, 28)
) -> None:
    """Generate a small invented all-status specimen; never an investment result."""
    base_protocol = Protocol.model_validate_json(protocol_path.read_bytes())
    policy = AvailabilityPolicy(
        policy_id="invented_zero_delay",
        policy_version="1.0.0",
        source_family="synthetic.primary",
        rationale="Invented source timestamps for engineering tests only.",
    )
    protocol = base_protocol.model_copy(
        update={
            "hypothesis_id": "invented-engineering-only",
            "source_families": ("synthetic.primary",),
            "availability_policies": (policy,),
        }
    )
    as_of = datetime.combine(coverage, datetime.min.time(), tzinfo=UTC) + timedelta(hours=23)
    config = BuildConfig(
        mode="synthetic",
        hypothesis_id=protocol.hypothesis_id,
        protocol_version=protocol.version,
        period=Period(start=date(2024, 1, 1), end=date(2024, 12, 31)),
        as_of=as_of,
        coverage_through=coverage,
        features=protocol.features,
        horizons=protocol.horizons,
        feed="iex",
        adjustment=PriceAdjustment.ALL,
        benchmark_security_id=ident(1099),
        benchmark_listing_id=ident(2099),
    )
    layout = DataLayout(root / "data")
    store = CanonicalParquetStore(layout)
    public = timestamp(datetime(2024, 1, 2, 16, tzinfo=UTC))
    source_observed_at = datetime(2024, 6, 28, 23, tzinfo=UTC)
    raw = encoded(
        {
            "notice": "INVENTED PRIMARY RECORDS; NO REAL DISCLOSURE",
            "event_ids": list(range(1, 12)),
            "reporting_lawmaker": 800,
            "transaction_owner": 801,
            "terminal_listing": 2004,
            "terminal_date": "2024-01-10",
        }
    )
    manifest = capture_raw_bytes(
        layout,
        raw,
        provider_namespace="synthetic.primary",
        source_family="synthetic.primary",
        source_native_id="INVENTED-DOCUMENT-1",
        retrieved_at=source_observed_at,
        adapter_version="invented/1",
        retention_class=RetentionClass.INTERNAL,
    )
    obs_id = deterministic_source_observation_id(
        "synthetic.primary", "INVENTED-DOCUMENT-1", manifest.content_hash.value
    )
    obs = SourceObservation(
        source_observation_id=obs_id,
        provider_namespace="synthetic.primary",
        source_native_id="INVENTED-DOCUMENT-1",
        lineage=SourceLineage(
            source_family="synthetic.primary", observation_role=ObservationRole.PRIMARY_SOURCE
        ),
        retrieved_at=source_observed_at,
        observed_at=source_observed_at,
        public_time=public,
        raw_content_hash=manifest.content_hash,
        adapter_version="invented/1",
        retention_class=RetentionClass.INTERNAL,
    )
    provenance = Provenance(
        provenance_id=ident(900),
        source_observation_ids=(obs_id,),
        derivation_kind=DerivationKind.SYNTHETIC_TEST,
        derived_at=source_observed_at,
        transform_version="invented-research-example/1",
    )
    store.persist(SourceObservation, (obs,))
    store.persist(Provenance, (provenance,))
    entities = tuple(
        Entity(
            entity_id=ident(i),
            entity_type=EntityType.ISSUER,
            display_name=f"Invented issuer {i}",
            provenance_id=ident(900),
        )
        for i in (101, 102, 103, 104, 105, 106, 107, 199)
    ) + tuple(
        Entity(
            entity_id=ident(i),
            entity_type=EntityType.PERSON,
            display_name=f"Invented separate party {i}",
            provenance_id=ident(900),
        )
        for i in (800, 801)
    )
    store.persist(Entity, entities)
    securities = tuple(
        Security(
            security_id=ident(1000 + index),
            issuer_entity_id=ident(100 + index),
            security_type=SecurityType.COMMON_STOCK,
            display_name=f"Invented Class A {index}",
            provenance_id=ident(900),
        )
        for index in (1, 2, 3, 4)
    ) + (
        Security(
            security_id=ident(1099),
            issuer_entity_id=ident(199),
            security_type=SecurityType.FUND_SHARE,
            display_name="Invented SPY stand-in; not real prices",
            provenance_id=ident(900),
        ),
    )
    listings = (
        Listing(
            listing_id=ident(2001),
            security_id=ident(1001),
            symbol="INVENTED_OLD",
            exchange_mic="XNYS",
            effective_from=day_value(date(2020, 1, 1)),
            effective_to=day_value(date(2024, 3, 1)),
            provenance_id=ident(900),
        ),
        Listing(
            listing_id=ident(2011),
            security_id=ident(1001),
            symbol="INVENTED_NEW",
            exchange_mic="XNYS",
            effective_from=day_value(date(2024, 3, 1)),
            provenance_id=ident(900),
        ),
        *(
            Listing(
                listing_id=ident(2000 + index),
                security_id=ident(1000 + index),
                symbol=f"INVENTED_{index}",
                exchange_mic="XNYS",
                effective_from=day_value(date(2020, 1, 1)),
                effective_to=day_value(date(2024, 1, 10)) if index == 4 else None,
                provenance_id=ident(900),
            )
            for index in (2, 3, 4)
        ),
        Listing(
            listing_id=ident(2099),
            security_id=ident(1099),
            symbol="SPY",
            exchange_mic="ARCX",
            effective_from=day_value(date(2020, 1, 1)),
            provenance_id=ident(900),
        ),
    )
    store.persist(Security, securities)
    store.persist(Listing, listings)
    engine = ForwardOutcomeEngine(
        methodology_id=ident(999),
        methodology_version="invented/1",
        adjustment=config.adjustment,
        benchmark_security=securities[-1],
        benchmark_listing=listings[-1],
        feed=config.feed,
    )
    entry = (
        ActionableTimeResolver().resolve(apply_availability_policy(public, policy)).actionable_at
    )
    assert entry is not None
    events: list[Event] = []
    bindings: list[IdentityBinding] = []
    event_observations = [obs]
    for index in range(1, 12):
        event_public = public
        action: datetime | None = entry
        if index in (9, 10):
            event_public = timestamp(
                datetime(2024, 6, 28, 21, tzinfo=UTC)
                if index == 9
                else datetime(2024, 5, 31, 21, tzinfo=UTC)
            )
            action = (
                ActionableTimeResolver()
                .resolve(apply_availability_policy(event_public, policy))
                .actionable_at
            )
        if index == 8:
            action = None
        extra_obs = obs.model_copy(
            update={
                "source_observation_id": ident(4000 + index),
                "source_native_id": f"INVENTED-ROW-{index}",
                "public_time": event_public,
            }
        )
        # Same invented document supports distinct source rows; IDs are explicit fixture choices.
        event_observations.append(extra_obs)
        evidence = EventEvidence(
            event_evidence_id=ident(3000 + index),
            event_id=ident(index),
            source_observation_ids=(extra_obs.source_observation_id,),
            provenance_id=ident(900),
        )
        event = Event(
            event_id=ident(index),
            event_type="lobbying_disclosure"
            if index == 11
            else "equity_sale"
            if index == 2
            else "equity_purchase",
            issuer_entity_id=ident(
                102
                if index == 3
                else 103
                if index == 4
                else 104
                if index == 5
                else 105
                if index == 6
                else 106
                if index == 7
                else 107
                if index == 8
                else 101
            ),
            actors=(
                EventPartyReference(entity_id=ident(800), role="reporting_lawmaker"),
                EventPartyReference(entity_id=ident(801), role="transaction_owner"),
            ),
            occurrence_time=day_value(date(2024, 1, 1)),
            public_time=event_public,
            actionable_at=action,
            financial_values=(
                FinancialValue(
                    name="transaction_shares",
                    kind=FinancialValueKind.QUANTITY,
                    value=Decimal(index * 10),
                    unit="shares",
                ),
            ),
            attributes=(
                EventAttribute(
                    name="unrequested_future_metric",
                    value_type=EventAttributeType.DECIMAL,
                    value=Decimal("999"),
                ),
            ),
            event_evidence_ids=(evidence.event_evidence_id,),
            provenance_id=ident(900),
        )
        events.append(event)
        store.persist(EventEvidence, (evidence,))
        asset = 2 if index == 3 else 3 if index == 4 else 4 if index == 5 else 1
        if index not in (6, 7, 8, 11):
            listing_id = ident(2011) if index in (9, 10) else ident(2000 + asset)
            bindings.append(
                IdentityBinding(
                    event_id=event.event_id,
                    security_id=ident(1000 + asset),
                    listing_id=listing_id,
                    listing_history_ids=(ident(2011),)
                    if asset == 1 and index not in (9, 10)
                    else (),
                    provenance_ids=(ident(900),),
                    review_reference="fixture://invented/explicit-identity",
                )
            )
    store.persist(SourceObservation, event_observations)
    store.persist(Event, events)
    relations = tuple(
        Relationship(
            relationship_id=ident(5000 + index),
            relationship_type="position",
            source=SubjectReference(subject_type=SubjectType.ENTITY, subject_id=ident(800)),
            target=SubjectReference(subject_type=SubjectType.ENTITY, subject_id=ident(101)),
            valid_from=day_value(date(2000, 1, 1)),
            known_from=day_value(date(2025, 1, 1)) if index == 1 else None,
            observed_at=source_observed_at,
            source_observation_ids=(obs_id,),
            provenance_id=ident(900),
        )
        for index in (1, 2)
    )
    store.persist(Relationship, relations)
    # Explicitly invented normalized copy corroborates event1 without creating a second event.
    vendor = obs.model_copy(
        update={
            "source_observation_id": ident(4999),
            "provider_namespace": "synthetic.vendor",
            "lineage": SourceLineage(
                source_family="synthetic.vendor",
                underlying_source_family="synthetic.primary",
                observation_role=ObservationRole.VENDOR_NORMALIZED,
            ),
        }
    )
    store.persist(SourceObservation, (vendor,))
    capture_raw_bytes(
        layout,
        raw,
        provider_namespace=vendor.provider_namespace,
        source_family=vendor.lineage.source_family,
        source_native_id=vendor.source_native_id,
        retrieved_at=source_observed_at,
        adapter_version=vendor.adapter_version,
        retention_class=vendor.retention_class,
    )
    store.persist(
        EventEvidence,
        (
            EventEvidence(
                event_evidence_id=ident(3999),
                event_id=ident(1),
                source_observation_ids=(vendor.source_observation_id,),
                provenance_id=ident(900),
            ),
        ),
    )
    prices_by_security: dict[UUID, dict[date, tuple[Decimal, Decimal]]] = {}
    for event in events:
        if (
            event.event_id not in {ident(i) for i in (1, 2, 3, 9, 10)}
            or event.actionable_at is None
        ):
            continue
        security_id = ident(1002) if event.event_id == ident(3) else ident(1001)
        opening_day = event.actionable_at.date()
        if opening_day <= coverage:
            prices_by_security.setdefault(security_id, {})[opening_day] = (
                Decimal(100),
                Decimal(100),
            )
            prices_by_security.setdefault(ident(1099), {})[opening_day] = (
                Decimal(500),
                Decimal(500),
            )
        for horizon, change in ((20, 10), (60, 20), (90, 30)):
            _, exit_day, _, _ = engine.session_bounds(event.actionable_at, horizon)
            if exit_day <= coverage:
                close = Decimal(100 - change if security_id == ident(1002) else 100 + change)
                prices_by_security.setdefault(security_id, {})[exit_day] = (close, close)
                prices_by_security.setdefault(ident(1099), {})[exit_day] = (
                    Decimal(500 + change // 2),
                    Decimal(500 + change // 2),
                )
    packets: list[PricePacket] = []
    for index, listing in enumerate(listings):
        request = DailyBarRequest.from_listing(
            listing,
            start=entry.date(),
            end=coverage,
            provider_asof=date(2024, 3, 1) if listing.listing_id == ident(2011) else entry.date(),
            adjustment=config.adjustment,
            feed=config.feed,
        )
        values = {
            d: v
            for d, v in prices_by_security.get(listing.security_id, {}).items()
            if request.start <= d <= request.end
        }
        raw_prices = encoded(
            {
                "notice": "INVENTED PRICE/IDENTITY SUPPORT; NOT ALPACA DATA",
                "values": {d.isoformat(): [str(x) for x in v] for d, v in values.items()},
            }
        )
        capture = capture_raw_bytes(
            layout,
            raw_prices,
            provider_namespace="synthetic.market_data",
            source_family="synthetic.prices",
            source_native_id=f"INVENTED-LISTING-{index}",
            retrieved_at=as_of,
            adapter_version="invented-price/1",
            retention_class=RetentionClass.INTERNAL,
        )
        observation = SourceObservation(
            source_observation_id=deterministic_source_observation_id(
                "synthetic.market_data", f"INVENTED-LISTING-{index}", capture.content_hash.value
            ),
            provider_namespace="synthetic.market_data",
            source_native_id=f"INVENTED-LISTING-{index}",
            lineage=SourceLineage(
                source_family="synthetic.prices", observation_role=ObservationRole.SYNTHETIC
            ),
            retrieved_at=as_of,
            observed_at=as_of,
            raw_content_hash=capture.content_hash,
            adapter_version="invented-price/1",
            retention_class=RetentionClass.INTERNAL,
        )
        store.persist(SourceObservation, (observation,))
        bars = tuple(
            DailyBar(
                security_id=listing.security_id,
                listing_id=listing.listing_id,
                session_date=d,
                open=v[0],
                close=v[1],
                high=max(v),
                low=min(v),
                provider_namespace=observation.provider_namespace,
                source_observation_id=observation.source_observation_id,
                adjustment=config.adjustment,
                feed=config.feed,
            )
            for d, v in sorted(values.items())
        )
        packets.append(
            PricePacket(
                packet_id=ident(7000 + index),
                request=request,
                batch=MarketDataBatch(
                    bars=bars, observations=(observation,), capture_ids=(capture.capture_id,)
                ),
            )
        )
    quiver_raw = encoded(
        [
            {
                "Representative": "Invented unresolved vendor filer",
                "Party": "Invented",
                "Transaction": "Purchase",
                "ReportDate": "2024-01-02",
            }
        ]
        * 2
    )
    QuiverAdapter(layout).ingest(
        quiver_raw,
        endpoint="congress_v1",
        source_locator="https://api.quiverquant.com/beta/live/congresstrading",
        retrieved_at=source_observed_at,
        synthetic=True,
    )
    controls = Controls(
        bindings=tuple(bindings),
        events=(
            EventControl(
                event_id=ident(7),
                exclusion_reason="invented_method_exclusion",
                review_reference="fixture://invented/exclusion",
            ),
            EventControl(
                event_id=ident(5),
                terminal_date=date(2024, 1, 10),
                terminal_observation_id=obs_id,
                review_reference="fixture://invented/explicit-terminal-record",
            ),
        ),
    )
    finish_preparation(
        root, config, protocol, controls, PriceInputs(packets=tuple(packets)), invented=True
    )
