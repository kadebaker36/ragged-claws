# Ragged Claws — Implementation Roadmap

**Status:** Draft v0.2  
**As of:** 2026-09-17  
**Scope:** Milestone 0 and Milestone 1

> Read `docs/09-adversarial-architecture-review.md` with this document. Its hardening decisions are binding where they narrow an older assumption.

## 1. Objective

The first implementation goal is not a dashboard, trading bot, or composite score.

It is a trustworthy vertical slice:

```text
source observation
    ↓
evidence/provenance
    ↓
canonical event
    ↓
entity/security/listing resolution
    ↓
public → actionable timestamp
    ↓
market outcome
    ↓
benchmark-relative research result
```

If that chain is not correct and reproducible, later graph/network features are not worth building.

## 2. Technical posture

V0 is local-first, cheap, inspectable, cross-platform, and replaceable piece by piece.

### Bootstrap support target

- **Language:** Python 3.12
- **Environment/package manager:** `uv`
- **Canonical models:** Pydantic v2
- **Persistent analytical datasets:** Parquet
- **Query/catalog/research engine:** DuckDB, rebuildable from Parquet
- **Dataframe layer:** Polars where useful
- **HTTP:** `httpx`
- **CLI:** Typer
- **Trading calendar:** `exchange_calendars` or explicitly reviewed equivalent
- **Tests:** pytest
- **Lint/format:** Ruff
- **Type checking:** one of mypy/pyright, chosen once and enforced
- **Config:** environment variables + typed settings; no secrets in Git
- **CI:** Ubuntu + Windows, Python 3.12

Current releases of the proposed core packages support Python 3.12. M0 should still pin/lock resolved dependencies through `uv.lock` so compatibility is reproducible rather than assumed.

Do not introduce Postgres, Redis, queues, Docker orchestration, cloud infrastructure, or a web framework until the workload demonstrates a need.

## 3. Storage authority

Avoid dual authoritative state.

Bootstrap convention:

```text
data/
├── raw/          # immutable source captures + manifests/hashes
├── staging/      # source-normalized Parquet
├── curated/      # canonical Parquet datasets
├── research/     # reproducible derived research outputs
├── snapshots/    # frozen/versioned research states
└── cache/        # disposable/rebuildable
```

**Parquet is canonical persisted analytical state. DuckDB is a query/catalog/research layer that must be rebuildable from those persisted datasets.**

Raw captures are append-only. Do not overwrite a prior capture merely because a provider later changes the record.

## 4. Planned repository structure

```text
ragged-claws/
├── README.md
├── AGENTS.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── .gitattributes
│
├── docs/
├── schemas/
│
├── src/ragged_claws/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── models/
│   ├── temporal/
│   ├── storage/
│   ├── resolution/
│   ├── ingestion/
│   ├── features/
│   ├── outcomes/
│   ├── backtest/
│   └── reporting/
│
├── research/
│   └── hypotheses/
│
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── regression/
│
└── data/
    └── README.md
```

`data/` contents other than documentation are ignored by Git. Commercial/restricted vendor payloads are not committed unless redistribution is explicitly permitted.

## 5. Schema authority and core models

Pydantic models under `src/ragged_claws/models/` are authoritative. JSON Schema files under `schemas/` are generated artifacts.

### 5.1 SourceObservation

Represents one source-native record/capture.

Minimum concepts:

- stable observation ID
- source/provider namespace
- source-native ID/accession
- source family / underlying primary-source family where known
- retrieval/observed timestamp
- source-public timestamp where known
- raw content hash
- adapter/parser version
- source URL/locator
- retention/license classification

This object is critical for dedupe and source-lineage accounting.

### 5.2 EventEvidence

Many-to-many link between canonical Events and SourceObservations.

Multiple vendors may corroborate one event without creating multiple independent signals.

### 5.3 Entity

Represents a canonical person, household, company, fund, government body, nonprofit, legal entity, or organization.

Do not use mutable names as permanent identity.

Aliases and external identifiers should be represented in a way that preserves source/provenance and, where relevant, validity/knowledge timing rather than being an unversioned bag of strings.

### 5.4 Security and Listing

Separate:

```text
Issuer Entity → Security/Share Class → Listing(symbol + exchange + effective dates)
```

Ticker is not canonical identity.

Identifier records must preserve identifier type, including distinctions among instrument FIGI, share-class FIGI, and composite FIGI.

### 5.5 Relationship

Required concepts:

- source entity
- target entity
- relationship type
- `valid_from` / `valid_to` where known
- `known_from` / public-as-of where defensible
- `observed_at`
- provenance/evidence
- confidence

A historical effective date does not by itself establish historical public knowledge.

### 5.6 TemporalValue / PartialDate

Represent source timing without inventing precision.

Support at least:

- year precision
- month precision
- day precision
- minute/second timestamp precision
- raw source text
- source timezone/interpretation where applicable

This is required for sources such as LittleSis that can expose partial dates.

### 5.7 Event

Minimum concepts:

- event ID
- event type
- actor/economic unit where relevant
- issuer/company
- security/listing where relevant
- underlying event/transaction date
- public time/date with source precision
- actionable timestamp
- exact financial values/ranges using `Decimal`
- canonical normalized attributes
- evidence links

### 5.8 Provenance

A canonical record must answer:

- where did this come from?
- what source-native record identifies it?
- when did we retrieve/observe it?
- when was it public, if known?
- what raw capture/hash produced it?
- what adapter/parser version produced it?
- was it primary, vendor-normalized, or enrichment data?

### 5.9 FeatureSnapshot

Represents only information allowed at a specific historical decision time.

Snapshot queries must enforce `known_from/public_as_of <= snapshot time` where knowledge timing exists and exclude relationships/claims whose historical knowledge time is not defensible when used as predictive features.

### 5.10 Outcome

Minimum concepts:

- event ID
- security/listing ID
- actionable timestamp
- entry timestamp/price convention
- horizon
- security return
- benchmark return
- excess return
- status (`complete`, `right_censored`, `missing_price`, `unresolved_security`, `terminal/delisted`, explicit exclusion)
- price-source provenance
- price adjustment convention

MFE/MAE are optional until their daily-bar semantics are fixed and tested.

## 6. Point-in-time actionable convention

V0 uses a conservative convention compatible with daily bars:

1. precise public timestamp before regular-session open → that session's open;
2. public timestamp at/after regular-session open → next regular session's open;
3. date-only disclosure → next regular session's open after that date unless a stronger source-specific rule exists;
4. preserve public and actionable times separately.

Never use a daily bar's same-day open for information published after that open.

Tests cover weekends, holidays, DST, early closes, premarket, intraday, after-hours, and date-only disclosures.

## 7. Milestone 0 — Research infrastructure

### M0.1 Repository/bootstrap

Deliver:

- Python 3.12 project scaffold
- `uv` lockfile
- `.gitignore`
- `.env.example`
- `.gitattributes`
- CLI entry point
- Windows + Ubuntu GitHub Actions CI
- Ruff/pytest/type-check commands

Acceptance:

- clean clone can `uv sync --frozen` after lockfile exists;
- tests/lint/type checks pass on supported CI platforms;
- paths/timezone behavior is platform-independent;
- no local data/secrets tracked.

### M0.2 Canonical domain/evidence models

Deliver:

- SourceObservation
- EventEvidence
- Entity
- external identifier / alias claim representation
- Security
- Listing
- Relationship
- TemporalValue/PartialDate
- Event
- Provenance
- FeatureSnapshot
- Outcome

Acceptance:

- deterministic serialization/schema generation;
- financial values use Decimal;
- partial dates survive roundtrip;
- source lineage can represent SEC + Quiver + UW observations of one event without producing three canonical events;
- ticker is never permanent identity.

### M0.3 Point-in-time / bitemporal rules

Implement:

- timezone-aware UTC normalization where precision supports it;
- source precision/raw time preservation;
- valid vs known vs observed semantics;
- public → actionable-time rule;
- historical snapshot filters.

Acceptance:

Regression tests prove later-discovered relationships and post-event vendor metrics cannot leak into prior snapshots.

### M0.4 Persistence / idempotency

Deliver:

- append-only raw capture manifest/hash convention;
- source-normalized staging Parquet;
- canonical curated Parquet;
- rebuildable DuckDB query/catalog layer;
- deterministic source-observation IDs and explicit canonicalization rules;
- schema metadata.

Acceptance:

Re-ingestion of the same raw capture creates no duplicate observation/event state and does not mutate the raw object.

### M0.5 Synthetic adapter contract

Create a tiny `SyntheticAdapter` used only by tests to prove:

```text
raw fixture
→ source observation
→ canonical mapping
→ persistence
→ reload
```

No real SEC implementation is required to close M0.

### Milestone 0 exit gate

M0 is complete when the synthetic vertical slice passes on Windows and Ubuntu with provenance, lineage, temporal semantics, deterministic IDs, and storage roundtrips intact.

## 8. Milestone 1 — First evidence pipeline

### M1.1 SEC Form 4 ingestion

Initial scope:

- Form 4 only;
- Table I non-derivative `P` and `S` transactions;
- filing-level group/accession preserved;
- transaction-level canonical events;
- multiple reporting owners/rows handled;
- exact EDGAR `ACCEPTANCE-DATETIME` preserved when available;
- SEC declared User-Agent and centralized rate limiting/backoff.

Do not use transaction date or nightly index date as a substitute for exact public time when the acceptance timestamp is available.

### M1.2 Market-data/outcome engine

Provider-neutral interface first; Alpaca Basic is a reasonable bootstrap provider.

If Alpaca Basic is used, initial historical research window is **2016-present**.

Implement:

- local exchange calendar;
- public → actionable-session rule;
- explicit bar adjustment mode;
- exact entry/exit convention;
- SPY benchmark;
- outcome statuses/right-censoring;
- survivorship/delisting/missing-coverage audit.

SPY-relative results are mandatory.

Sector-relative results are optional until a point-in-time-safe sector mapping exists.

### M1.3 Baseline entity/security/listing resolution

Resolution order:

1. SEC issuer/CIK identity;
2. historical listing/symbol evidence;
3. GLEIF entity enrichment where useful;
4. OpenFIGI instrument/share-class/composite identifiers where useful.

Unresolved mappings remain explicit.

### M1.4 LittleSis adapter/snapshot

Use LittleSis for graph context/entity enrichment.

Preserve:

- LittleSis IDs;
- effective relationship dates;
- curation `updated_at` separately;
- partial date precision;
- snapshot/observed time;
- CC BY-SA 4.0 provenance/attribution metadata.

Undated/current relationships or relationships without defensible historical knowledge time may not silently enter historical predictive snapshots.

### M1.5 Quiver Hobbyist adapter

Initial priorities:

- political/congress trades/holdings;
- politician profiles where useful;
- government contracts;
- lobbying;
- selected political/exposure context under the plan.

Rules:

- raw licensed responses remain local/untracked subject to license terms;
- Git tests use synthetic vendor fixtures unless redistribution is explicitly allowed;
- vendor `Date` fields receive canonical meaning only after endpoint semantics are documented;
- post-event fields such as vendor-calculated returns are quarantined from PIT features;
- self/spouse/household distinctions are preserved when supplied, not invented;
- source lineage identifies normalized copies of underlying primary events.

### M1.6 First vertical-slice research dataset

Produce reproducible event-level research rows containing:

- canonical event;
- evidence/source lineage;
- resolved issuer/security/listing;
- public/actionable timing;
- selected graph/context features that pass PIT rules;
- market outcomes;
- SPY-relative outcomes;
- sector-relative outcomes only where mapping is PIT-safe.

First descriptive cuts can include:

- insider purchases vs sales;
- officer/director role where available;
- transaction-size buckets;
- political ownership distinctions where actually available;
- disclosure-lag buckets;
- simple relationship-context presence/absence.

No optimized composite score.

## 9. Research validation protocol

Before viewing the untouched validation-period result, create a hypothesis record under `research/hypotheses/` with:

- hypothesis ID;
- population;
- feature definition;
- horizon(s);
- benchmark;
- sample filters;
- discovery period;
- validation period;
- expected direction if declared;
- code/config version.

Keep negative findings.

Reports must show at minimum:

- qualifying event count;
- distinct issuer count;
- complete outcome count by horizon;
- right-censored count;
- unresolved/missing/delisted count;
- mean/median absolute return;
- mean/median SPY-relative return;
- distribution statistics;
- rejected/excluded record counts by reason.

Repeated issuer events are correlated; M1 may remain descriptive, but later inferential analysis must account for dependence rather than treating every row as IID.

## 10. Source-dependence rule

The backtester/research layer must not infer stronger convergence from duplicated vendor coverage.

Examples:

```text
SEC Form 4 direct parse
+ Quiver copy of same Form 4
+ UW copy of same Form 4
= one underlying insider disclosure family
```

Provider corroboration is useful for parsing/QA, but independent-signal convergence requires distinct underlying event families.

## 11. Test taxonomy

### Unit

Models, temporal precision, Decimal parsing, deterministic IDs, calendar/actionable-time rules, return calculations.

### Integration

Adapter → observation/evidence → canonical mapping using open-data or synthetic restricted-vendor fixtures.

### Regression

Protect against:

- look-ahead leakage;
- fake convergence from duplicate vendors;
- duplicate ingestion;
- ticker reuse/change;
- issuer/security/listing conflation;
- spouse/self collapse;
- transaction/public/actionable date collapse;
- partial-date parse failures;
- later-discovered relationships leaking backward;
- corporate actions breaking return calculations;
- current-universe survivorship filtering;
- silent right-censoring/missing outcomes.

### Smoke

Opt-in live-source tests. Never required for normal local/CI runs.

## 12. Definition of done for M1

M1 is complete when Ragged Claws can reproducibly answer a question like:

> For public Form 4 open-market insider transactions and selected political-household disclosures available in the source, what were the 20/60/90-day SPY-relative outcomes from the first conservative actionable session after disclosure, and how did those outcomes vary by a small predeclared feature set?

The result must:

- use only historically allowable feature information;
- retain evidence/source lineage;
- quantify unresolved/delisted/censored observations;
- avoid duplicate-vendor convergence;
- use a predeclared untouched validation period;
- be reproducible without undocumented manual intervention.

That is the first point at which Ragged Claws becomes a research system rather than a collection of ideas.
