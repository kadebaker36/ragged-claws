# Ragged Claws — Bootstrap Cost Strategy

**Status:** Draft v0.2  
**As of:** 2026-09-17  
**Initial investment contribution:** approximately $500/month  
**Initial infrastructure target:** approximately $30/month

## 1. Objective

Ragged Claws should be financially disciplined before it ever attempts to impose financial discipline on a portfolio.

Bootstrap with free public infrastructure, one inexpensive normalized-data subscription, and narrow agent-assisted enrichment.

Spend where a dollar materially improves research quality or removes engineering friction; do not buy expensive feeds merely because they are interesting.

## 2. Separate research overhead from investment capital

```text
monthly investment capital:  ~$500 after live gate
monthly project overhead:     ~$30 initially
```

Track separately.

### Portfolio ledger

- contributions
- positions
- realized/unrealized P&L
- total return
- benchmark-equivalent return
- benchmark-relative value added

### Research-cost ledger

- Quiver
- market-data subscriptions
- agent/browser tooling
- infrastructure
- data-access memberships
- Unusual Whales when upgraded

Combined view:

> **net system value = strategy value added over benchmark − research/data costs**

## 3. V0 recurring budget

### Quiver Hobbyist — $30/month

The planned bootstrap paid layer because it combines normalized politics/government/lobbying data with MCP access and meaningfully reduces ingestion engineering.

Current plan scope includes Congress trading/holdings, politician context, government contracts, lobbying, donors, off-exchange context, Trump trades, and a subset of Quiver MCP tools.

The Hobbyist plan is noncommercial. That is acceptable for personal V0 research and must be revisited before any external productization.

### Everything else — target $0/month initially

Prefer free/public access for:

- SEC / EDGAR
- USAspending
- LittleSis
- GLEIF
- OpenFIGI
- GovInfo
- FRED / ALFRED
- ICIJ Offshore Leaks
- appropriate LobbyView access
- free market-data/paper tiers where sufficient

The initial free market-data choice constrains the historical research window. If Alpaca Basic is used, M1 begins in 2016 rather than pretending the entire older SEC archive is priced by the chosen provider.

## 4. Duct-tape layer

Operational friction is acceptable. Methodological or contractual shortcuts are not.

### Clarence

Clarence bridges gaps only where the target source permits the access method being used.

Good task:

```text
Input:
- ticker/company or event ID
- last capture state
- exact requested fields
- allowed source/interface

Output:
- strict structured delta
- source reference
- capture timestamp
- no investment opinion
```

Bad task:

```text
Go research everything interesting about this company and tell me what you think.
```

Clarence is an adapter/enrichment worker, not the model.

### Firecrawl / browser tooling

Use only where it reduces agent overhead **and the target source's terms permit automated extraction**.

Technical capability is not authorization.

Do not use a scraper to bypass a provider's supported API/MCP product or access restrictions.

### Unusual Whales before premium API access

Until the supported API is economically justified:

1. Ragged Claws finds candidates from deterministic/cheap sources.
2. UW is used as a reference/enrichment surface only through interfaces allowed by its terms.
3. Vendor observations are stored explicitly as vendor evidence, not ground truth.
4. Material facts are verified against primary sources where practical.
5. No attempt is made to reproduce UW's commercial real-time feed through broad crawling.

Where automation is not permitted, the bootstrap bridge is manual/user-visible enrichment rather than a shadow scraper.

## 5. Why not pay $150 for Unusual Whales immediately?

The API is highly attractive and likely useful.

At current Basic pricing:

```text
$150/month
$1,800/year at monthly billing
```

That is too large relative to a $500/month initial contribution before the strategy has demonstrated value.

The first job is to validate the slow-signal thesis using inexpensive inputs.

## 6. UW upgrade gates

Upgrade when at least one of these becomes true and the expense is sustainable.

### Gate A — strategy pays for it

Benchmark-relative forward/live value makes the recurring feed a reasonable operating expense.

> **Ragged Claws earns its own data.**

### Gate B — UW-only variables add measurable value

Supported premium features materially improve event selection, risk, latency, execution, or benchmark-relative outcomes.

### Gate C — duct tape becomes the bottleneck

Manual/Clarence enrichment consumes enough time, tokens, failures, or maintenance that the supported API is economically cleaner.

Measure this rather than guessing.

### Gate D — account scale makes the fixed cost immaterial

As deployed capital grows, fixed data cost becomes small relative to capital and expected value.

## 7. Cost/value accounting by source

Every paid source should have a scorecard:

```text
source
monthly_cost
engineering_hours_saved
agent_tokens/time_saved
events_added
coverage_improvement
public-timestamp improvement
latency improvement
incremental backtest value
incremental forward value
risk reduction
renew / cancel / investigate
```

Subscription creep should be visible.

## 8. Quiver review

Quiver is pre-approved for V0 at $30/month because it buys development acceleration as well as data.

Review after roughly 60–90 days:

1. Which endpoints/MCP tools are actually used?
2. Which records would otherwise be expensive to normalize?
3. Does Quiver reduce engineering effort?
4. Do its politics/government/lobbying variables add predictive or contextual value?
5. Are we relying on fields absent from Hobbyist?
6. Is licensing/retention compatible with our use?
7. Would Trader add enough incremental value to justify itself before UW?

No subscription is permanent by default.

## 9. Free-source philosophy

"Free" does not mean inferior.

Primary public sources often provide the best:

- provenance
- legally/administratively meaningful timing
- long history
- reproducibility
- vendor independence

Paid providers mostly earn their cost through normalization, joins, latency, proprietary telemetry, and engineering convenience.

## 10. Acquisition ladder

```text
1. Existing free primary API/bulk source
          ↓
2. Existing $30 Quiver capability
          ↓
3. Free supported RSS/webhook/MCP interface
          ↓
4. Narrow manual/agent enrichment where terms permit
          ↓
5. Low-cost specialized provider
          ↓
6. Premium supported feed (UW, etc.)
```

Choose the lowest-cost source sufficiently reliable and legally/contractually usable for the research purpose.

## 11. Capital deployment remains gated separately

Data access does not justify live investment.

The ~$500/month live experiment begins only after:

- historical event reconstruction works;
- evidence lineage prevents duplicate-vendor convergence;
- public/actionable timing is reliable;
- benchmark/outcome construction works;
- survivorship/missing/censoring are quantified;
- at least one signal family survives predeclared validation;
- forward paper behavior is directionally consistent;
- sizing/exit rules are predefined.

## 12. Long-term target state

```text
BOOTSTRAP
$30 Quiver + public infrastructure + permitted duct tape
        ↓
VALIDATED RESEARCH
reproducible event/evidence/identity/outcome pipeline
        ↓
FORWARD EVIDENCE
paper signals behave roughly as expected
        ↓
LIVE PILOT
~$500/month long-only capital
        ↓
STRATEGY EARNS DATA
incremental value supports premium feeds
        ↓
SUPPORTED INFRASTRUCTURE
UW API replaces brittle/manual enrichment
        ↓
SCALE ONLY IF EVIDENCE SURVIVES
```

The premium API is not a trophy for finishing the codebase. It is an operating expense the strategy earns the right to carry.
