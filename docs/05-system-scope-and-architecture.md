# Ragged Claws — System Scope and Architecture

**Status:** Draft v0.1  
**As of:** 2026-09-17  
**Scope:** Bootstrap research architecture

## 1. Purpose

Ragged Claws is a public-information investment research system.

Its job is not to explain society, prove misconduct, or assign moral meaning to relationships. Its job is to determine whether observable behavior by economically informed, institutionally connected, or incentive-aligned actors contains durable information about future public-market returns.

The system is built around a simple chain:

```text
incentives
    ↓
behavior
    ↓
public traces
    ↓
normalized events + relationships
    ↓
point-in-time features
    ↓
forward returns
    ↓
validated investment signals
```

The objective is practical: make better investment decisions and, if the evidence supports it, make money.

## 2. V0 research mandate

The V0 system should answer:

> Given only information publicly available at time T, can observable economic behavior around a public company identify materially different forward risk-adjusted returns?

V0 is intentionally narrow enough to finish and broad enough to test the core thesis.

### In scope

- U.S.-listed public equities
- long-only research
- medium-term holding horizons
- public corporate-insider activity
- political-household financial activity
- government spending and procurement activity
- corporate lobbying activity
- documented person / organization / company relationships
- entity and security resolution
- benchmark-relative forward returns
- targeted agent-assisted enrichment
- reproducible backtesting
- forward paper observation

### Explicitly out of scope for V0

- options execution
- intraday trading
- short selling
- leverage
- automated live brokerage execution
- generalized sentiment analysis
- social-media trading signals
- election forecasting
- moral or legal scoring of people
- a generalized "corruption score"
- exhaustive mapping of every elite institution or social relationship
- machine-learning complexity before simpler models have earned it
- real-time market-microstructure strategies

These exclusions are sequencing decisions, not permanent prohibitions.

## 3. Architectural principles

### 3.1 Event-centric

The primary research object is a timestamped event.

Examples:

- officer/director open-market purchase
- spouse-owned political disclosure
- new federal award
- material increase in award obligations
- lobbying filing or spending change
- board or executive relationship change
- institutional ownership change

The research question is always: **what was publicly knowable when this event became actionable, and what happened afterward?**

### 3.2 Graph-enriched

Events do not exist in isolation. The system maintains entities and relationships so an event can be interpreted in economic context.

Examples:

```text
PERSON ──spouse_of────────► PERSON
PERSON ──director_of──────► COMPANY
PERSON ──employed_by──────► ORGANIZATION
ENTITY ──direct_parent_of─► ENTITY
HOUSEHOLD ──owns──────────► SECURITY
COMPANY ──recipient_of────► FEDERAL_AWARD
COMPANY ──lobbies_on──────► ISSUE
```

A relationship is context, not automatically a signal.

### 3.3 Company/security-centered

The system does not revolve around politicians, celebrities, or individual financiers.

The investable security is the analytical center. People, households, institutions, government activity, and capital flows are observations surrounding that security.

```text
                       people / households
                               │
                               ▼
institutions ───────────────► COMPANY ◄──────────── government
                               │
                               ▼
                           SECURITY
                               │
                               ▼
                         forward return
```

### 3.4 Point-in-time correct

The public timestamp is sacred.

A transaction that occurred on January 1 but became public on February 10 enters the historical information set on February 10.

Every event should preserve, where applicable:

- occurrence date
- transaction date
- filing date
- publication timestamp
- ingestion timestamp
- source retrieval timestamp

Historical features must be reconstructable from information available at the simulated decision time.

### 3.5 Vendor-independent internally

External providers are adapters, not architecture.

Quiver, Unusual Whales, LittleSis, SEC, USAspending, or any later source should map into Ragged Claws' canonical internal model.

Research logic should not depend directly on a vendor-specific field name or response structure.

### 3.6 Provenance-first

Every material fact should remain traceable to its source.

The system should distinguish:

1. raw source observation;
2. normalized internal record;
3. inferred relationship or feature;
4. model output;
5. portfolio decision.

No derived conclusion should silently overwrite the evidence it came from.

## 4. Four-interface rule

Ragged Claws should choose the cheapest reliable interface appropriate to each job.

### Interface A — API / bulk data

Use for deterministic ingestion, historical research, reproducible backtests, and high-volume structured data.

Preferred whenever available.

Examples:

- SEC / EDGAR
- USAspending
- LittleSis bulk/API
- GLEIF
- OpenFIGI
- ICIJ Offshore Leaks reconciliation/bulk data
- FRED / ALFRED
- LobbyView

### Interface B — RSS / webhook / event feed

Use when timeliness matters but polling the full source would be wasteful.

Examples:

- SEC filing feeds
- GovInfo RSS
- CourtListener alerts/webhooks when economically justified

### Interface C — MCP / agent-native interface

Use when the source is naturally queried through contextual research rather than bulk ETL.

Examples:

- Quiver MCP
- GovInfo MCP
- CourtListener MCP
- Alpaca MCP / agent skills

MCP is an enrichment and research interface. Durable model inputs still need to be persisted into Ragged Claws' canonical schema with provenance.

### Interface D — browser / agent fallback

Use only when the information is valuable and a reliable structured interface is unavailable or uneconomic.

Initial implementation:

- Clarence for narrow, predefined tasks
- Firecrawl or similar extraction assistance when it materially reduces browser/token overhead
- Unusual Whales free/retail surfaces for targeted enrichment until the full API is economically justified

The browser fallback should never become an invisible source of truth.

## 5. Core system layers

```text
┌───────────────────────────────────────────────────────────┐
│                    SOURCE INTERFACES                      │
│ API/Bulk | RSS/Webhook | MCP | Browser/Agent Fallback    │
└────────────────────────────┬──────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────┐
│                  RAW SOURCE / PROVENANCE                  │
│ source ID | retrieval time | raw fields | source version │
└────────────────────────────┬──────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────┐
│                CANONICAL INTERNAL MODEL                   │
│ Entities | Securities | Relationships | Events | Sources │
└────────────────────────────┬──────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────┐
│                  POINT-IN-TIME STATE                      │
│ what was knowable about company/security at time T       │
└────────────────────────────┬──────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────┐
│                     FEATURE ENGINE                        │
│ event features | network context | economic context      │
└────────────────────────────┬──────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────┐
│                       BACKTESTER                          │
│ 5d | 20d | 60d | 90d | 120d | SPY/sector comparisons   │
└────────────────────────────┬──────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────┐
│                 SIGNAL / DECISION LEDGER                  │
│ model version | score | action | reason | portfolio state│
└────────────────────────────┬──────────────────────────────┘
                             ▼
                  paper → controlled live pilot
```

## 6. Canonical domain objects

V0 should define a small number of durable objects before writing source-specific business logic.

### Entity

Represents a person, household, company, government body, fund, legal entity, nonprofit, lobbying firm, or other organization.

Minimum concepts:

- internal entity ID
- entity type
- canonical name
- aliases
- external identifiers
- active dates where known
- resolution confidence

### Security

Represents the actual investable instrument rather than a transient ticker string.

Minimum concepts:

- internal security ID
- ticker
- exchange
- FIGI where available
- issuer entity ID
- security type
- effective dates

### Relationship

Represents a sourced connection between entities.

Minimum concepts:

- source entity
- target entity
- relationship type
- effective start/end
- source
- confidence
- discovered_at
- public_as_of when knowable

### Event

Represents a timestamped observable occurrence.

Minimum concepts:

- event ID
- event type
- actor / economic unit
- company / security
- event date
- public timestamp
- value / size where applicable
- normalized attributes
- source provenance

### Feature snapshot

Represents derived information available at a particular historical decision time.

It must be immutable once used in a paper/live decision.

### Outcome

Represents forward market results from the event's actionable timestamp.

Initial horizons:

- 5 trading days
- 20 trading days
- 60 trading days
- 90 trading days
- 120 trading days

Initial comparisons:

- absolute return
- SPY-relative return
- sector-relative return
- maximum favorable excursion
- maximum adverse excursion

### Decision

Represents a paper or live investment choice.

It should preserve:

- decision timestamp
- model/version
- feature version
- signal state
- selected action
- sizing
- reason
- portfolio state

## 7. Source roles

### Primary sources

Primary sources anchor factual observations whenever practical.

Examples include SEC filings, government spending records, official disclosure records, GovInfo, and similar official datasets.

### Quiver

Quiver is the initial paid normalized alternative-data layer.

Its V0 role is to accelerate political/government/lobbying ingestion and give the project an agent-native research surface without rebuilding every parser immediately.

Quiver observations should still map to internal objects and retain source provenance.

### LittleSis

LittleSis is the foundational relationship graph.

Its initial role is entity resolution and documented relationship context, not generating an "elite score."

### Unusual Whales

Unusual Whales is the principal external reference model and the intended premium-data upgrade path.

Before full API access is justified:

- use public/available UW surfaces for reference;
- use targeted Clarence enrichment on already-interesting events;
- preserve UW classifications separately from Ragged Claws conclusions;
- do not attempt to recreate a full real-time options/dark-pool feed through scraping.

Once the premium feed is economically justified, replace browser duct tape with the supported API/MCP interfaces.

### ICIJ Offshore Leaks

ICIJ is selective network enrichment.

A match to an offshore entity, officer, intermediary, or address is a relationship observation, not a misconduct label.

It should be used where it improves entity resolution or generates a testable economic hypothesis.

## 8. Clarence's role

Clarence is a thin agentic adapter, not the analytical brain.

### Clarence should

- execute narrow source-specific collection instructions;
- operate from small durable state files;
- return strict structured records;
- preserve source URLs/identifiers and capture times;
- emit deltas rather than repeating known records;
- enrich only candidates already selected by deterministic logic where possible.

### Clarence should not

- re-read the whole project every run;
- decide whether something is a good investment;
- infer misconduct;
- manufacture missing facts;
- substitute a web page for a primary source when primary verification is practical;
- recreate an entire commercial market-data feed.

Ideal flow:

```text
free/cheap deterministic ingestion
              ↓
        candidate event
              ↓
     targeted Clarence task
              ↓
     structured enrichment
              ↓
       canonical event store
              ↓
        research / decision
```

## 9. V0 implementation sequence

### Milestone A — canonical spine

Deliver:

- entity schema
- security schema
- relationship schema
- event schema
- provenance schema
- timestamp conventions

Acceptance criterion:

A sample event from SEC, Quiver, and LittleSis can be represented without source-specific fields leaking into research logic.

### Milestone B — first live sources

Integrate:

- SEC insider events
- Quiver Hobbyist
- LittleSis
- basic market prices / benchmarks
- GLEIF/OpenFIGI resolution where useful

Acceptance criterion:

A historical event can be resolved to an issuer/security, enriched with sourced relationships, and assigned forward returns from its public timestamp.

### Milestone C — government/economic context

Integrate:

- USAspending
- lobbying data
- selected GovInfo context

Acceptance criterion:

A company event can be enriched with historical government-spending and lobbying context without look-ahead leakage.

### Milestone D — first research dataset

Produce event-level outcomes and simple stratifications.

No composite Ragged Claws score is required yet.

Acceptance criterion:

The project can answer at least one falsifiable question using an untouched validation period.

### Milestone E — targeted UW bridge

Create Clarence enrichment routines for the small set of UW fields shown to add practical context.

Acceptance criterion:

UW enrichment is reproducible, low-token, source-preserving, and only runs on selected candidates.

## 10. Architecture test

Any proposed feature should answer all of these questions:

1. What observable event or relationship does this represent?
2. What was its public timestamp?
3. What is its authoritative or best available source?
4. Can it be represented in the canonical model?
5. Could we have known it at the historical decision time?
6. Does it plausibly change expected returns?
7. Can its incremental value be tested?

If those answers are weak, the feature probably does not belong in V0.
