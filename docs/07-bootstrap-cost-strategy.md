# Ragged Claws — Bootstrap Cost Strategy

**Status:** Draft v0.1  
**As of:** 2026-09-17  
**Initial investment contribution:** approximately $500/month  
**Initial infrastructure target:** approximately $30/month

## 1. Objective

Ragged Claws should be financially disciplined before it ever attempts to impose financial discipline on a portfolio.

The project will bootstrap with free public infrastructure, one inexpensive normalized-data subscription, and narrow agent-assisted enrichment.

The goal is not to minimize cost at all costs.

The goal is to spend where a dollar meaningfully increases research quality or reduces implementation friction, while avoiding expensive feeds before the strategy has demonstrated enough value to justify them.

## 2. Separate research overhead from investment capital

The initial operating assumption is:

```text
monthly investment capital:  ~$500
monthly project overhead:     ~$30 initially
```

These should be tracked separately.

The $500 is investable capital once the project reaches live validation.

The $30 is research/infrastructure expense.

Do not reduce the investment contribution by the tooling cost and then pretend the strategy's return absorbed the tooling expense. Maintain two ledgers:

### Portfolio ledger

- contributions
- positions
- realized P&L
- unrealized P&L
- total return
- SPY-equivalent return
- sector-relative return
- benchmark-relative alpha

### Research-cost ledger

- Quiver
- market-data subscriptions
- agent/browser tooling
- cloud/database costs
- legal/data-access memberships if later added
- Unusual Whales when upgraded

A third view should combine them:

> **net system value = strategy value added over benchmark − research/data costs**

## 3. V0 monthly budget

### Quiver Hobbyist — $30/month

This is the only planned recurring paid data source at bootstrap.

It earns its place because it provides both structured normalized datasets and an MCP research interface across several domains Ragged Claws already needs.

Current V0 uses include:

- congressional trades/holdings
- political profiles/net worth context
- government contracts
- corporate lobbying
- corporate donors
- Donald Trump trades
- off-exchange context
- agent/MCP access

The current plan is noncommercial, which is acceptable for personal research.

### Everything else — target $0/month initially

Use free/public access for:

- SEC / EDGAR
- USAspending
- LittleSis
- GLEIF
- OpenFIGI
- GovInfo
- FRED / ALFRED
- ICIJ Offshore Leaks
- appropriate LobbyView access
- free market-data / paper-trading tiers where sufficient

Potential usage-based or membership costs should not be activated until the relevant feature has a concrete research use.

## 4. Duct-tape layer

The bootstrap system intentionally accepts some operational friction.

### Clarence

Clarence bridges gaps where a supported API is unavailable or too expensive.

Use only for narrow, high-value enrichment.

Good Clarence task:

```text
Input:
- ticker/company
- event ID
- last capture timestamp
- exact fields requested

Action:
- inspect designated UW/company/source pages

Output:
- strict JSON/JSONL
- new records only
- source reference
- capture timestamp
- no investment opinion
```

Bad Clarence task:

```text
Go research everything interesting about this company and tell me what you think.
```

The first is an adapter. The second burns tokens and contaminates methodology with unstructured judgment.

### Firecrawl

Use the free tier only when it meaningfully reduces agent/browser overhead on web sources.

The expected role is extraction assistance, not continuous broad crawling.

### Unusual Whales public/retail access

Until premium API access is justified:

1. Ragged Claws finds candidates from deterministic/cheap sources.
2. Clarence enriches only selected candidates.
3. UW observations are stored as explicit vendor observations.
4. Material facts are verified against primary sources where practical.
5. No attempt is made to reproduce UW's full real-time commercial feed.

This is intentional duct tape.

## 5. Why not pay $150 for Unusual Whales immediately?

The API is highly attractive and likely useful.

That is not the same as being economically justified at bootstrap.

At current pricing, API Basic is roughly:

```text
$150/month
$1,800/year
```

At an initial $500/month investment contribution, premium data would dominate the economics of the experiment before we have demonstrated that the underlying strategy works.

The first job is therefore to validate the slow-signal thesis using inexpensive inputs.

## 6. UW upgrade gates

Ragged Claws should upgrade from the duct-tape UW layer to the supported full API when **any one** of the following becomes true and the expense is sustainable.

### Gate A — strategy pays for it

Benchmark-relative realized/forward-validated value has become large enough that the $150/month feed is a reasonable recurring strategy expense.

The preferred philosophical milestone is:

> **Ragged Claws earns its own data.**

### Gate B — UW-only features demonstrate incremental value

Backtesting or forward observation shows that features only available reliably through the premium UW feed materially improve:

- excess returns;
- drawdown/risk control;
- event selection;
- timeliness;
- or execution quality.

The improvement must be meaningful enough to justify the subscription, not merely statistically interesting.

### Gate C — duct tape becomes the bottleneck

Clarence/browser enrichment is consuming enough time, tokens, maintenance, or failure handling that the supported API is cheaper than continuing to improvise.

This should be measured rather than guessed.

### Gate D — account scale makes the cost immaterial

As deployed capital grows, a fixed $150/month data cost becomes less economically significant.

The system may upgrade even before direct P&L fully covers the feed if forward evidence is strong and the fee becomes small relative to invested capital and expected research value.

## 7. Cost/value accounting by source

Every paid source should have a small internal scorecard.

```text
source
monthly_cost
engineering_hours_saved
agent_tokens_saved
events_added
coverage_improvement
latency_improvement
incremental_backtest_alpha
incremental_forward_alpha
risk_reduction
renew / cancel / investigate
```

The purpose is not to reduce everything to a single number.

The purpose is to make subscription creep visible.

## 8. Quiver evaluation

Quiver is pre-approved for V0 because its $30/month cost is low enough to function as development acceleration as well as data access.

Still, it should be reviewed after the first 60–90 days.

Questions:

1. Which Quiver endpoints/MCP tools are actually used?
2. Which Quiver observations are otherwise expensive to reproduce?
3. Does Quiver materially reduce ingestion engineering?
4. Do its political/government/lobbying features add research value?
5. Are we relying on data not available under the Hobbyist plan?
6. Would the $75 Trader plan add enough value to justify itself before UW?

No subscription is permanent by default.

## 9. Free-source philosophy

"Free" does not mean "inferior."

For many Ragged Claws use cases, the primary public source is preferable because it provides:

- provenance
- legally/administratively meaningful timestamps
- longer history
- reproducibility
- lower vendor lock-in

Examples:

- SEC for insider filings
- USAspending for federal awards
- GLEIF for legal entities
- GovInfo for official federal documents
- ALFRED for historical macro vintages

Paid providers primarily earn their cost through normalization, joins, timeliness, proprietary telemetry, and engineering convenience.

## 10. Escalation ladder

The default acquisition order for a needed data capability is:

```text
1. Existing free API/bulk source
          ↓
2. Existing paid $30 Quiver capability
          ↓
3. Free RSS/webhook/MCP interface
          ↓
4. Narrow Clarence/Firecrawl enrichment
          ↓
5. Low-cost specialized provider
          ↓
6. Premium supported feed (UW, etc.)
```

Do not choose the cheapest source blindly. Choose the lowest-cost source that is sufficiently reliable for the research use.

## 11. Capital deployment remains gated separately

Data access does not justify live investment.

The live $500/month experiment begins only after:

- historical event reconstruction works;
- public timestamps are reliable;
- benchmark comparisons work;
- at least one signal family survives validation;
- forward paper observations are directionally consistent with the backtest;
- sizing and exit rules are predefined.

The infrastructure budget may begin earlier because its purpose is to build and test the research system.

## 12. Long-term target state

The desired progression is:

```text
BOOTSTRAP
$30 Quiver + public infrastructure + duct tape
        ↓
VALIDATED RESEARCH
repeatable event/graph/backtest pipeline
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
UW API replaces brittle browser enrichment
        ↓
SCALE ONLY IF EVIDENCE SURVIVES
```

The premium API is not a trophy for finishing the codebase.

It is an operating expense the strategy earns the right to carry.
