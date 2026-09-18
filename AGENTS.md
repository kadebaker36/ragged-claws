# AGENTS.md — Ragged Claws

## Purpose

Ragged Claws is a public-information investment research system.

The project tests whether observable behavior by economically informed, institutionally connected, or incentive-aligned actors contains durable information about future public-market returns.

The objective is empirical investment research, not political advocacy, investigative accusation, or narrative generation.

## Read before changing code

Treat these documents as authoritative, in this order:

1. `docs/05-system-scope-and-architecture.md`
2. `docs/09-adversarial-architecture-review.md`
3. `docs/08-implementation-roadmap.md`
4. `docs/06-data-source-register.md`
5. `docs/07-bootstrap-cost-strategy.md`

If `docs/09-adversarial-architecture-review.md` narrows or hardens an older draft assumption, the adversarial-review decision controls until the older document is updated.

If earlier philosophy/methodology docs are present, follow them as well.

If an issue conflicts with the architecture docs, stop and surface the conflict rather than silently changing the architecture.

## Foundational rules

### 1. Public timestamp is sacred

Never allow a model, feature, backtest, or report to use information before it became publicly available.

Keep occurrence/transaction date separate from filing/publication/actionable timestamps.

Do not fabricate timestamp precision. Preserve source date/time precision and raw values.

### 2. Observation is not inference

Store sourced facts separately from derived interpretations.

Do not label activity corrupt, illegal, suspicious, informed, or conflicted unless the source itself provides such a classification; if a vendor provides a classification, preserve it explicitly as a vendor classification.

### 3. Provenance and evidence lineage are mandatory

Every source-derived canonical record must remain traceable to its source, retrieval time, public time where known, source identifier/URL, raw-object hash, and adapter/parser version where applicable.

The same underlying event repeated by SEC, Quiver, Unusual Whales, or another provider must not be counted as multiple independent signals merely because multiple vendors observed it.

Use `SourceObservation` / evidence-link concepts described in the adversarial review.

### 4. Internal models are vendor-independent

Quiver, LittleSis, SEC, Unusual Whales, and other external providers are adapters.

Do not let source-specific response fields leak into research logic.

Map source data into canonical models first.

Vendor-derived future-return fields are never point-in-time features.

### 5. Do not guess entity mappings

Unresolved identities or securities must remain unresolved or explicitly low-confidence.

Never silently merge people, households, companies, tickers, or securities because names look similar.

Issuer, security/share class, listing, and ticker are not interchangeable concepts.

### 6. Model temporal knowledge explicitly

Where historical knowledge timing matters, distinguish:

- when a fact/relationship was valid;
- when it was publicly knowable;
- when our source or collector observed it.

A current database's historical effective date is not by itself proof that the information was available to the strategy at that historical time.

### 7. Raw data is immutable

Do not mutate or overwrite raw source snapshots. Create staging/curated derivatives.

Raw captures should be append-only and content-addressed or accompanied by hashes/manifests.

### 8. Idempotency matters

Repeated ingestion of the same source material should not create duplicate canonical records.

Do not derive canonical permanent IDs from mutable names or ticker strings.

### 9. Prefer simple research before complex scoring

Do not add a composite Ragged Claws score, ML model, graph-centrality score, or optimization layer during M0/M1 unless an issue explicitly authorizes it.

### 10. No live trading in M0/M1

Do not add code that can place real-money orders.

Paper-trading integration may be introduced only by an explicit issue after the research pipeline is validated.

### 11. No secrets or restricted payloads in Git

API keys, credentials, tokens, account identifiers, and restricted vendor data must never be committed.

Use environment variables and `.env.example` placeholders.

For commercial/restricted providers, Git fixtures should be synthetic unless redistribution is explicitly permitted.

### 12. Respect source terms

The existence of a browser agent or scraper does not authorize automated access.

Use supported APIs/MCP interfaces where available. Browser/agent fallback is allowed only where source terms permit it.

## Technical defaults

Unless an issue says otherwise:

- Python 3.12 for the bootstrap support target
- `uv`
- Pydantic v2 canonical models
- DuckDB + Parquet local analytical storage
- **Parquet is canonical persisted analytical state; DuckDB is rebuildable query/catalog/research state**
- `Decimal` for canonical financial numeric values
- `httpx`
- Typer CLI
- `exchange_calendars` (or an explicitly reviewed equivalent) for local trading-calendar semantics
- pytest
- Ruff
- one consistent static type checker

Avoid adding infrastructure dependencies without a demonstrated need.

Do not introduce Postgres, Redis, message queues, Docker orchestration, cloud services, or a web framework during M0/M1 unless explicitly approved.

M0 CI must cover Ubuntu and Windows on Python 3.12.

## Schema policy

Pydantic models under `src/ragged_claws/models/` are canonical.

JSON Schema files under `schemas/` are generated artifacts. Do not hand-edit generated schemas in a way that diverges from the canonical models.

The canonical model set includes evidence/provenance concepts needed to prevent duplicate vendor observations from becoming fake signal convergence.

Schema changes must:

- be deliberate;
- preserve or bump schema version appropriately;
- include tests;
- document migration implications when persisted data is affected.

## Source-adapter policy

Each adapter should separate:

1. retrieval;
2. immutable raw source representation;
3. source observation/evidence record;
4. normalization;
5. canonical mapping;
6. persistence.

Adapters should support recorded open-data fixtures or synthetic restricted-vendor fixtures so the default test suite does not require network access.

Live smoke tests must be opt-in.

Provider field names such as `Date`, `ReportDate`, or `ExcessReturn` must not be assigned canonical semantics without endpoint-specific documentation.

## Point-in-time actionable convention

Unless an issue explicitly defines a stronger source-specific convention:

1. precise public time before regular-session open → that session's open;
2. precise public time at/after regular-session open → next regular session's open;
3. date-only disclosure → next regular session's open after that date;
4. preserve public time/date and actionable timestamp separately.

Never use a same-day daily-bar open for information published after that open.

## Testing requirements

Every issue should add the smallest sufficient tests to prove its acceptance criteria.

Prioritize regression tests for:

- look-ahead leakage;
- duplicate source observations / fake convergence;
- duplicate ingestion;
- transaction/public/actionable date confusion;
- spouse/self household collapse;
- ticker reuse/change;
- issuer/security/listing conflation;
- later-discovered relationship leakage;
- partial/coarse date handling;
- corporate-action return errors;
- delisted/missing-security survivorship loss;
- right-censored outcomes.

A change is not complete if tests only prove the happy path while violating point-in-time, lineage, provenance, survivorship, or licensing rules.

## Research-output rules

Any generated research result should record enough metadata to reconstruct it, including where applicable:

- source snapshot dates/hashes;
- schema/model version;
- feature version;
- benchmark convention;
- price provider and adjustment mode;
- actionable-time convention;
- discovery/train period;
- untouched validation period;
- hypothesis/experiment ID.

Do not present absolute returns as evidence of alpha without appropriate benchmark comparisons.

SPY-relative return is mandatory in M1. Sector-relative return is optional until a point-in-time-safe sector mapping is available.

Reports must expose censored, unresolved, delisted, and missing-price records rather than silently dropping them.

## Agent workflow

When implementing an issue:

1. Read the issue and referenced docs.
2. Identify the smallest coherent change that satisfies it.
3. Add/modify tests first or alongside implementation.
4. Keep unrelated refactors out of scope.
5. Run the documented checks on the supported platforms where CI permits.
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
