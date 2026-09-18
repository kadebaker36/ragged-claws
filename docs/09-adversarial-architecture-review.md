# Ragged Claws — Adversarial Architecture Review

**Status:** Binding hardening supplement v0.1  
**As of:** 2026-09-17  
**Scope:** M0/M1 architecture, compatibility, integration semantics, and backtest validity

## 1. Purpose

This review attempts to break the current design before implementation begins.

The broad architecture survives: local-first Python, canonical internal models, source adapters, strict point-in-time research, DuckDB/Parquet, SEC + market data as the first evidence spine, then LittleSis and Quiver enrichment.

However, several integration details are important enough to change M0/M1 acceptance criteria. Where this document narrows or clarifies an earlier implementation assumption, this document controls until the older document is updated.

The largest risks are not package incompatibility. They are semantic:

- duplicate vendor observations masquerading as independent signal convergence;
- using an event's occurrence date as though it were its public date;
- using daily bars to simulate an entry that could not actually have been taken at the assumed price;
- current relationship or security metadata leaking backward into history;
- survivorship bias from unresolved/delisted securities;
- provider-derived future-return fields leaking into features;
- treating issuer, share class, listing, and ticker as the same object;
- unclear persistence authority between DuckDB and Parquet.

## 2. Compatibility conclusion

The proposed Python 3.12 stack is viable on Windows and Linux with current package releases.

M0 should nevertheless target **Python 3.12 explicitly**, rather than loosely relying on all future `3.12+` versions. Expand the supported interpreter matrix deliberately after CI proves it.

Required M0 CI targets:

- Ubuntu / Python 3.12
- Windows / Python 3.12

Application and test code must use portable paths and commands. Do not depend on POSIX-only shell behavior, symlinks, or the developer machine's local timezone.

Use a root `.gitattributes` to keep text line endings predictable.

## 3. Add a source-observation / evidence layer

The existing Entity / Security / Relationship / Event model is not sufficient by itself because the same real-world fact can arrive through multiple providers.

Example:

```text
SEC filing
   ├── parsed directly by Ragged Claws
   ├── normalized by Quiver
   └── normalized by Unusual Whales
```

Those are three observations of one underlying disclosure, not three independent signals.

M0 therefore adds two canonical concepts.

### SourceObservation

Represents one source-native observation.

Minimum fields:

- `source_observation_id`
- source/provider namespace
- source-native record ID or accession number
- source family / underlying primary-source family where known
- retrieval timestamp
- source publication/public timestamp where known
- raw object hash
- adapter/parser version
- source URL/locator where applicable
- license/retention classification

### EventEvidence

Links one canonical Event to one or more SourceObservations.

This preserves corroboration without double-counting duplicate feeds.

### Convergence rule

Signal convergence must be calculated over **independent underlying event families**, not over the number of vendors that repeated the same source event.

SEC + Quiver + UW copies of one Form 4 do not create three votes.

Likewise, a Quiver government-contract record derived from federal procurement data and the matching USAspending record are not automatically independent signals.

## 4. Use bitemporal semantics where knowledge timing matters

A single `public_as_of` timestamp is not enough for all relationship/entity data.

At minimum distinguish:

- **valid time** — when the relationship/fact was true in the real world;
- **known/public time** — when Ragged Claws could have known it;
- **observed time** — when our collector or source snapshot recorded it.

Recommended fields for relationships/identity claims:

- `valid_from`
- `valid_to`
- `known_from` (or `public_as_of`)
- `observed_at`

A dated LittleSis relationship may tell us that a board role began in 2018 while the current database record was curated in 2024. The 2018 effective date does **not** prove the relationship was available to our simulated strategy in 2018.

Rule: if historical public-knowledge timing cannot be established, the record may be used for current/entity-resolution context but must not silently enter a historical predictive feature snapshot.

## 5. Date and timestamp precision are first-class data

Sources do not all provide second-level UTC timestamps.

The canonical model must preserve:

- raw source timestamp/date text;
- interpreted timezone where applicable;
- precision: year / month / day / minute / second;
- normalized UTC timestamp only when the source supports that precision;
- the convention used when converting coarse source dates into an actionable time.

Do not fabricate midnight UTC and then treat it as a precise public timestamp.

LittleSis can expose partial dates such as `1856-00-00`. Source staging must preserve partial dates rather than forcing them through `datetime.date`.

A small `PartialDate` / `TemporalValue` value object is preferable to source-specific hacks scattered through adapters.

## 6. Define the actionable-market-time rule now

M1 uses daily bars. Daily bars cannot fairly simulate an entry at 10:30 a.m. after a 10:29 a.m. disclosure.

The conservative V0 convention is:

1. If a precise public timestamp is **strictly before the regular-session open**, entry is the regular-session open that day.
2. If a precise public timestamp is **at or after regular-session open**, including during or after the session, entry is the **next regular session's open**.
3. If the source provides only a disclosure **date**, entry is the next regular session's open after that date unless a source-specific, documented rule provides stronger timing evidence.
4. Preserve both `public_timestamp` (or coarse public date) and `actionable_timestamp`.
5. Never use a daily bar's same-day open for information that arrived after that open.

Use an exchange-calendar library locally rather than binding calendar semantics to the market-data vendor.

Tests must cover:

- weekends;
- U.S. market holidays;
- DST transitions;
- early closes;
- premarket publication;
- intraday publication;
- after-hours publication;
- date-only disclosures.

## 7. SEC Form 4 timing and access semantics

M1 should begin with **Form 4, Table I, non-derivative open-market P/S transactions** rather than loosely ingesting all Forms 3/4/5 transaction types at once.

Preserve the filing as a group and emit transaction-level canonical events. One filing can contain multiple owners and multiple transaction rows.

For public timing, prefer the filing's exact EDGAR **ACCEPTANCE-DATETIME** from the complete submission header when available. Do not substitute the underlying transaction date or the nightly index date.

SEC integration requirements:

- configured declared User-Agent with contact information;
- centralized throttling under SEC's published fair-access ceiling;
- retry/backoff for transient failures;
- accession number retained as source-native identity;
- `ACCEPTANCE-DATETIME` retained separately from filed-as-of date;
- source filing/complete submission traceable from each event.

## 8. Security identity needs three levels

Do not collapse issuer, security/share class, and listing into one object.

Minimum conceptual separation:

```text
Issuer Entity
   ↓ issues
Security / Share Class
   ↓ listed_as over time
Listing (exchange + symbol + effective dates)
```

OpenFIGI exposes multiple identifiers with different semantics, including instrument FIGI, share-class FIGI, and composite FIGI. Preserve the identifier type; do not store a single ambiguous `figi` field and assume it means the same thing everywhere.

Ticker is a time-varying listing attribute, not the canonical security identity.

Entity/security resolution should prefer an unresolved record to a confident false merge.

## 9. Financial values use exact numeric types

Shares, prices, transaction amounts, and disclosed ranges must not use binary floating point as their canonical representation.

Use `Decimal` in domain models and DECIMAL-compatible persisted types where practical.

For disclosed ranges, preserve:

- raw range text;
- parsed lower bound;
- parsed upper bound;
- currency;
- parsing/version metadata.

## 10. Market-data bootstrap window is 2016+

The currently planned free Alpaca Basic historical-equity coverage begins in 2016.

Therefore M1's first reproducible backtest window should be explicitly **2016-present** if Alpaca is the selected price provider.

The SEC insider archive extends earlier, but those earlier events are not automatically backtestable with the selected free market-data layer.

Longer history is a later data-provider decision, not a reason to distort M1.

## 11. Return convention must be exact

M1 must declare one reproducible outcome convention.

Recommended V0 default:

- entry: actionable regular-session open under Section 6;
- horizons: trading-session counts from entry;
- exit: close of the Nth regular trading session after entry;
- price adjustment: one documented provider adjustment convention applied consistently to both security and benchmark;
- benchmark: SPY mandatory;
- sector benchmark: optional until a point-in-time-safe sector classification exists.

Alpaca exposes raw, split, dividend, spin-off, and combined adjustments. The adapter must request the intended mode explicitly rather than relying on provider defaults.

Outcome construction may use later corporate-action knowledge to calculate historical realized return labels, but no later corporate-action information may leak into the feature state at the simulated decision time.

MFE/MAE should be implemented only after its daily-bar semantics are explicitly defined.

## 12. Sector benchmarking is not free of look-ahead

Today's sector label is not necessarily the historical sector classification.

M1 therefore makes SPY-relative return mandatory and sector-relative return conditional on a documented, time-valid mapping.

Acceptable bootstrap paths include:

- a fixed documented SIC-to-sector mapping using historically available SEC SIC values;
- another source with effective-dated classifications.

Do not quietly apply current GICS classifications backward through history.

## 13. Survivorship and delisting are mandatory audit items

A historical event should not disappear simply because its issuer later delisted, failed, merged, changed symbols, or is missing from today's asset master.

M1 must count and classify unresolved outcomes.

Minimum outcome states:

- complete;
- right-censored;
- missing price coverage;
- unresolved security;
- delisted / terminal event requiring treatment;
- excluded by an explicit predeclared rule.

A current-symbol-only backtest is not an acceptable validity baseline.

If V0 cannot reconstruct a reliable delisting return, disclose that limitation and quantify affected events rather than silently dropping them.

## 14. Source-specific point-in-time caveats

### USAspending

Award `action_date` is not automatically the date the market could observe the record.

Federal source systems can report with delays before records appear on USAspending. Forward collection should record a nightly `first_seen_at`. Historical award data should not be treated as exact PIT input unless a defensible publication/availability date is reconstructable.

### LittleSis

`updated_at` is a database curation timestamp, not proof of when the underlying relationship became public.

Effective relationship dates remain useful, but historical use is governed by the bitemporal rule in Section 4.

### Quiver

Vendor dates must be mapped by documented endpoint semantics. Do not automatically translate a field named `Date` into canonical `public_timestamp`.

Provider-derived performance fields such as `ExcessReturn`, `PriceChange`, and `SPYChange` are **post-event information** and must be quarantined from point-in-time features.

### Unusual Whales

Use supported API/MCP interfaces when available. Browser/agent extraction is permitted only where the source's terms allow automated access. The existence of Firecrawl or another scraper does not itself authorize scraping.

## 15. Licensing-safe fixture strategy

The public repository must not contain copied commercial vendor payloads unless the applicable license clearly permits redistribution.

For Quiver, Unusual Whales, and other restricted providers:

- use **synthetic fixtures** that reproduce schema shape with invented values;
- keep raw licensed captures outside Git;
- keep credentials outside Git;
- record source/license metadata and the date terms were reviewed;
- re-audit before commercialization.

Open-data attribution/share-alike requirements must also be preserved where applicable.

## 16. Persistence authority: Parquet first, DuckDB as query/catalog layer

M0 must avoid a dual-write architecture where DuckDB and Parquet can disagree.

Bootstrap convention:

- raw: immutable original source bytes/JSON/XML plus manifest/hash;
- staging: source-normalized Parquet;
- curated: canonical Parquet datasets with schema/version metadata;
- DuckDB: query/catalog/research layer that can be rebuilt from persisted Parquet.

Do not make independent authoritative writes to both DuckDB tables and Parquet datasets.

## 17. Raw snapshots are content-addressed and append-only

A directory named only by snapshot date is not enough.

Every raw capture should have a manifest containing, where available:

- source;
- retrieval timestamp;
- request parameters;
- source-native ID;
- HTTP ETag / Last-Modified;
- response/content SHA-256;
- adapter version;
- license/retention class.

Repeated downloads do not overwrite prior raw objects.

## 18. Deterministic IDs need namespace rules

Do not hash mutable names or ticker strings into permanent canonical IDs.

Recommended rules:

- source observations: deterministic ID from source namespace + stable source-native ID + version/hash where needed;
- source-native identity claims: source namespace + external ID;
- canonical entity/security/event IDs: assigned by the resolution/canonicalization layer;
- event duplicates: reconciled through evidence links rather than destructive replacement.

## 19. M0 needs a synthetic adapter

M0's exit gate requires:

```text
raw fixture → adapter → canonical object → persisted state → reload
```

No real production adapter is scheduled until M1.

Therefore M0 should include a deliberately tiny `SyntheticAdapter`/`TestAdapter` used only to prove the contract, idempotency, provenance, storage, and reload behavior.

Do not pull SEC implementation forward merely to satisfy the M0 integration test.

## 20. Quiver-specific leakage and contract guards

Quiver is still an excellent $30 V0 dependency, but the adapter must treat it as a normalized vendor, not as canonical truth.

Rules:

- raw licensed responses stay local/untracked subject to license terms;
- Git fixtures are synthetic unless redistribution is explicitly permitted;
- derived future-return/performance fields are never allowed into PIT features;
- political ownership fields such as self/spouse are preserved **if the endpoint actually supplies them**, but M1 must not invent an acceptance requirement around an undocumented field;
- Quiver MCP is an enrichment/query interface; durable model data still goes through canonical adapters;
- contract/lobbying dates are mapped only after endpoint semantics are documented.

## 21. Research validation needs a hypothesis ledger

Before the untouched validation period is evaluated, record:

- hypothesis ID;
- event population;
- feature definition;
- horizon(s);
- benchmark;
- sample filters;
- discovery period;
- validation period;
- expected direction if predeclared;
- code/config version.

Negative findings stay in the ledger.

This reduces HARKing and repeated slicing until an attractive story appears.

A simple YAML/JSON research ledger is sufficient for M1.

## 22. Right-censoring and dependence must be visible

At long horizons, recent events will not have complete outcomes.

Do not silently drop them.

Reports should show:

- qualifying event count;
- complete outcome count by horizon;
- right-censored count;
- unresolved/missing count;
- distinct issuer count;
- distinct economic-unit count where relevant.

Repeated events from one issuer are correlated observations. M1 may remain descriptive, but later inferential statistics should not pretend every event row is independent.

## 23. Updated M0/M1 blocking decisions

The following must be resolved before Codex implementation is considered complete for the relevant issue:

### M0 blockers

- SourceObservation + EventEvidence model exists.
- relationship/identity temporal semantics include valid/known/observed distinctions where relevant.
- partial/coarse date precision can be represented.
- financial values use Decimal.
- storage authority is Parquet-first; DuckDB is rebuildable query/catalog state.
- synthetic adapter proves the integration contract.
- Windows + Ubuntu CI on Python 3.12 passes.

### M1 blockers

- SEC exact acceptance timing is preserved when available.
- actionable-time convention is implemented and tested.
- security identity distinguishes issuer/security/listing semantics.
- market-data coverage window is explicit.
- survivorship/delisting/missing outcomes are audited.
- source lineage prevents duplicate vendor observations from becoming fake convergence.
- provider-derived future performance fields are excluded from PIT features.
- validation hypothesis is recorded before final validation is viewed.

## 24. Conclusion

The project does not need a different technology stack.

It needs stricter semantics at the seams.

The adversarial review therefore leaves the broad architecture intact while hardening:

```text
identity
+ time
+ evidence lineage
+ market execution assumptions
+ storage authority
+ vendor/licensing boundaries
+ validation discipline
```

Those are the places where an apparently clean alternative-data backtest is most likely to lie to us.