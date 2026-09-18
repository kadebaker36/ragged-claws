# Research Roadmap

The project should become more sophisticated only when evidence justifies additional complexity.

## Stage 0 — Foundation

Establish:

- project charter
- research philosophy
- methodological guardrails
- source policy
- internal schemas
- naming conventions
- versioning conventions

No investment logic should be considered durable until these exist.

## Stage 1 — Baseline Data Pipeline

Build ingestion for high-value free or inexpensive sources.

Initial targets:

- SEC insider transactions
- market price history
- political financial disclosures
- USAspending
- lobbying data
- FEC data

Where normalization is disproportionately expensive, evaluate inexpensive third-party APIs.

## Stage 2 — Entity Resolution

Build durable representations for:

- people
- households
- companies
- securities
- institutions
- funds
- government entities
- economic relationships

Explicitly preserve:

- relationship type
- effective dates
- confidence
- evidence source

## Stage 3 — Event Dataset

Normalize observations into timestamped events.

Examples:

- insider purchase
- household purchase
- ownership increase
- government award
- lobbying increase
- board appointment
- political disclosure
- institutional accumulation

The event dataset should be independently useful before any scoring model exists.

## Stage 4 — Baseline Backtester

For each qualifying event, calculate forward results such as:

- 5 trading days
- 20 trading days
- 60 trading days
- 90 trading days
- 120 trading days

Measure:

- absolute return
- market-relative return
- sector-relative return
- maximum adverse excursion
- maximum favorable excursion
- volatility

All simulations must begin after the information became public.

## Stage 5 — Feature Research

Test whether predictive value varies by:

- transaction size
- transaction type
- filing latency
- ownership type
- household status
- insider role
- network context
- government exposure
- lobbying activity
- institutional confirmation
- market regime
- price trend

Avoid composite scoring until individual features and interactions have been evaluated.

## Stage 6 — Convergence Research

Test whether independent signals become more informative when they occur near one another.

The primary research question becomes:

> Which combinations of observable behavior produce materially different forward return distributions?

## Stage 7 — Forward Paper Observation

Run the current model prospectively.

Record every signal as it occurs.

Do not rewrite historical scores using future model versions.

Compare forward performance against historical expectations.

## Stage 8 — Initial Live Deployment

Initial parameters:

- approximately $500/month new capital
- long-only
- shares/fractional shares
- low turnover
- no leverage
- no shorting
- no requirement to deploy all available cash

Sizing and holding periods should be established from research rather than intuition.

## Stage 9 — Paid Data Evaluation

Only after the baseline pipeline works, test whether paid datasets materially improve:

- predictive performance
- latency
- coverage
- entity resolution
- research efficiency

Initial paid baseline is expected to be Quiver Hobbyist, with Unusual Whales as the principal premium upgrade path.

Paid services should earn their continued cost.

## Stage 10 — Scale

Capital should increase only after:

- historical evidence
- out-of-sample evidence
- forward paper evidence
- live evidence

are directionally consistent.

Early profits are not sufficient justification for increasing exposure.
