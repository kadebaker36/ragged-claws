# AGENTS.md — Ragged Claws

## Purpose

Ragged Claws is a public-information investment research system.

The project tests whether observable behavior by economically informed, institutionally connected, or incentive-aligned actors contains durable information about future public-market returns.

The objective is empirical investment research, not political advocacy, investigative accusation, or narrative generation.

## Read before changing code

Treat these documents as authoritative, in this order:

1. `docs/05-system-scope-and-architecture.md`
2. `docs/08-implementation-roadmap.md`
3. `docs/06-data-source-register.md`
4. `docs/07-bootstrap-cost-strategy.md`

If earlier philosophy/methodology docs are present, follow them as well.

If an issue conflicts with the architecture docs, stop and surface the conflict rather than silently changing the architecture.

## Foundational rules

### 1. Public timestamp is sacred

Never allow a model, feature, backtest, or report to use information before it became publicly available.

Keep occurrence/transaction date separate from filing/publication/actionable timestamps.

### 2. Observation is not inference

Store sourced facts separately from derived interpretations.

Do not label activity corrupt, illegal, suspicious, informed, or conflicted unless the source itself provides such a classification; if a vendor provides a classification, preserve it explicitly as a vendor classification.

### 3. Provenance is mandatory

Every source-derived canonical record must remain traceable to its source, retrieval time, public time where known, source identifier/URL, and adapter/parser version.

### 4. Internal models are vendor-independent

Quiver, LittleSis, SEC, Unusual Whales, and other external providers are adapters.

Do not let source-specific response fields leak into research logic.

Map source data into canonical models first.

### 5. Do not guess entity mappings

Unresolved identities or securities must remain unresolved or explicitly low-confidence.

Never silently merge people, households, companies, tickers, or securities because names look similar.

### 6. Raw data is immutable

Do not mutate raw source snapshots. Create staging/curated derivatives.

### 7. Idempotency matters

Repeated ingestion of the same source material should not create duplicate canonical records.

### 8. Prefer simple research before complex scoring

Do not add a composite Ragged Claws score, ML model, graph-centrality score, or optimization layer during M0/M1 unless an issue explicitly authorizes it.

### 9. No live trading in M0/M1

Do not add code that can place real-money orders.

Paper-trading integration may be introduced only by an explicit issue after the research pipeline is validated.

### 10. No secrets in Git

API keys, credentials, tokens, account identifiers, and restricted vendor data must never be committed.

Use environment variables and `.env.example` placeholders.

## Technical defaults

Unless an issue says otherwise:

- Python 3.12+
- `uv`
- Pydantic v2 canonical models
- DuckDB + Parquet local analytical storage
- `httpx`
- Typer CLI
- pytest
- Ruff
- one consistent static type checker

Avoid adding infrastructure dependencies without a demonstrated need.

Do not introduce Postgres, Redis, message queues, Docker orchestration, cloud services, or a web framework during M0/M1 unless explicitly approved.

## Schema policy

Pydantic models under `src/ragged_claws/models/` are canonical.

JSON Schema files under `schemas/` are generated artifacts. Do not hand-edit generated schemas in a way that diverges from the canonical models.

Schema changes must:

- be deliberate;
- preserve or bump schema version appropriately;
- include tests;
- document migration implications when persisted data is affected.

## Source-adapter policy

Each adapter should separate:

1. retrieval;
2. raw source representation;
3. normalization;
4. canonical mapping;
5. persistence.

Adapters should support recorded/sanitized fixtures so the default test suite does not require network access.

Live smoke tests must be opt-in.

## Testing requirements

Every issue should add the smallest sufficient tests to prove its acceptance criteria.

Prioritize regression tests for:

- look-ahead leakage;
- duplicate ingestion;
- transaction/public date confusion;
- spouse/self household collapse;
- ticker reuse/change;
- later-discovered relationship leakage;
- corporate-action return errors.

A change is not complete if tests only prove the happy path while violating point-in-time or provenance rules.

## Research-output rules

Any generated research result should record enough metadata to reconstruct it, including where applicable:

- source snapshot dates;
- schema/model version;
- feature version;
- benchmark convention;
- price provider;
- discovery/train period;
- untouched validation period.

Do not present absolute returns as evidence of alpha without appropriate benchmark comparisons.

## Agent workflow

When implementing an issue:

1. Read the issue and referenced docs.
2. Identify the smallest coherent change that satisfies it.
3. Add/modify tests first or alongside implementation.
4. Keep unrelated refactors out of scope.
5. Run the documented checks.
6. Summarize exactly what changed, what was tested, and any unresolved risk.

If source documentation is ambiguous, preserve raw data and fail explicitly rather than inventing semantics.

## Scope control

Interesting does not mean in scope.

The following are deferred unless explicitly requested:

- options-flow trading
- dark-pool strategies
- social-media sentiment
- broad news NLP
- generalized power/elite scores
- election predictions
- automated real-money brokerage execution
- dashboards before the underlying research data is trustworthy

The project should become more sophisticated only when evidence justifies the additional complexity.
