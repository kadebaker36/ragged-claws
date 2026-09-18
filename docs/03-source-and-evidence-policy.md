# Source and Evidence Policy

Ragged Claws should use the strongest practical source for each class of information while preserving the ability to cross-check vendors and reproduce important findings.

## Evidence Tiers

### Tier 1 — Primary Sources

Official records and first-party filings.

Examples include:

- SEC filings
- Forms 3, 4, and 5
- 13F filings
- congressional financial disclosures
- executive-branch financial disclosures
- FEC records
- USAspending
- lobbying disclosure records
- company filings
- government procurement records

Tier 1 sources are the preferred factual anchor for material observations.

### Tier 2 — Normalized Data Providers

Third parties that collect, parse, normalize, classify, or enrich primary data.

Initial examples include:

- Unusual Whales
- Quiver Quantitative
- Capitol Trades

These sources may materially accelerate research.

Their classifications are inputs, not ground truth.

Where practical, important events should remain traceable to Tier 1 evidence.

### Tier 3 — Research and Investigative Sources

Sources useful for identifying relationships, generating hypotheses, and understanding institutional context.

Examples include:

- OpenSecrets
- LittleSis
- ProPublica
- CREW
- Sludge
- academic literature
- credible financial and investigative journalism
- ICIJ Offshore Leaks

Tier 3 sources are especially useful for discovering questions and relationships that structured financial datasets may not expose directly.

They should not automatically become trading signals.

## Operating Rule

> Tier 3 discovers questions.  
> Tier 2 accelerates analysis.  
> Tier 1 anchors material facts.

## Unusual Whales

Unusual Whales is an important external reference model for Ragged Claws because it combines political disclosures, insider activity, options data, institutional information, and other alternative-market datasets.

Ragged Claws should use Unusual Whales in three ways:

1. as a source of normalized observations where economically sensible;
2. as a benchmark for feature design and event classification;
3. as a candidate paid data layer whose incremental value can be measured.

Unusual Whales should not function as an oracle.

Where UW labels an event as unusual, conflicted, or otherwise notable, Ragged Claws should preserve that classification and independently test whether it predicts anything useful.

## Vendor Independence

The architecture should avoid making the research system dependent on any single vendor where primary or alternate sources exist.

Vendor adapters should map external data into internal schemas.

Research logic should depend on those internal schemas rather than vendor-specific response formats.

## Data Licensing

Raw vendor data should not be committed to Git unless explicitly permitted.

The repository should primarily contain:

- ingestion code
- schemas
- transformation logic
- derived features
- methodology
- reproducible research
- permitted aggregate outputs

Secrets, API keys, credentials, and restricted datasets must remain outside version control.
