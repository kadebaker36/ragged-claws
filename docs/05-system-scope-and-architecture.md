# Ragged Claws — System Scope and Architecture

**Status:** Draft v0.2  
**As of:** 2026-09-17  
**Scope:** Bootstrap research architecture

> `docs/09-adversarial-architecture-review.md` contains the detailed failure analysis behind the hardened decisions summarized here.

## 1. Purpose

Ragged Claws is a public-information investment research system.

Its job is to determine whether observable behavior by economically informed, institutionally connected, or incentive-aligned actors contains durable information about future public-market returns.

```text
incentives
    ↓
behavior
    ↓
public traces
    ↓
source observations + evidence lineage
    ↓
canonical events / entities / relationships
    ↓
point-in-time feature state
    ↓
forward benchmark-relative outcomes
    ↓
validated investment signals
```

The objective is practical: make better investment decisions and, if the evidence supports it, make money.

## 2. V0 research mandate

> Given only information publicly available at time T, can observable economic behavior around a public company identify materially different forward risk-adjusted returns?

### In scope

- U.S.-listed public equities
- long-only research
- medium-term horizons
- corporate-insider activity
- political-household financial disclosures where source data supports ownership attribution
- government spending/procurement context
- lobbying context
- documented person/organization/company relationships
- entity/security/listing resolution
- benchmark-relative outcomes
- targeted agent enrichment
- reproducible backtesting and forward paper observation

### Out of scope for V0

- options execution
- intraday trading
- shorting/leverage
- automated live brokerage execution
- generalized sentiment/social-media models
- election forecasting
- legal/moral/person scoring
- generalized corruption/elite scores
- broad ML before simpler hypotheses survive testing
- market-microstructure strategies

## 3. Architectural principles

### Event-centric, evidence-aware

The main research object is a canonical timestamped Event, but a canonical Event is not the same thing as a vendor row.

The same disclosure may be observed by SEC, Quiver, Unusual Whales, or another provider. Those are multiple **SourceObservations** linked through evidence to one underlying event where appropriate.

This prevents duplicated vendor coverage from becoming fake signal convergence.

### Graph-enriched

Relationships supply context:

```text
PERSON ──spouse_of────────► PERSON
PERSON ──director_of──────► COMPANY
PERSON ──employed_by──────► ORGANIZATION
ENTITY ──parent_of────────► ENTITY
HOUSEHOLD ──owns──────────► SECURITY
COMPANY ──recipient_of────► FEDERAL_AWARD
COMPANY ──lobbies_on──────► ISSUE
```

Relationship presence is not automatically a trading signal.

### Company/security-centered

Politicians, insiders, institutions, contracts, lobbying, and networks are observations surrounding an investable security.

```text
                       people / households
                               │
                               ▼
institutions ───────────────► ISSUER ◄──────────── government
                               │
                             issues
                               ▼
                         SECURITY/CLASS
                               │
                           listed as
                               ▼
                    LISTING / SYMBOL / VENUE
                               │
                               ▼
                         forward return
```

### Point-in-time correct

Occurrence time, source-public time, effective availability under an explicit versioned policy,
observed time, and actionable time are separate concepts.

A historical feature may use only information whose historical public/known timing is defensible at that simulated decision time.

A relationship's effective date does not itself prove when the market knew about it.

### Vendor-independent internally

External sources are adapters, not architecture.

Research code consumes canonical models rather than provider response keys.

### Provenance and lineage first

The system must be able to reconstruct:

1. immutable/raw source capture;
2. SourceObservation;
3. canonical event/entity/relationship mapping;
4. feature snapshot;
5. outcome;
6. research/paper decision.

No derived conclusion overwrites its evidence.

## 4. Four-interface rule

Use the cheapest reliable interface appropriate to the job.

### A — API / bulk

Deterministic ingestion and reproducible historical research.

Examples: SEC, USAspending, LittleSis, GLEIF, OpenFIGI, FRED/ALFRED, LobbyView, ICIJ.

### B — RSS / webhook / event feed

Sparse timely event detection without wasteful polling.

Examples: SEC/GovInfo feeds; later CourtListener alerts where justified.

### C — MCP / agent-native

Contextual retrieval and enrichment.

Examples: Quiver MCP, GovInfo MCP, CourtListener MCP, later Alpaca agent tooling.

Durable model inputs still pass through evidence/canonical persistence.

### D — browser / agent fallback

Use only where structured interfaces are unavailable/uneconomic **and source terms permit automated access**.

Clarence is a narrow adapter/enrichment mechanism, not an analytical authority.

A scraping tool's technical capability is not permission to automate a target site.

## 5. Core system layers

```text
SOURCE INTERFACES
API/Bulk | RSS/Webhook | MCP | permitted Browser/Agent
        ↓
IMMUTABLE RAW CAPTURE + MANIFEST/HASH
        ↓
SOURCE OBSERVATION / EVIDENCE LINEAGE
        ↓
CANONICAL INTERNAL MODEL
Entity | Security | Listing | Relationship | Event
        ↓
POINT-IN-TIME STATE
valid time + known/public time + observed time
        ↓
FEATURE ENGINE
        ↓
OUTCOME / BACKTEST ENGINE
        ↓
RESEARCH LEDGER / SIGNAL LEDGER
        ↓
paper → controlled live pilot
```

## 6. Canonical domain concepts

### SourceObservation

One provider/source-native observation.

Minimum concepts:

- provider/source namespace
- source-native ID/accession
- source family / underlying primary lineage where known
- retrieval/observed time
- source-public time where known
- raw capture hash
- adapter/parser version
- source locator
- retention/license class

### EventEvidence

Links one canonical Event to one or more SourceObservations.

Multiple providers can corroborate parsing without increasing independent convergence count.

### Entity

Canonical person, household, issuer/company, fund, government body, nonprofit, legal entity, or organization.

Names/aliases/external identifiers are sourced claims, not safe permanent identity by themselves.

### Security / Listing

Separate issuer, security/share class, and listing.

Ticker is a time-varying listing property.

Identifier types such as FIGI/share-class FIGI/composite FIGI retain their specific semantics.

### Relationship

A sourced connection between entities with, where applicable:

- valid/effective time;
- known/public time;
- observed/snapshot time;
- confidence;
- evidence/provenance.

### TemporalValue / PartialDate

Preserves raw temporal text and precision. Do not fabricate exact timestamps from coarse/partial dates.

### Event

Timestamped observable occurrence with actor/economic unit, issuer/security/listing linkage where relevant, underlying transaction/event date, public timing, actionable timing, exact financial values/ranges, normalized attributes, and evidence links.

### FeatureSnapshot

Immutable representation of information allowable at a specific historical decision time.

### Outcome

Forward result from the documented actionable-time/entry convention, with benchmark, price-source/adjustment metadata, and completion/censoring/missing status.

### Decision

Paper/live decision preserving model/config/features/source state and portfolio context. Live decisions are outside M0/M1.

## 7. Temporal and execution convention

First derive effective availability from source-public evidence using an explicit, named, versioned
availability policy. Preserve both values; never overwrite the source-public evidence.

Then, for the daily-bar bootstrap:

1. precise effective availability before regular-session open → that session's open;
2. effective availability at/after regular-session open → next regular session's open;
3. date-only disclosure → next regular session's open after that date unless a stronger source rule exists.

Never use a same-day daily-bar open for information that became effectively available at or after
the open.

## 8. Storage convention

Bootstrap persistence has one authority:

- raw = append-only original captures + manifests/hashes;
- staging = source-normalized Parquet;
- curated = canonical Parquet;
- DuckDB = rebuildable query/catalog/research layer.

Avoid authoritative dual writes to both DuckDB tables and Parquet.

## 9. Source roles

### Primary sources

Anchor material facts and public timing where practical.

### Quiver

Initial paid normalized politics/government/lobbying layer and MCP research surface.

Quiver-derived performance fields are not PIT features. Quiver copies of primary events are not independent convergence.

### LittleSis

Foundational relationship/context graph. Effective dates and curation dates are not interchangeable with historical knowledge dates.

### Unusual Whales

Principal external reference model and intended premium upgrade. Until the supported API is justified, use available public/manual surfaces only within applicable terms; do not attempt to recreate the commercial feed through scraping.

### ICIJ / other network sources

Selective entity/network enrichment. A match is a relationship/context observation, not a wrongdoing label.

## 10. Clarence's role

Clarence should:

- execute narrow source-specific enrichment;
- receive minimal durable state;
- return strict structured deltas;
- preserve source/capture timing;
- operate only where source terms allow;
- enrich candidate events rather than broadly crawl the web.

Clarence should not decide investments, infer misconduct, manufacture facts, or recreate commercial feeds.

## 11. V0 implementation sequence

### Milestone A — hardened canonical/evidence spine

Deliver evidence/source-observation, canonical identity/event, temporal, Decimal financial value, and persistence conventions.

### Milestone B — first real primary event + market outcome

SEC Form 4 P/S + market data prove the event/timestamp/actionable/outcome spine.

If Alpaca Basic is the bootstrap historical provider, the initial historical window is 2016-present.

### Milestone C — identity and graph context

Add issuer/security/listing resolution and LittleSis context under bitemporal/PIT rules.

### Milestone D — Quiver normalized context

Add only endpoints required by the first research dataset; preserve vendor licensing and source lineage.

### Milestone E — first predeclared validation dataset

Produce descriptive benchmark-relative outcomes under a hypothesis ledger, with survivorship/right-censoring/missing coverage visible.

### Milestone F — targeted UW bridge / later premium feed

Only after the baseline system demonstrates what additional UW variables are worth paying for.

## 12. Architecture test

Any proposed feature/source must answer:

1. What observable event, fact, or relationship is represented?
2. What is the underlying source family?
3. When was it true?
4. When was it publicly knowable?
5. When did our source observe it?
6. Is the temporal precision real or fabricated?
7. Can it map to canonical identity without guessing?
8. Is the provider giving us future-derived metadata that must be quarantined?
9. Can the incremental value be tested without survivorship or duplicate-vendor bias?
10. Are storage/retention/automation rights compatible with the intended use?

If those answers are weak, the feature does not belong in V0.
