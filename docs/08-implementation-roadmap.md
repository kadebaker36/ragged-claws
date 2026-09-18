# Ragged Claws — Implementation Roadmap

**Status:** Draft v0.1  
**As of:** 2026-09-17  
**Scope:** Milestone 0 and Milestone 1

## 1. Objective

This document converts the project philosophy and system architecture into a build plan precise enough for Codex/agent-assisted implementation.

The first implementation goal is not a dashboard, trading bot, or composite score.

It is a trustworthy vertical slice:

```text
public event
    ↓
canonical normalization
    ↓
entity/security resolution
    ↓
public timestamp
    ↓
market outcome
    ↓
benchmark-relative research result
```

If that chain is not correct and reproducible, later graph/network features are not worth building.

## 2. Technical posture

V0 should be local-first, cheap, inspectable, and easy to replace piece by piece.

### Proposed stack

- **Language:** Python 3.12+
- **Environment/package manager:** `uv`
- **Canonical models:** Pydantic v2
- **Analytical storage:** DuckDB + Parquet
- **Dataframe layer:** Polars where useful; avoid dataframe dependence in domain models
- **HTTP:** `httpx`
- **CLI:** Typer
- **Tests:** pytest
- **Lint/format:** Ruff
- **Type checking:** mypy or pyright; choose one and enforce it consistently
- **Config:** environment variables + typed settings; no secrets in Git

### Why DuckDB + Parquet first

Ragged Claws is initially a personal research system, not a multi-user transactional application. DuckDB and Parquet provide:

- simple local setup;
- strong analytical performance;
- cheap snapshots;
- easy reproducibility;
- transparent files;
- a clean migration path to Postgres/object storage later if needed.

Do not introduce Postgres, queues, containers, orchestration, or cloud infrastructure until the research workload requires them.

## 3. Planned repository structure

```text
ragged-claws/
├── README.md
├── AGENTS.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
│
├── docs/
│   ├── 00-project-charter.md
│   ├── 01-research-philosophy.md
│   ├── 02-methodological-guardrails.md
│   ├── 03-source-and-evidence-policy.md
│   ├── 04-research-roadmap.md
│   ├── 05-system-scope-and-architecture.md
│   ├── 06-data-source-register.md
│   ├── 07-bootstrap-cost-strategy.md
│   └── 08-implementation-roadmap.md
│
├── schemas/
│   ├── README.md
│   ├── entity.schema.json
│   ├── security.schema.json
│   ├── relationship.schema.json
│   ├── event.schema.json
│   ├── provenance.schema.json
│   ├── feature-snapshot.schema.json
│   └── outcome.schema.json
│
├── src/ragged_claws/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   │
│   ├── models/
│   │   ├── entity.py
│   │   ├── security.py
│   │   ├── relationship.py
│   │   ├── event.py
│   │   ├── provenance.py
│   │   ├── feature_snapshot.py
│   │   └── outcome.py
│   │
│   ├── storage/
│   │   ├── duckdb.py
│   │   └── parquet.py
│   │
│   ├── resolution/
│   │   ├── entities.py
│   │   └── securities.py
│   │
│   ├── ingestion/
│   │   ├── base.py
│   │   ├── sec/
│   │   ├── quiver/
│   │   ├── littlesis/
│   │   └── market/
│   │
│   ├── features/
│   ├── outcomes/
│   ├── backtest/
│   └── reporting/
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

`data/` contents other than documentation should be ignored by Git. Paid/restricted raw datasets must never be committed unless licensing explicitly permits it.

## 4. Schema authority

The canonical Pydantic models in `src/ragged_claws/models/` are the source of truth.

The JSON files in `schemas/` are generated artifacts and should be reproducible from those models.

This avoids maintaining two competing schema definitions.

Every canonical model should include:

- stable internal ID;
- schema version;
- source/provenance linkage where relevant;
- temporal fields where relevant;
- explicit optionality instead of undocumented nulls.

## 5. Canonical model minimums

### 5.1 Entity

Required concepts:

- `entity_id`
- `entity_type`
- `canonical_name`
- aliases
- external IDs (`cik`, `lei`, LittleSis ID, etc.)
- valid/effective dates where known
- resolution confidence
- provenance

Initial entity types:

- person
- household
- company
- fund
- government body
- nonprofit
- legal entity
- other organization

### 5.2 Security

Required concepts:

- `security_id`
- issuer `entity_id`
- ticker
- exchange
- FIGI where available
- security type
- effective start/end dates
- provenance

Ticker must never be treated as the permanent canonical identifier.

### 5.3 Relationship

Required concepts:

- `relationship_id`
- source entity
- target entity
- relationship type
- valid start/end dates if known
- `public_as_of` if reconstructable
- source/provenance
- confidence

Initial relationship types should remain small and explicit:

- spouse_of
- household_member_of
- director_of
- officer_of
- employed_by
- owns_or_controls
- parent_of
- subsidiary_of
- adviser_to
- government_role_at
- related_to

Do not create a generalized "elite" relationship type.

### 5.4 Event

Required concepts:

- `event_id`
- `event_type`
- actor entity
- economic-unit entity where relevant
- issuer/company entity
- security ID where relevant
- event/transaction date
- public timestamp
- ingestion timestamp
- transaction/value range where relevant
- normalized attributes
- provenance

Initial event types:

- insider_open_market_purchase
- insider_open_market_sale
- political_household_purchase
- political_household_sale
- federal_award
- federal_obligation_change
- lobbying_filing
- relationship_change

M1 only needs to implement the event types required by its first sources; the enumeration may expand later through reviewed migrations.

### 5.5 Provenance

Every source-derived record must be able to answer:

- where did this come from?
- when was it retrieved?
- when did it become public?
- what source identifier/URL locates it?
- what parser/adapter version produced this representation?
- was it primary, normalized vendor data, or research/enrichment data?

### 5.6 Outcome

Required concepts:

- event ID
- security ID
- actionable timestamp
- entry timestamp/price convention
- horizon
- security return
- benchmark ID
- benchmark return
- excess return
- MFE
- MAE
- price-source provenance

## 6. Milestone 0 — Research infrastructure

### Goal

Create a repository that is safe for Codex to work in and establishes one canonical way to represent, validate, persist, and test project data.

### M0.1 Repository/bootstrap

Deliver:

- Python project scaffold
- dependency management
- `.gitignore`
- `.env.example`
- CLI entry point
- basic CI/test command documentation

Acceptance:

- `uv sync` succeeds from a clean clone;
- `uv run pytest` succeeds;
- `uv run ruff check .` succeeds;
- no secrets or local data files are tracked.

### M0.2 Canonical domain models

Deliver Pydantic models for:

- Entity
- Security
- Relationship
- Event
- Provenance
- FeatureSnapshot
- Outcome

Acceptance:

- models serialize deterministically;
- invalid timestamps/types are rejected;
- JSON Schema generation is reproducible;
- fixtures cover at least SEC, Quiver, and LittleSis-shaped examples without embedding vendor-specific keys in the canonical models.

### M0.3 Point-in-time rules

Implement shared utilities/conventions for:

- UTC normalization;
- date-only events;
- public timestamp vs occurrence date;
- `public_as_of` relationship handling;
- actionable-market-time convention.

Acceptance:

Regression tests must prove that an event cannot generate a feature snapshot containing records that became public after the snapshot timestamp.

### M0.4 Storage layer

Deliver:

- DuckDB connection/configuration;
- Parquet read/write helpers;
- canonical table/dataset layout;
- idempotent upsert/dedupe policy;
- schema-version metadata.

Acceptance:

Running the same fixture ingestion twice produces identical canonical state and no duplicate events.

### M0.5 Agent guardrails

Deliver:

- root `AGENTS.md`;
- source-adapter conventions;
- no-look-ahead requirements;
- test expectations;
- explicit prohibition on adding live-trading actions during M0/M1.

Acceptance:

A new coding agent can determine project purpose, authoritative docs, allowed architecture, required tests, and forbidden shortcuts without relying on chat history.

### Milestone 0 exit gate

M0 is complete when a fixture from any source can travel:

```text
raw fixture → adapter → canonical object → validated storage → reload
```

with provenance intact, deterministic IDs, and passing tests.

No production data ingestion is required to close M0.

## 7. Milestone 1 — First evidence pipeline

### Goal

Produce the first trustworthy event-to-return research dataset from real public data.

M1 should prove the architecture using four source families:

1. SEC insider transactions;
2. market prices/benchmarks;
3. LittleSis relationships;
4. Quiver normalized alternative data.

### M1.1 SEC Form 4 historical ingestion

Start with open-market purchases (`P`) and sales (`S`) from Forms 3/4/5 data, prioritizing Form 4.

Normalize:

- reporting owner
- issuer
- CIKs
- transaction code
- transaction date
- filing/public date
- shares
- price where available
- direct/indirect ownership
- source filing identifier

Acceptance:

- known fixture filings reproduce expected canonical events;
- `P` transactions are distinguishable from grants, exercises, gifts, tax withholding, etc.;
- transaction date and public/filing timestamp remain separate;
- reruns are idempotent;
- source document/filing is traceable.

### M1.2 Market-data adapter and outcome engine

Implement a provider-neutral market-data interface before binding research logic to one provider.

Initial provider may be Alpaca/free market data or another explicitly documented bootstrap source.

Implement:

- daily adjusted price retrieval;
- trading-calendar handling;
- next-actionable-session logic;
- SPY benchmark;
- sector-benchmark mapping interface;
- 5/20/60/90/120 trading-day outcomes.

Acceptance:

- weekend/holiday public timestamps resolve to the correct actionable session;
- split/dividend-adjusted return behavior is documented and tested;
- a hand-calculated fixture matches engine results;
- outcome rows retain price-source provenance.

### M1.3 Baseline entity/security resolution

Implement resolution in this order:

1. SEC CIK / issuer identity;
2. ticker mapping with effective dates;
3. LEI enrichment through GLEIF where useful;
4. FIGI through OpenFIGI where useful.

Acceptance:

- historical ticker reuse/change does not silently merge unrelated securities;
- unresolved mappings remain explicit rather than guessed;
- resolution confidence/provenance is retained.

### M1.4 LittleSis adapter/snapshot

Use LittleSis as graph context, not a trading signal.

Deliver:

- entity import/mapping;
- relationship import;
- source IDs/provenance;
- validity/effective dates where present;
- snapshot date metadata.

Acceptance:

- a documented person→company relationship can be traced back to LittleSis/source metadata;
- undated/current relationships cannot silently appear in historical point-in-time features;
- relationship data can be joined to a canonical company/person without overwriting primary identity records.

### M1.5 Quiver Hobbyist adapter

The Quiver adapter should normalize only the endpoints needed for V0 research.

Initial priorities:

- congressional/political trades and holdings;
- politician profiles/economic ownership fields where available;
- government contracts;
- lobbying;
- Trump/executive transactions where useful;
- political-exposure/context data where available under the plan.

Acceptance:

- vendor raw responses are retained outside canonical models;
- vendor classifications are preserved as vendor classifications;
- self/spouse/household ownership distinctions map explicitly;
- records can be cross-referenced to primary sources where Quiver supplies identifiers/links;
- no research code directly consumes Quiver response fields.

### M1.6 First vertical-slice research dataset

Produce a reproducible dataset joining:

- canonical event;
- resolved issuer/security;
- public timestamp;
- selected graph context;
- market outcomes;
- SPY-relative outcomes;
- sector-relative outcomes where mapping is available.

First research cuts should be descriptive, not optimized scoring:

- insider purchases vs sales;
- officer/director role where available;
- transaction size buckets;
- political self vs spouse/household ownership;
- disclosure lag buckets;
- simple relationship-context presence/absence.

Acceptance:

- dataset can be regenerated from source snapshots/configuration;
- no look-ahead test failures;
- every row traces to source provenance;
- train/discovery and untouched validation periods are explicitly separated;
- report contains counts, missingness, median/mean forward excess returns, and basic distribution statistics;
- no composite Ragged Claws score is introduced yet.

## 8. Initial ingestion priority

Implementation order should be:

```text
1. SEC Form 4
2. market/outcome engine
3. identity/security resolution
4. LittleSis
5. Quiver
6. first cross-source research dataset
```

This order is deliberate.

SEC + market data prove the event/timestamp/outcome spine using primary data before normalized/vendor/network context is layered in.

LittleSis and Quiver should enter M1 early enough to validate the architecture, but they should not be allowed to obscure whether the basic system is correct.

## 9. Test taxonomy

### Unit tests

Pure model, timestamp, ID, normalization, and return-calculation behavior.

### Integration tests

Adapter-to-canonical behavior using recorded/sanitized fixtures.

Network calls should not be required for the default test suite.

### Regression tests

Protect against known failure modes:

- look-ahead leakage;
- duplicate events on re-ingestion;
- ticker changes;
- spouse/self ownership collapse;
- transaction-date/public-date collapse;
- later-discovered relationships leaking backward;
- corporate actions breaking return calculations.

### Smoke tests

Opt-in tests against live APIs for adapters with credentials.

These should never be required to run the normal local/CI suite.

## 10. Data retention conventions

Suggested local layout:

```text
data/
├── raw/<source>/<snapshot-date>/
├── staging/<source>/
├── curated/
├── research/
├── snapshots/
└── cache/
```

Rules:

- raw data is immutable;
- transformations create new artifacts;
- generated research outputs record model/schema versions;
- vendor licensing controls whether raw snapshots may be retained and for how long;
- Git stores code, schemas, docs, small legal fixtures, and permitted aggregate outputs — not bulk datasets.

## 11. Definition of ready for Codex

Codex can begin implementation when:

- architecture docs are committed;
- this implementation roadmap is committed;
- root `AGENTS.md` exists;
- M0/M1 issues exist with acceptance criteria;
- technical stack is accepted;
- no unresolved architectural question blocks the canonical models.

Codex should be given one issue at a time, with review before dependent work proceeds.

## 12. Definition of done for M1

M1 is complete when Ragged Claws can reproducibly answer a question like:

> For public open-market insider purchases and selected political-household purchases, what were the 20/60/90-day SPY- and sector-relative returns from the first actionable market session after disclosure, and how did those outcomes vary by a small number of pre-declared features?

The answer must be produced without look-ahead leakage, undocumented manual intervention, or vendor-specific research logic.

That is the first point at which Ragged Claws becomes a research system rather than a collection of ideas.
