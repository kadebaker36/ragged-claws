"""Fixture-first SEC ownership capture, mapping and Parquet publication."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid5

from ragged_claws.ingestion.observations import accept_source_observation
from ragged_claws.ingestion.sec_models import SecBundle, SecFiling
from ragged_claws.ingestion.sec_parser import SecParseError, parse_filing
from ragged_claws.models import (
    DerivationKind,
    Entity,
    EntityType,
    Event,
    EventAttribute,
    EventAttributeType,
    EventEvidence,
    EventPartyReference,
    ExternalIdentifier,
    ExternalIdentifierType,
    FinancialValue,
    FinancialValueKind,
    IdentifierSubjectType,
    ObservationRole,
    Provenance,
    RetentionClass,
    SourceLineage,
    SourceObservation,
)
from ragged_claws.models.base import CanonicalModel
from ragged_claws.resolution import (
    day_value,
    deterministic_entity_id_from_cik,
    deterministic_external_identifier_id,
    normalize_cik,
)
from ragged_claws.storage import (
    CanonicalConflictError,
    CanonicalParquetStore,
    DataLayout,
    RawCaptureManifest,
    capture_raw_bytes,
    deterministic_source_observation_id,
    load_envelope_records,
    persist_envelope_records,
)
from ragged_claws.temporal import (
    ActionableTimeResolver,
    AvailabilityPolicy,
    apply_availability_policy,
)

PROVIDER = "sec.edgar"
SOURCE_FAMILY = "sec.ownership"
ADAPTER_VERSION = "sec-form4/1.0.0"
PARSER_VERSION = "sec-ownership-xml/1.0.0"
TRANSFORM_VERSION = "sec-form4-mapping/1.0.0"
PROVENANCE_NAMESPACE = UUID("dc94edf2-b05f-4742-9a3d-66f5a5677b64")
EVENT_NAMESPACE = UUID("3ccf9ea0-633b-4b78-af1f-782ad2ae4eaa")
EVIDENCE_NAMESPACE = UUID("0c7ec7a4-8765-4dd5-92d1-d4cab404aa97")


def acceptance_policy() -> AvailabilityPolicy:
    """An explicit research convention, never a measured dissemination instant."""
    return AvailabilityPolicy(
        policy_id="sec_acceptance_plus_five_minutes",
        policy_version="1.0.0",
        delay=timedelta(minutes=5),
        source_family=SOURCE_FAMILY,
        rationale="EDGAR acceptance plus an explicit five-minute research delay; SEC does not "
        "guarantee dissemination latency. This assumption does not measure first availability.",
    )


class SecForm4Adapter:
    def __init__(self, layout: DataLayout) -> None:
        self.layout = layout
        self.store = CanonicalParquetStore(layout)
        self.staging_path = layout.staging / "sec_ownership.parquet"
        self.mapping_path = layout.staging / "sec_ownership_mapping.parquet"

    def capture(
        self,
        content: bytes,
        *,
        accession: str,
        retrieved_at: datetime,
        source_locator: str,
        metadata: Mapping[str, str] | None = None,
    ) -> RawCaptureManifest:
        locator = urlsplit(source_locator)
        if locator.hostname == "www.sec.gov" and (
            f"/{accession.replace('-', '')}/" not in locator.path
            or (locator.path.endswith(".txt") and not locator.path.endswith(f"/{accession}.txt"))
        ):
            raise SecParseError("source URL/accession contradiction")
        return capture_raw_bytes(
            self.layout,
            content,
            provider_namespace=PROVIDER,
            source_family=SOURCE_FAMILY,
            source_native_id=accession,
            retrieved_at=retrieved_at,
            observed_at=retrieved_at,
            source_locator=source_locator,
            request_parameters=dict(metadata or {}),
            adapter_version=ADAPTER_VERSION,
            parser_version=PARSER_VERSION,
            retention_class=RetentionClass.PUBLIC,
            license_name="sec-public-filings",
        )

    def normalize(
        self,
        content: bytes,
        manifest: RawCaptureManifest,
        *,
        acceptance_timezone: str | None = None,
        document_name: str | None = None,
        form_type: str | None = None,
        filed_as_of: date | None = None,
        acceptance_raw: str | None = None,
    ) -> SecFiling:
        if hashlib.sha256(content).hexdigest() != manifest.content_hash.value:
            raise SecParseError("input bytes disagree with capture hash")
        if manifest.provider_namespace != PROVIDER or manifest.source_native_id is None:
            raise SecParseError("capture is not an SEC filing")
        return parse_filing(
            content,
            accession=manifest.source_native_id,
            source_version_id=deterministic_source_observation_id(
                PROVIDER,
                manifest.source_native_id,
                manifest.content_hash.value,
            ),
            acceptance_timezone=acceptance_timezone,
            document_name=document_name,
            form_type=form_type,
            filed_as_of=filed_as_of,
            acceptance_raw=acceptance_raw,
        )

    def observation(self, filing: SecFiling, manifest: RawCaptureManifest) -> SourceObservation:
        if (
            filing.acceptance_time is not None
            and filing.acceptance_time.timestamp is not None
            and filing.acceptance_time.timestamp > manifest.retrieved_at
        ):
            raise SecParseError("acceptance time cannot follow collection time")
        return SourceObservation(
            source_observation_id=filing.source_version_id,
            provider_namespace=PROVIDER,
            source_native_id=filing.accession,
            lineage=SourceLineage(
                source_family=SOURCE_FAMILY, observation_role=ObservationRole.PRIMARY_SOURCE
            ),
            retrieved_at=manifest.retrieved_at,
            observed_at=manifest.retrieved_at,
            public_time=filing.acceptance_time,
            raw_content_hash=manifest.content_hash,
            adapter_version=ADAPTER_VERSION,
            parser_version=PARSER_VERSION,
            source_locator=manifest.source_locator,
            retention_class=RetentionClass.PUBLIC,
            license_name="sec-public-filings",
        )

    def canonicalize(
        self,
        filing: SecFiling,
        observation: SourceObservation,
        *,
        policy: AvailabilityPolicy | None = None,
    ) -> SecBundle:
        if observation.source_observation_id != filing.source_version_id:
            raise SecParseError("filing/observation identity contradiction")
        policy = policy or acceptance_policy()
        if policy.source_family not in (None, SOURCE_FAMILY):
            raise SecParseError("availability policy has a different source family")
        provenance = Provenance(
            provenance_id=uuid5(
                PROVENANCE_NAMESPACE, f"{observation.source_observation_id}:{TRANSFORM_VERSION}"
            ),
            source_observation_ids=(observation.source_observation_id,),
            derivation_kind=DerivationKind.NORMALIZATION,
            derived_at=observation.observed_at,
            transform_version=TRANSFORM_VERSION,
        )
        actionability = (
            ActionableTimeResolver().resolve(
                apply_availability_policy(
                    observation.public_time,
                    policy,
                )
            )
            if observation.public_time is not None
            else None
        )
        existing_entities = self.store.load(Entity)
        existing_claims = self.store.load(ExternalIdentifier)
        by_cik: dict[str, Entity] = {}
        for entity in existing_entities:
            for claim in (*entity.external_identifiers, *existing_claims):
                if (
                    claim.identifier_type is ExternalIdentifierType.SEC_CIK
                    and claim.subject_type is IdentifierSubjectType.ENTITY
                    and claim.subject_id == entity.entity_id
                ):
                    cik = normalize_cik(claim.value)
                    if cik in by_cik and by_cik[cik].entity_id != entity.entity_id:
                        raise SecParseError("conflicting existing CIK identity")
                    by_cik[cik] = entity
        issuer_id = deterministic_entity_id_from_cik(filing.issuer_cik)
        issuer = by_cik.get(filing.issuer_cik)
        if issuer is None:
            issuer = Entity(
                entity_id=issuer_id,
                entity_type=EntityType.ISSUER,
                display_name=filing.issuer_name,
                provenance_id=provenance.provenance_id,
            )
        elif issuer.entity_type is not EntityType.ISSUER:
            raise SecParseError("existing issuer CIK has incompatible entity type")
        by_cik[filing.issuer_cik] = issuer
        resolved = {owner.cik: by_cik[owner.cik] for owner in filing.owners if owner.cik in by_cik}
        entities = {issuer.entity_id: issuer, **{e.entity_id: e for e in resolved.values()}}
        subjects = {filing.issuer_cik: issuer, **resolved}
        claims = tuple(
            ExternalIdentifier(
                external_identifier_id=deterministic_external_identifier_id(
                    subject_type=IdentifierSubjectType.ENTITY,
                    subject_id=entity.entity_id,
                    identifier_type=ExternalIdentifierType.SEC_CIK,
                    value=cik,
                    source_observation_id=observation.source_observation_id,
                ),
                subject_type=IdentifierSubjectType.ENTITY,
                subject_id=entity.entity_id,
                identifier_type=ExternalIdentifierType.SEC_CIK,
                value=cik,
                source_observation_id=observation.source_observation_id,
                provenance_id=provenance.provenance_id,
                observed_at=observation.observed_at,
                # Acceptance is not proof that this separate entity-type claim was known then.
                known_from=None,
            )
            for cik, entity in sorted(subjects.items())
        )
        unresolved = tuple(
            sorted(owner.cik for owner in filing.owners if owner.cik not in resolved)
        )
        events: list[Event] = []
        evidence: list[EventEvidence] = []
        for row in filing.rows:
            if row.exclusion_reason is not None:
                continue
            if row.transaction_date is None:
                raise SecParseError("qualifying row has no occurrence date")
            coordinate = f"{filing.accession}:{filing.document_sequence}:{row.coordinate}"
            event_id = uuid5(EVENT_NAMESPACE, coordinate)
            evidence_id = uuid5(
                EVIDENCE_NAMESPACE, f"{event_id}:{observation.source_observation_id}"
            )
            evidence.append(
                EventEvidence(
                    event_evidence_id=evidence_id,
                    event_id=event_id,
                    source_observation_ids=(observation.source_observation_id,),
                    provenance_id=provenance.provenance_id,
                )
            )
            values = (
                ()
                if row.shares is None
                else (
                    FinancialValue(
                        name="transaction_shares",
                        kind=FinancialValueKind.QUANTITY,
                        value=row.shares,
                        unit="shares",
                    ),
                )
            )
            attributes = [
                _attribute("filing_group_id", str(filing.filing_group_id)),
                _attribute("accession", filing.accession),
                _attribute("source_document", filing.document_name),
                _attribute("source_row", row.coordinate),
                _attribute("transaction_code", row.code or "missing"),
                _attribute("direct_indirect_ownership", row.direct_indirect or "unknown"),
                _attribute("acquired_disposed", row.acquired_disposed or "unknown"),
                _attribute("security_title", row.security_title or "unknown"),
                _attribute("filed_as_of", str(filing.filed_as_of or "unknown")),
                _attribute("timing_status", filing.timing_reason or "acceptance_policy_assumption"),
                _attribute(
                    "reporting_owners",
                    json.dumps(
                        [owner.model_dump(mode="json") for owner in filing.owners],
                        sort_keys=True,
                    ),
                ),
                _attribute("unresolved_owner_ciks", json.dumps(unresolved)),
                _attribute("ownership_attribution", "filing_reporting_owners_not_row_allocation"),
                _attribute("footnote_ids", json.dumps(row.footnote_ids)),
            ]
            if row.price is not None:
                # Ownership XML does not declare a currency. Do not invent USD.
                attributes.append(
                    EventAttribute(
                        name="reported_price_per_share",
                        value_type=EventAttributeType.DECIMAL,
                        value=row.price,
                    )
                )
            events.append(
                Event(
                    event_id=event_id,
                    event_type="equity_purchase" if row.code == "P" else "equity_sale",
                    issuer_entity_id=issuer.entity_id,
                    actors=tuple(
                        EventPartyReference(entity_id=entity.entity_id, role="reporting_owner")
                        for _, entity in sorted(resolved.items())
                    ),
                    occurrence_time=day_value(row.transaction_date),
                    public_time=observation.public_time,
                    actionable_at=actionability.actionable_at if actionability else None,
                    financial_values=values,
                    attributes=tuple(attributes),
                    event_evidence_ids=(evidence_id,),
                    provenance_id=provenance.provenance_id,
                )
            )
        if len({event.event_id for event in events}) != len(events):
            raise SecParseError("duplicate transaction coordinates in canonical mapping")
        return SecBundle(
            filing=filing,
            observation=observation,
            provenance=provenance,
            entities=tuple(sorted(entities.values(), key=lambda e: str(e.entity_id))),
            identifier_claims=claims,
            events=tuple(events),
            evidence=tuple(evidence),
            unresolved_owner_ciks=unresolved,
            availability_policy=policy,
            actionability=actionability,
        )

    def persist(self, bundle: SecBundle) -> None:
        """Preflight all datasets before publication; filesystem writes remain single-writer."""
        staged = self.load_staging()
        _check_existing(staged, (bundle.filing,), "source_version_id")
        mappings = self.load_mappings()
        for previous in mappings:
            if (
                previous.filing.source_version_id == bundle.filing.source_version_id
                and previous != bundle
            ):
                raise CanonicalConflictError("SEC source version has a different mapping")
        # Changed bytes for an accession require reconciliation, including files with no P/S rows.
        for prior_filing in staged:
            if prior_filing.accession == bundle.filing.accession and prior_filing != bundle.filing:
                raise CanonicalConflictError(
                    "changed SEC accession requires explicit reconciliation"
                )
        _check_existing(
            self.store.load(SourceObservation), (bundle.observation,), "source_observation_id"
        )
        _check_existing(self.store.load(Provenance), (bundle.provenance,), "provenance_id")
        _check_existing(self.store.load(Entity), bundle.entities, "entity_id")
        _check_existing(
            self.store.load(ExternalIdentifier), bundle.identifier_claims, "external_identifier_id"
        )
        _check_existing(self.store.load(EventEvidence), bundle.evidence, "event_evidence_id")
        _check_existing(self.store.load(Event), bundle.events, "event_id")
        persist_envelope_records(
            self.staging_path,
            model_type=SecFiling,
            id_field="source_version_id",
            records=(bundle.filing,),
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
        persist_envelope_records(
            self.mapping_path,
            model_type=SecBundle,
            id_field="source_version_id",
            records=(bundle,),
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )
        self.store.persist(SourceObservation, (bundle.observation,))
        self.store.persist(Provenance, (bundle.provenance,))
        self.store.persist(Entity, bundle.entities)
        self.store.persist(ExternalIdentifier, bundle.identifier_claims)
        self.store.persist(EventEvidence, bundle.evidence)
        self.store.persist(Event, bundle.events)

    def load_staging(self) -> tuple[SecFiling, ...]:
        return load_envelope_records(
            self.staging_path,
            model_type=SecFiling,
            id_field="source_version_id",
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )

    def load_mappings(self) -> tuple[SecBundle, ...]:
        return load_envelope_records(
            self.mapping_path,
            model_type=SecBundle,
            id_field="source_version_id",
            dataset_kind="staging",
            model_schema_version="1.0.0",
        )

    def ingest(
        self,
        content: bytes,
        *,
        accession: str,
        retrieved_at: datetime,
        source_locator: str,
        acceptance_timezone: str | None = None,
        document_name: str | None = None,
        form_type: str | None = None,
        filed_as_of: date | None = None,
        acceptance_raw: str | None = None,
        policy: AvailabilityPolicy | None = None,
    ) -> SecBundle:
        manifest = self.capture(
            content,
            accession=accession,
            retrieved_at=retrieved_at,
            source_locator=source_locator,
            metadata={
                "acceptance_timezone": acceptance_timezone or "unconfirmed",
                "document_name": document_name or "submission",
                "form_type": form_type or "submission",
                "acceptance_raw": acceptance_raw or "submission",
                "filed_as_of": str(filed_as_of or "submission"),
            },
        )
        filing = self.normalize(
            content,
            manifest,
            acceptance_timezone=acceptance_timezone,
            document_name=document_name,
            form_type=form_type,
            filed_as_of=filed_as_of,
            acceptance_raw=acceptance_raw,
        )
        candidate = self.observation(filing, manifest)
        previous = next(
            (
                mapping
                for mapping in self.load_mappings()
                if mapping.source_version_id == filing.source_version_id
            ),
            None,
        )
        existing = next(
            (
                obs
                for obs in self.store.load(SourceObservation)
                if obs.source_observation_id == candidate.source_observation_id
            ),
            None,
        )
        if existing is None and previous is not None:
            existing = previous.observation
        observation = accept_source_observation(existing, candidate)
        if previous is not None:
            if (
                previous.filing != filing
                or previous.observation != observation
                or previous.availability_policy != (policy or acceptance_policy())
                or previous.provenance.transform_version != TRANSFORM_VERSION
            ):
                raise CanonicalConflictError("SEC source version has different mapping semantics")
            # Frozen mappings survive later catalog enrichment. Revalidate/repair missing datasets
            # after an interrupted publication without recalculating attribution or first-seen time.
            self.persist(previous)
            return previous
        bundle = self.canonicalize(filing, observation, policy=policy)
        self.persist(bundle)
        return bundle


def _check_existing[RecordT: CanonicalModel](
    existing: Sequence[RecordT], incoming: Sequence[RecordT], key: str
) -> None:
    indexed = {getattr(record, key): record for record in existing}
    for record in incoming:
        identity = getattr(record, key)
        if identity in indexed and indexed[identity] != record:
            raise CanonicalConflictError(f"{type(record).__name__} has a different payload")
        indexed[identity] = record


def _attribute(name: str, value: str) -> EventAttribute:
    return EventAttribute(name=name, value_type=EventAttributeType.TEXT, value=value)
