# Ragged Claws — Data Source Register

**Status:** Draft v0.1  
**As of:** 2026-09-17  
**Purpose:** Define the role, interface, cost posture, point-in-time risk, and implementation priority of external data sources.

> Prices, quotas, licensing terms, and product access can change. Re-verify vendor terms immediately before implementation or subscription changes.

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

## 2. Bootstrap source register

| Source | Tier | Primary V0 role | Interfaces | Current cost posture | Point-in-time / methodological concern | Priority |
|---|---|---|---|---|---|---|
| **SEC / EDGAR** | 1 | Form 3/4/5 insider events; filings; issuer identifiers; later 13F/fundamentals | API, filings, bulk datasets, feeds/RSS | Free | Must use filing/public timestamp, not underlying transaction date; flattened quarterly datasets are not a substitute for live filing timestamps | **V0 core** |
| **Quiver Quantitative** | 2 | Normalized political trades/holdings, government contracts, lobbying, donors, Trump trades, off-exchange context; agent-native research | REST API, MCP | **$30/mo Hobbyist** currently; noncommercial rights | Vendor normalization/classification must remain separable from our features; verify historical timestamps and licensing | **V0 paid core** |
| **LittleSis** | 3 | Entity resolution and relationship graph: people, organizations, boards, employment, family/business links | API, bulk dataset | Free; API currently requires no key | Database curation time may differ from when relationship was publicly knowable; dated relationships preferred for historical features | **V0 core** |
| **USAspending** | 1 | Federal awards, transactions, recipients, agencies, IDVs, spending trends | REST API | Free; current endpoints require no auth | Award publication/transaction timing must be distinguished from effective performance dates; recipient-to-public-company resolution is nontrivial | **V0 core** |
| **GLEIF** | 1/utility | Legal-entity resolution; LEIs; direct/ultimate corporate relationships where reported | API, bulk/golden-copy data | Free | Coverage is incomplete for entities without LEIs or reported parents; ownership relationships need effective dates | **V0 utility** |
| **OpenFIGI** | utility | Security identifier resolution and canonical mapping between tickers/identifiers | REST API | Free; unauthenticated use has lower rate limits, free keys increase throughput | Tickers change; map to stable instrument/issuer identifiers with effective dates | **V0 utility** |
| **Market-price provider / Alpaca** | 1/2 utility | Price history, benchmark returns, later paper trading | API, MCP/CLI/skills | Free entry/paper capabilities available; paid data optional later | Exchange coverage differs by plan; research must document exact feed used | **V0/V1 core utility** |
| **GovInfo** | 1 | Official bills, hearings, Congressional Record, reports, Federal Register/CFR context, presidential documents | API, RSS, bulk, **MCP public preview** | Free public access | Policy relevance is contextual; avoid converting legislative proximity into a directional trade without testing | **V1 enrichment** |
| **LobbyView** | 2/research | Historical lobbying reports, clients, bills, issues, lobbying text and relationships | REST API, datasets | Free/research-oriented; API currently rate limited | Useful for backtests; currentness and normalized client identity must be checked | **V0/V1 research** |
| **SAM.gov Opportunities** | 1 | Upstream procurement demand and contract opportunity notices | REST API | Free account/API key; quotas apply | An opportunity is not an award and does not identify the eventual winner; use as industry/demand context | **V1 research** |
| **Federal Register / Regulations.gov** | 1 | Proposed/final rules, agency notices, dockets, comments | API/web | Free public data | Regulatory events can affect whole sectors; company attribution must be explicit and timestamp-safe | **V1 research** |
| **CourtListener / RECAP** | 2/primary-adjacent | Dockets, decisions, PACER-derived material, legal alerts, court-event context | REST API, MCP, webhooks, bulk/member services | Some APIs/occasional MCP access available; advanced access/webhooks may require membership or agreement | Filing date, docket availability, and later document acquisition are different timestamps; cost/access should be verified before dependence | **V1 selective** |
| **FRED / ALFRED** | 1 | Macro/regime controls with vintage-correct historical values | API | Free key | Use ALFRED real-time periods for backtests; today's revised macro history can introduce look-ahead bias | **V1 controls** |
| **ICIJ Offshore Leaks** | 3 | Entity/officer/intermediary/address reconciliation; offshore relationship enrichment | Reconciliation API, bulk CSV/graph | Free dataset; open-data licensing with attribution/share-alike obligations | Match ≠ wrongdoing; fuzzy matches require confidence and human/primary verification before material use | **V1 selective** |
| **OpenSanctions** | 3 | PEP/entity matching, sanctions/watchlist relationships, identity enrichment | API, bulk | Bulk data free for noncommercial use; API access/licensing varies by use case | Regulatory/watchlist presence must not become a moral score; licensing matters if project ever becomes commercial | **Later/selective** |
| **Unusual Whales — public/retail surfaces** | 2 | Reference model, manual verification, targeted political/insider/market enrichment | Web platform; retail tools | Free/retail access varies | Browser extraction is brittle; preserve exact source/capture time; do not scrape at commercial-feed scale | **V0 bridge** |
| **Unusual Whales — API Basic** | 2 | Premium normalized feed: congressional/insider events, dark pool, real-time options/equities, derived indicators, MCP/skills | REST API, websocket, MCP/skills | **$150/mo currently** ($125/mo annual equivalent) | Two-year standard historical lookback may limit long backtests; market microstructure can tempt scope drift | **Upgrade target** |
| **Firecrawl** | utility | Cheap structured web extraction for narrow agent tasks | API/CLI/MCP/browser tools | Free plan currently includes 1,000 credits/mo | Extraction output is not authoritative evidence; respect source ToS and avoid replacing supported APIs with scraping | **V0 utility** |
| **Clarence** | internal agent | Low-frequency targeted enrichment and delta capture where APIs are unavailable/uneconomic | Browser/agent workflow | Token/agent cost | Must return structured records, not narrative; never silently become ground truth | **V0 bridge** |

## 3. Current verified access notes

### SEC / EDGAR

The SEC publishes flattened insider-transaction datasets derived from Forms 3, 4, and 5. The current archive spans January 2006 through June 2026 and is updated quarterly.

For current-event research, Ragged Claws should ingest filing-level data rather than waiting for quarterly flattened datasets.

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

The plan explicitly lacks commercial-use rights.

Ragged Claws V0 is personal/noncommercial research, so the limitation is acceptable for the bootstrap phase. Reassess licensing before any external productization.

### LittleSis

The API currently requires no API key or authentication, although rate limiting may apply. LittleSis also makes its full dataset available in bulk.

Treat LittleSis as graph infrastructure, not a trading recommendation engine.

### USAspending

Current USAspending API documentation states that endpoints do not require authorization.

Use deterministic endpoints for durable ingestion. Agent/LLM-style search, if used, should be an exploration aid rather than the canonical data path.

### GLEIF

GLEIF provides open access to LEI data and corporate relationship information, including direct and ultimate parent-child relationships where reported.

Use GLEIF to strengthen legal-entity resolution, not to assume complete ownership coverage.

### OpenFIGI

OpenFIGI's API is free and public. Unauthenticated requests have lower rate limits; a free API key increases throughput.

Use FIGI/security identifiers to avoid treating ticker strings as permanent identities.

### GovInfo

GovInfo's official MCP server entered public preview in January 2026. GovInfo also provides traditional API, RSS, and bulk interfaces.

This makes GovInfo a particularly good example of the four-interface strategy: deterministic retrieval for data, MCP for contextual agent research.

### FRED / ALFRED

ALFRED supports real-time periods that reconstruct what economic information was known at a historical date.

Any macro features used in a backtest should prefer vintage-correct data rather than today's revised historical series.

### ICIJ Offshore Leaks

ICIJ's Offshore Leaks database contains more than 810,000 offshore companies, foundations, and trusts and provides a reconciliation API designed for matching external entity records.

The downloadable database is graph-structured and available under open-data licensing terms.

Use cases for Ragged Claws:

- person/entity reconciliation
- officer/intermediary relationship enrichment
- ownership-network research

Non-use case:

- treating presence in the database as evidence of wrongdoing.

### CourtListener

CourtListener currently exposes REST APIs, an MCP connector, and event-driven webhook functionality. Many APIs can be explored openly; broader/advanced access is tied to Free Law Project membership/commercial arrangements.

Do not make V0 dependent on paid CourtListener features until legal-event data has demonstrated incremental value.

### Unusual Whales API

Current API Basic pricing is $150/month, or $125/month when billed annually.

The current plan advertises:

- real-time options flow
- real-time Nasdaq equities data
- congressional and insider trades
- dark-pool data
- derived market indicators
- two-year historical lookback
- 80,000 requests/day
- MCP support
- agent skills
- websocket streaming for selected feeds

This remains the intended premium-data upgrade once Ragged Claws earns it.

### Firecrawl

The current free plan advertises 1,000 credits per month.

Its V0 purpose is narrow: reduce the token and browser-navigation cost of agent enrichment. It should not become a shadow replacement for an available supported API.

## 4. Point-in-time risk classes

Each source should be tagged with a point-in-time risk class.

### PIT-A — native timestamped event

Source provides a clear historical public filing/publication timestamp.

Examples:

- SEC filing
- government award transaction
- court filing

These are preferred for direct backtesting.

### PIT-B — effective dates known, discovery time uncertain

The relationship/event has historical dates, but the current database may have learned or curated it later.

Examples:

- LittleSis relationships
- some ICIJ relationships
- manually curated network data

Use carefully in historical features.

### PIT-C — current snapshot only

Source may tell us what is true now without allowing reconstruction of what was knowable then.

Do not use directly in historical predictive models unless historical snapshots can be reconstructed.

## 5. Licensing / retention rules

1. Never commit credentials or API keys to Git.
2. Do not commit raw commercial/vendor data unless the license explicitly allows it.
3. Store source adapters, schemas, derived features, and reproducible aggregate outputs in Git.
4. Preserve source attribution required by open-data licenses.
5. Keep a machine-readable record of source license/terms version where practical.
6. Before any commercialization, re-audit every noncommercial or share-alike dependency.
7. Vendor data should be replaceable without rewriting the research engine.

## 6. Prioritization test for new sources

A new source enters the roadmap only if it improves at least one of:

- event coverage
- timestamp quality
- entity resolution
- relationship quality
- economic context
- prediction
- execution
- agent/research efficiency

And it must have a plausible path to answering:

> What incremental information does this source provide after the data we already have?

Interesting is not sufficient.
