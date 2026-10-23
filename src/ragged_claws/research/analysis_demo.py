"""Small, fully invented engine-to-analysis examples. No real source or price requests."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from ragged_claws.market_data import DailyBar, DailyBarRequest, MarketDataBatch
from ragged_claws.models import (
    DerivationKind,
    Entity,
    EntityType,
    Event,
    EventEvidence,
    Listing,
    ObservationRole,
    PriceAdjustment,
    Provenance,
    RetentionClass,
    Security,
    SecurityType,
    SourceLineage,
    SourceObservation,
)
from ragged_claws.outcomes import ForwardOutcomeEngine
from ragged_claws.research.analysis_models import AnalysisPlan
from ragged_claws.research.examples import finish_preparation, ident, timestamp
from ragged_claws.research.models import (
    BuildConfig,
    Controls,
    IdentityBinding,
    Period,
    PriceInputs,
    PricePacket,
    Protocol,
)
from ragged_claws.research.snapshot import encoded, model_hash, write_once
from ragged_claws.resolution import day_value
from ragged_claws.storage import CanonicalParquetStore, DataLayout, capture_raw_bytes
from ragged_claws.temporal import (
    ActionableTimeResolver,
    AvailabilityPolicy,
    apply_availability_policy,
)

Case = Literal["positive", "negative", "one_arm_missing", "no_complete"]


def prepare_demo(root: Path, proposal: Path, case: Case) -> AnalysisPlan:
    """Four explicit invented share classes, two issuers, six distinct economic events.

    Issuer A has two purchases/two sales and B one purchase/one sale. Different
    class prices are explicit fixture facts, never guessed mappings of real securities.
    """
    policy = AvailabilityPolicy(
        policy_id="invented_immediate",
        policy_version="1.0.0",
        delay=timedelta(0),
        source_family="synthetic.primary",
        rationale="Invented engineering support only",
    )
    protocol = Protocol.model_validate_json(proposal.read_bytes()).model_copy(
        update={
            "hypothesis_id": "invented-analysis-only",
            "source_families": ("synthetic.primary",),
            "availability_policies": (policy,),
        }
    )
    layout = DataLayout(root / "data")
    store = CanonicalParquetStore(layout)
    as_of = datetime(2024, 6, 28, 23, tzinfo=UTC)
    public = timestamp(datetime(2024, 1, 2, 16, tzinfo=UTC))
    entry = (
        ActionableTimeResolver().resolve(apply_availability_policy(public, policy)).actionable_at
    )
    assert entry is not None
    config = BuildConfig(
        mode="synthetic",
        hypothesis_id=protocol.hypothesis_id,
        protocol_version=protocol.version,
        period=Period(start=date(2024, 1, 1), end=date(2024, 12, 31)),
        as_of=as_of,
        coverage_through=as_of.date(),
        features=protocol.features,
        feed="iex",
        adjustment=PriceAdjustment.ALL,
        benchmark_security_id=ident(1099),
        benchmark_listing_id=ident(2099),
    )
    # All declarations are captured before normalization; raw bytes are append-only.
    declaration = {
        "notice": "INVENTED engineering only",
        "case": case,
        "classes": {
            "1": [101, "purchase"],
            "2": [101, "sale"],
            "3": [102, "purchase"],
            "4": [102, "sale"],
        },
        "events_classes": [1, 2, 1, 2, 3, 4],
    }
    capture = capture_raw_bytes(
        layout,
        encoded(declaration),
        provider_namespace="synthetic.primary",
        source_family="synthetic.primary",
        source_native_id="INVENTED-ANALYSIS",
        retrieved_at=as_of,
        adapter_version="invented-analysis/1",
        retention_class=RetentionClass.INTERNAL,
    )
    observation = SourceObservation(
        source_observation_id=ident(500),
        provider_namespace="synthetic.primary",
        source_native_id="INVENTED-ANALYSIS",
        retrieved_at=as_of,
        observed_at=as_of,
        lineage=SourceLineage(
            source_family="synthetic.primary", observation_role=ObservationRole.PRIMARY_SOURCE
        ),
        public_time=public,
        raw_content_hash=capture.content_hash,
        adapter_version="invented-analysis/1",
        retention_class=RetentionClass.INTERNAL,
    )
    store.persist(SourceObservation, (observation,))
    store.persist(
        Provenance,
        (
            Provenance(
                provenance_id=ident(900),
                source_observation_ids=(ident(500),),
                derivation_kind=DerivationKind.SYNTHETIC_TEST,
                derived_at=as_of,
                transform_version="invented-analysis/1",
            ),
        ),
    )
    store.persist(
        Entity,
        tuple(
            Entity(
                entity_id=ident(i),
                entity_type=EntityType.ISSUER,
                display_name=f"Invented issuer {i}",
                provenance_id=ident(900),
            )
            for i in (101, 102, 199)
        ),
    )
    securities = tuple(
        Security(
            security_id=ident(1000 + i),
            issuer_entity_id=ident(101 if i < 3 else 102),
            security_type=SecurityType.COMMON_STOCK,
            display_name=f"Invented class {i}",
            provenance_id=ident(900),
        )
        for i in range(1, 5)
    ) + (
        Security(
            security_id=ident(1099),
            issuer_entity_id=ident(199),
            security_type=SecurityType.FUND_SHARE,
            display_name="Invented SPY stand-in",
            provenance_id=ident(900),
        ),
    )
    listings = tuple(
        Listing(
            listing_id=ident(s.security_id.int + 1000),
            security_id=s.security_id,
            symbol="SPY" if s.security_id == ident(1099) else f"INVENTED_{i}",
            exchange_mic="ARCX" if s.security_id == ident(1099) else "XNYS",
            effective_from=day_value(date(2020, 1, 1)),
            provenance_id=ident(900),
        )
        for i, s in enumerate(securities)
    )
    store.persist(Security, securities)
    store.persist(Listing, listings)
    bindings = []
    for number, asset in enumerate((1, 2, 1, 2, 3, 4), 1):
        event = Event(
            event_id=ident(number),
            event_type="equity_purchase" if asset % 2 else "equity_sale",
            issuer_entity_id=securities[asset - 1].issuer_entity_id,
            security_id=ident(1000 + asset),
            occurrence_time=day_value(date(2024, 1, 1)),
            public_time=public,
            actionable_at=entry,
            provenance_id=ident(900),
            event_evidence_ids=(ident(3000 + number),),
        )
        store.persist(Event, (event,))
        store.persist(
            EventEvidence,
            (
                EventEvidence(
                    event_evidence_id=ident(3000 + number),
                    event_id=event.event_id,
                    source_observation_ids=(ident(500),),
                    provenance_id=ident(900),
                ),
            ),
        )
        bindings.append(
            IdentityBinding(
                event_id=event.event_id,
                security_id=ident(1000 + asset),
                listing_id=ident(2000 + asset),
                provenance_ids=(ident(900),),
                review_reference="fixture://invented-explicit-share-class",
            )
        )
    engine = ForwardOutcomeEngine(
        methodology_id=ident(999),
        methodology_version="invented-analysis/1",
        adjustment=config.adjustment,
        benchmark_security=securities[-1],
        benchmark_listing=listings[-1],
        feed=config.feed,
    )
    packets = []
    for index, listing in enumerate(listings, 1):
        request = DailyBarRequest.from_listing(
            listing,
            start=entry.date(),
            end=as_of.date(),
            provider_asof=entry.date(),
            adjustment=config.adjustment,
            feed=config.feed,
        )
        benchmark = index == 5
        values = {entry.date(): Decimal(500 if benchmark else 100)}
        for horizon, stock_change, spy_change in ((20, 12, 5), (60, 25, 10), (90, 38, 15)):
            _, exit_day, _, _ = engine.session_bounds(entry, horizon)
            change = (
                spy_change
                if benchmark
                else (stock_change if (index % 2 == 1) == (case != "negative") else 0)
            )
            values[exit_day] = Decimal((500 if benchmark else 100) + change)
        if case == "no_complete" or (case == "one_arm_missing" and index in (2, 4)):
            values = {}
        raw_prices = encoded(
            {
                "notice": "INVENTED prices only",
                "case": case,
                "listing_id": str(listing.listing_id),
                "values": {d.isoformat(): str(v) for d, v in values.items()},
            }
        )
        price_capture = capture_raw_bytes(
            layout,
            raw_prices,
            provider_namespace="synthetic.market_data",
            source_family="synthetic.prices",
            source_native_id=f"INVENTED-PRICE-{index}",
            retrieved_at=as_of,
            adapter_version="invented-analysis-prices/1",
            retention_class=RetentionClass.INTERNAL,
        )
        obs = SourceObservation(
            source_observation_id=ident(600 + index),
            provider_namespace="synthetic.market_data",
            source_native_id=f"INVENTED-PRICE-{index}",
            retrieved_at=as_of,
            observed_at=as_of,
            lineage=SourceLineage(
                source_family="synthetic.prices", observation_role=ObservationRole.SYNTHETIC
            ),
            raw_content_hash=price_capture.content_hash,
            adapter_version="invented-analysis-prices/1",
            retention_class=RetentionClass.INTERNAL,
        )
        store.persist(SourceObservation, (obs,))
        packets.append(
            PricePacket(
                packet_id=ident(7000 + index),
                request=request,
                batch=MarketDataBatch(
                    observations=(obs,),
                    capture_ids=(price_capture.capture_id,),
                    bars=tuple(
                        DailyBar(
                            security_id=listing.security_id,
                            listing_id=listing.listing_id,
                            session_date=d,
                            open=v,
                            close=v,
                            high=v,
                            low=v,
                            provider_namespace=obs.provider_namespace,
                            source_observation_id=obs.source_observation_id,
                            adjustment=config.adjustment,
                            feed=config.feed,
                        )
                        for d, v in sorted(values.items())
                    ),
                ),
            )
        )
    finish_preparation(
        root,
        config,
        protocol,
        Controls(bindings=tuple(bindings)),
        PriceInputs(packets=tuple(packets)),
        invented=True,
    )
    plan = AnalysisPlan(
        purpose="invented_engineering",
        plan_id="invented-analysis-demo",
        version="v1",
        protocol_sha256=model_hash(protocol),
        hypothesis_id=protocol.hypothesis_id,
        protocol_version=protocol.version,
        period=config.period,
        features=config.features,
        source_families=protocol.source_families,
        provider="synthetic.market_data",
        feed=config.feed,
        adjustment=config.adjustment,
        minimum_complete_per_arm=2,
        minimum_issuers_per_arm=2,
        rationale="Engineering only: two issuers per arm; never the production 1000/200 gates.",
    )
    write_once(root.parent / "analysis-plan.json", encoded(plan))
    return plan
