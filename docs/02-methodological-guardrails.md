# Methodological Guardrails

Ragged Claws will fail if it tells convincing stories about historical data that could not have been acted upon in real time.

The following rules are foundational.

## 1. Public Timestamp Is Sacred

Every event must distinguish where applicable:

- underlying event date
- transaction date
- filing date
- publication timestamp
- ingestion timestamp

A strategy may not use information before it became publicly available.

If a transaction occurred January 1 but was disclosed February 10, the strategy learned about it on February 10.

Historical simulations must reflect that.

## 2. No Look-Ahead Bias

Features must be calculated only from information available at the simulated decision timestamp.

Later revisions, corrected filings, subsequently discovered relationships, and future classifications cannot be silently inserted into historical observations.

## 3. Preserve Raw Observation Separately From Derived Features

Store separately:

- source observation
- normalized representation
- derived feature
- model score
- investment decision

This allows later models to be reconstructed without rewriting history.

## 4. Preserve Provenance

Every material observation should retain:

- source
- source URL or identifier
- retrieval time
- filing/publication date
- parser/version where relevant

Derived information should remain traceable back to evidence.

## 5. Separate Fact From Inference

Examples:

FACT: A director reported an open-market purchase.

INFERENCE: The director believes the company is undervalued.

FACT: A company increased reported lobbying expenditure.

INFERENCE: The company expects favorable regulatory action.

Facts may enter the system directly.

Inferences should be explicitly labeled and tested.

## 6. Model Economic Ownership Carefully

Do not automatically equate:

- filer with purchaser
- politician with spouse
- household with adviser
- director with beneficial owner
- fund manager with fund exposure

Relationship type and attribution confidence must remain explicit.

## 7. Record Every Qualifying Signal

Do not record only events that became trades.

The research dataset must include qualifying signals that were:

- traded
- rejected
- ignored
- blocked by portfolio constraints

Otherwise the project will introduce selection bias.

## 8. Benchmark Everything

At minimum evaluate against:

- SPY or broad-market equivalent
- relevant sector benchmark

Where useful, also evaluate against:

- factor benchmarks
- equal-weight benchmarks
- volatility-adjusted benchmarks

Absolute return is not sufficient evidence of alpha.

## 9. Avoid Premature Composite Scores

Do not begin with an elaborate 20-factor scoring system merely because one can be designed.

First determine which individual variables have explanatory value.

Then test interactions.

Complexity must earn its place.

## 10. Separate Discovery From Validation

Research should use distinct periods or datasets for:

- hypothesis generation
- parameter selection
- validation
- final out-of-sample testing

Forward performance should be preserved as a separate dataset.

## 11. Version Decisions

Every live or paper decision should preserve:

- model version
- feature version
- source version
- decision timestamp
- score
- reason
- portfolio state

Do not retroactively reinterpret historical decisions using a newer model.

## 12. Do Not Force Deployment

Cash is an acceptable position.

A month with zero qualifying investments is a valid outcome.

The research system exists to identify opportunities, not create activity.

## 13. Paid Data Must Demonstrate Incremental Value

A paid dataset should be evaluated against the free-source baseline.

The relevant question is not:

“Is this data interesting?”

It is:

“Does this data materially improve prediction, execution, or research efficiency?”

Paid data that does not earn its cost should be removed.
