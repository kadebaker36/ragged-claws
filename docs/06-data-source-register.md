# Ragged Claws — Data Source Register

**Status:** Draft v0.2  
**As of:** 2026-09-17  
**Purpose:** Define the role, interface, cost posture, temporal risk, licensing posture, and implementation priority of external data sources.

> Prices, quotas, licensing terms, schemas, and product access can change. Re-verify vendor terms immediately before implementation, subscription changes, or commercialization.

## 1. Source classification

Ragged Claws distinguishes three evidence roles.

### Tier 1 — Primary / authoritative

Official filings, government records, or first-party records used to anchor material facts.

### Tier 2 — Normalized / commercial or research provider

Sources that parse, normalize, enrich, or classify primary information.

These improve speed and coverage but are not automatically ground truth.

### Tier 3 — Relationship / investigative / hypothesis enrichment

Sources used to identify connections, resolve entities, discover context, or generate hypotheses.

A Tier 3 relationship does not by itself establish motive, legality, or investment value.

## 2. Temporal-quality dimensions

The previous PIT-A/B/C shorthand is not sufficient by itself. Each source/field should be evaluated on at least four separate dimensions:

1. **Event-time quality** — how precisely do we know when the underlying event occurred?
2. **Public-time quality** — how precisely do we know when the market could first have observed it?
3. **Historical reconstructability** — can we reconstruct the source state as it existed at historical time T?
4. **Lineage independence** — is this independent information or a normalized copy of another source event?

A source can be excellent on one dimension and weak on another.

Example: USAspending can provide authoritative award transaction data while still having a nontrivial delay between `action_date` and publication on the site.

## 3. Bootstrap source register

| Source | Tier | Primary V0 role | Interfaces | Current cost posture | Temporal / methodological concern | Priority |
|---|---|---|---|---|---|---|
| **SEC / EDGAR** | 1 | Form 4 insider events; filings; issuer identifiers; later 13F/fundamentals | API/files, filings, bulk datasets, feeds/RSS | Free | Preserve exact EDGAR acceptance time when available; transaction date is not public time; nightly index date is not a substitute | **V0 core** |
| **Quiver Quantitative** | 2 | Normalized political trades/holdings, government contracts, lobbying, donors, Trump trades, off-exchange context; agent-native research | REST API, MCP | **$30/mo Hobbyist** currently; noncommercial rights | Vendor dates need endpoint-specific semantics; vendor performance fields may contain future information; normalized copies are not independent convergence | **V0 paid core** |
| **LittleSis** | 3 | Entity resolution and relationship graph: people, organizations, boards, employment, family/business links | API, bulk dataset | Free; API currently requires no key; database licensed CC BY-SA 4.0 | Effective dates may predate database curation/our historical knowledge; partial dates occur; current graph cannot silently leak backward | **V0 core** |
| **USAspending** | 1 | Federal awards, transactions, recipients, agencies, IDVs, spending trends | REST API | Free; current endpoints require no auth | `action_date` is not guaranteed public date; source systems can report days/weeks later and some DOD/USACE procurement reporting can be delayed much longer | **V0 core, PIT-cautious** |
| **GLEIF** | 1/utility | Legal-entity resolution; LEIs; direct/ultimate corporate relationships where reported | API, bulk/golden-copy data | Free | Coverage incomplete; ownership relationships need effective dates and knowledge-time treatment | **V0 utility** |
| **OpenFIGI** | utility | Security identifier resolution among instrument/share-class/composite identifiers | REST API | Free; unauthenticated use has lower rate limits, free keys increase throughput | FIGI variants have different semantics; tickers change; identifier type must be preserved | **V0 utility** |
| **Market-price provider / Alpaca** | 1/2 utility | Price history, benchmark returns, later paper trading | API, MCP/CLI/skills | Free Basic/paper capabilities available; paid data optional later | Basic historical equity coverage begins in 2016; live Basic equities are IEX-only; adjustment and symbol-mapping modes must be explicit | **V0/V1 core utility** |
| **GovInfo** | 1 | Official bills, hearings, Congressional Record, reports, Federal Register/CFR context, presidential documents | API, RSS, bulk, MCP public preview | Free public access | Policy relevance is contextual; preserve document/publication timing | **V1 enrichment** |
| **LobbyView** | 2/research | Historical lobbying reports, clients, bills, issues, lobbying text and relationships | REST API, datasets | Free/research-oriented; API rate limits apply | Useful for backtests; currentness and normalized client identity must be checked; source lineage may overlap LDA/Quiver | **V0/V1 research** |
| **SAM.gov Opportunities** | 1 | Upstream procurement demand and contract opportunity notices | REST API | Free account/API key; quotas apply | Opportunity is not award and does not identify eventual winner; use as demand/industry context | **V1 research** |
| **Federal Register / Regulations.gov** | 1 | Proposed/final rules, agency notices, dockets, comments | API/web | Free public data | Sector/company attribution must be explicit and timestamp-safe | **V1 research** |
| **CourtListener / RECAP** | 2/primary-adjacent | Dockets, decisions, PACER-derived material, legal alerts, court-event context | REST API, MCP, webhooks, member/bulk services | Access tiers vary; verify before dependence | Filing date, public availability, and later document acquisition can be different times | **V1 selective** |
| **FRED / ALFRED** | 1 | Macro/regime controls with vintage-correct historical values | API | Free key | Use ALFRED real-time vintages; today's revised history can create look-ahead | **V1 controls** |
| **ICIJ Offshore Leaks** | 3 | Entity/officer/intermediary/address reconciliation; offshore relationship enrichment | Reconciliation API, bulk CSV/graph | Open data; attribution/share-alike terms apply | Match ≠ wrongdoing; fuzzy matches require confidence and verification | **V1 selective** |
| **OpenSanctions** | 3 | PEP/entity matching, sanctions/watchlist relationships, identity enrichment | API, bulk | Licensing varies by use case; verify before use | Watchlist/PEP presence is context, not moral score; commercialization/licensing matters | **Later/selective** |
| **Unusual Whales — public/retail surfaces** | 2 | Reference model, manual verification, targeted enrichment where terms allow | Web platform; retail tools | Free/retail access varies | Browser extraction is brittle and must comply with source terms; no assumption that automation is permitted | **V0 reference/bridge** |
| **Unusual Whales — API Basic** | 2 | Premium normalized feed: congressional/insider events, dark pool, real-time options/equities, derived indicators, MCP/skills | REST API, websocket, MCP/skills | **$150/mo currently** | Current Basic: two-year lookback, 40,000 requests/day; personal-use/no redistribution; market-microstructure scope drift risk | **Upgrade target** |
| **Firecrawl** | utility | Structured web extraction for narrow agent tasks where target-source terms permit it | API/CLI/MCP/browser tools | Free allowance varies; verify before use | Capability is not permission; extracted output is not authoritative evidence | **V0 utility, conditional** |
| **Clarence** | internal agent | Low-frequency targeted enrichment and delta capture where permitted | Browser/agent workflow | Token/agent cost | Must return structured records, preserve source/capture time, and never silently become ground truth | **V0 bridge** |

## 4. Current verified access notes

### SEC / EDGAR

The SEC supports scripted access subject to its published fair-access rules. The current published ceiling is 10 requests/second and automated clients should send a declared User-Agent with contact information.

For ownership filings, Ragged Claws should retain the exact EDGAR `ACCEPTANCE-DATETIME` from the complete submission header where available. SEC guidance distinguishes acceptance time from the filed-as-of date, and filings can appear on sec.gov shortly after EDGAR acceptance rather than at the nightly index time.

M1 scope should begin with Form 4, Table I, non-derivative open-market `P` and `S` transaction rows. Other ownership transaction codes can be preserved in raw/staging data and added deliberately later.

### Quiver Hobbyist

Current monthly Hobbyist pricing is $30.

The plan currently lists:

- Congress trading
- Congress stock holdings
- politician net worth
- corporate donors
- government contracts
- corporate lobbying
- off-exchange trading
- Donald Trump stock trades
- 10 of 18 Quiver MCP tools

The plan explicitly lacks commercial-use rights. The same API key is used for REST and MCP access.

Ragged Claws V0 is personal/noncommercial research, so the limitation is acceptable for the bootstrap phase. Reassess licensing before any external productization.

Important adapter rule: Quiver datasets can expose provider-derived fields such as `ExcessReturn`, `PriceChange`, and `SPYChange`. These are post-event performance fields and must never enter point-in-time feature snapshots. Quarantine them as vendor-derived metadata or discard them from canonical research features.

Do not assume an ownership-detail field such as self/spouse exists for every Quiver endpoint until the subscribed endpoint schema is verified. Preserve such distinctions when supplied; do not invent them when absent.

### LittleSis

The current API documentation states that no API key/authentication is required, although requests may be rate-limited. API responses identify the database data license as **CC BY-SA 4.0**.

LittleSis exposes entity/relationship effective dates and `updated_at`, but `updated_at` is a database curation timestamp, not necessarily the original public-knowledge time of the relationship.

LittleSis can also contain partial dates such as `1856-00-00`. Preserve source precision rather than forcing these values into a full `datetime.date`.

Treat LittleSis as graph infrastructure, not a trading recommendation engine.

### USAspending

USAspending updates after its nightly pipeline, but the upstream reporting deadline varies by source system.

For example, contract data can be submitted to FPDS within several business days of the transaction and then published downstream; DOD/USACE procurement submission can be delayed substantially longer. Financial-assistance reporting has its own lag rules.

Therefore:

- `action_date` is an event/effective date, not automatically a public timestamp;
- forward collectors should record `first_seen_at` from our own snapshots;
- historical USAspending events should not be used as exact PIT features unless a defensible publication/availability time is reconstructed.

### GLEIF

GLEIF provides open access to LEI data and corporate relationship information, including direct and ultimate parent-child relationships where reported.

Use GLEIF to strengthen legal-entity resolution, not to assume complete ownership coverage.

### OpenFIGI

OpenFIGI's API is free and public. Current documentation distinguishes instrument `figi`, `shareClassFIGI`, and `compositeFIGI` and publishes separate mapping/search rate limits.

Ragged Claws must preserve which FIGI type was returned. Do not place all three into one undifferentiated identifier field.

Use identifiers to resolve security/share-class/listing semantics; do not treat ticker strings as permanent identity.

### Alpaca market data

Current Basic equity market-data access is free and provides historical U.S. stock/ETF data **since 2016**. Live Basic equities data is IEX-only rather than the full consolidated market.

Historical bars expose explicit adjustment modes including raw, split, dividend, spin-off, and all, plus an `asof` mechanism for historical symbol/name changes.

Implications:

- if Alpaca Basic is the M1 price provider, the first backtest window is explicitly 2016-present;
- adjustment mode must be requested/documented explicitly;
- outcome and benchmark calculations must use the same convention;
- historical symbol mapping does not eliminate the need for our own stable security/listing model;
- missing/delisted coverage must be audited rather than assumed complete.

### GovInfo

GovInfo offers official API/RSS/bulk access and an MCP public preview. It is a good example of the four-interface strategy: deterministic retrieval for durable data, agentic retrieval for contextual research.

### FRED / ALFRED

ALFRED supports real-time periods that reconstruct what economic information was known at a historical date.

Any macro features used in a backtest should prefer vintage-correct data rather than today's revised historical series.

### ICIJ Offshore Leaks

ICIJ's Offshore Leaks database provides entity/officer/intermediary/address relationship data and reconciliation/bulk interfaces.

Use cases for Ragged Claws:

- person/entity reconciliation
- officer/intermediary relationship enrichment
- ownership-network research

Non-use case:

- treating presence in the database as evidence of wrongdoing.

### CourtListener

CourtListener exposes REST/agent/event-driven capabilities with access conditions that can vary by feature. Do not make V0 dependent on paid/member-only functionality until legal-event data demonstrates incremental value.

### Unusual Whales API

Current API Basic pricing is $150/month.

The current Basic plan advertises:

- real-time options flow
- real-time Nasdaq equities data
- congressional and insider trades
- dark-pool data
- derived market indicators
- two-year historical lookback
- **40,000 requests/day**
- MCP support
- agent skills
- websocket streaming for selected feeds

The API is currently described as personal-use with redistribution prohibited.

This remains the intended premium-data upgrade once Ragged Claws earns it.

### Firecrawl / browser extraction

A web-extraction tool can reduce agent overhead, but it does not override the target site's terms.

Browser/automation fallback must be evaluated source by source. When automated access is not permitted, use manual enrichment or the source's supported API/MCP interface.

## 5. Point-in-time risk patterns

### Native precise public event

The source provides a defensible public filing/publication timestamp.

Example: SEC filing acceptance timestamp.

Preferred for direct event backtesting.

### Effective date known; knowledge time uncertain

The source says when a relationship/event was effective, but current data do not establish when the market could have known the fact.

Examples:

- many LittleSis relationships;
- current curated network datasets;
- historical USAspending records when first-public availability cannot be reconstructed.

Use for context/entity resolution or apply a conservative rule; do not silently treat effective date as public date.

### Current snapshot only

The source may tell us what is true now without allowing a historical state reconstruction.

Do not use directly in historical predictive features unless historical snapshots can be reconstructed.

## 6. Source lineage and duplicate evidence

Every source observation should identify, where practical:

- provider/source;
- source-native record ID;
- underlying primary-source family;
- raw snapshot hash/version;
- public time quality;
- observed/retrieved time.

A normalized vendor observation is not automatically independent evidence.

Examples:

- SEC Form 4 + Quiver's normalization of the same Form 4 = one underlying disclosure family;
- USAspending + Quiver's normalized record of the same award = potentially one underlying procurement event;
- multiple providers can corroborate parsing without increasing convergence count.

## 7. Licensing / retention rules

1. Never commit credentials or API keys to Git.
2. Do not commit raw commercial/vendor data unless the license explicitly allows redistribution.
3. For restricted vendors, Git fixtures should be synthetic and contain invented values while preserving schema shape.
4. Store source adapters, schemas, derived features, methodology, and permitted aggregate outputs in Git.
5. Preserve attribution/share-alike obligations required by open-data licenses.
6. Keep a machine-readable record of source license/terms review date where practical.
7. Before any commercialization, re-audit every noncommercial, personal-use, or share-alike dependency.
8. Vendor data should be replaceable without rewriting the research engine.
9. Browser/scraper use is allowed only where the target source permits automated access.

## 8. Prioritization test for new sources

A new source enters the roadmap only if it improves at least one of:

- event coverage
- public-timestamp quality
- historical reconstructability
- entity resolution
- relationship quality
- economic context
- prediction
- execution
- agent/research efficiency

And it must have a plausible path to answering:

> What incremental information does this source provide after the data we already have, and is it independent of the source families we already count?

Interesting is not sufficient.
