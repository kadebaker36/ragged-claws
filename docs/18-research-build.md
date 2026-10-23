# Offline research snapshots and protocol review

**Status:** bounded M1 engineering slice for #10; not an investment-validation result.

The builder joins frozen canonical events/evidence, explicitly reviewed identity bindings,
point-in-time features and the existing `ForwardOutcomeEngine`. It writes descriptive 20/60/90
regular-session absolute, SPY and SPY-relative outcomes. It does not implement portfolio returns,
cost sensitivity, clustered inference, capital deployment or a composite score. Issue #10 remains
open until real benchmark-priced coverage and an accepted protocol with untouched validation exist.

## Local input contract

A preparation directory contains `config.json`, `protocol.json`, `controls.json`, `prices.json`,
`origins.json` and `data/`. Typed research artifact models live in `ragged_claws.research.models`;
canonical domain models remain under `ragged_claws.models`. No canonical schema or persisted
canonical migration is introduced. Research artifact/envelope and transform versions start at
1.0.0. Incompatible future changes require a version change and a new freeze; existing files are
never upgraded in place.

`research-freeze` copies an explicit allowlist: canonical Entity, ExternalIdentifier, Security,
Listing, Relationship, Event, EventEvidence, Provenance and SourceObservation Parquet; supported
typed SEC/LittleSis/Quiver staging envelopes; referenced immutable raw bytes and matching capture
manifests; and the five configuration/input JSON files. Global Outcome/FeatureValue files, DuckDB,
caches and unrelated files are not inputs. An empty source capture or adapter rejection that has
not become a canonical Event is not a new economic event or proof of population coverage.

The snapshot records hashes of every copied file, configuration/protocol, package source,
generated canonical schemas, pyproject, uv.lock, and relevant installed runtime versions including
calendar/timezone/numeric packages. A mismatch rejects the build. Snapshot identity includes this
content and the coverage/as-of policy. The same bytes can be regenerated without reference to the
original absolute preparation path, using the same supported locked environment. This does not
promise byte-identical Parquet across different runtime versions or operating systems.

Origin inventory covers every canonical/staging record, price packet, identity binding and event
control, with its payload hash, explicit origin and review basis. Synthetic data anywhere in the
graph cannot enter real diagnostic/discovery/validation modes. Real discovery/validation also reject
unverified origins. Provider namespaces, adapter/parser metadata, raw hashes, capture manifests,
record references, price requests and feed/adjustment must agree. Origin declarations are operator
assertions, not cryptographic proof that a vendor payload or identity interpretation is authentic.
Actual source entitlement, documentation and identity review remain necessary.

Every observation must resolve to retained raw bytes and an applicable capture manifest. Credential
keys in request/query metadata are rejected without echoing their values. Unknown/restricted rights
require a reviewed raw-retention and derivative permission reference, private-only configuration,
and roots outside Git, UNC shares and known sync directories for upstream preparation, frozen data,
outputs and journal. Path checks cannot discover every shared folder; operators remain responsible
for actual storage access controls. No restricted payload, key, private setup file or local contact
belongs in Git. The examples require no account, keys or network.

## Assembly, features and denominators

Every input canonical Event produces one ResearchRow per configured horizon, including excluded,
unknown-window, non-actionable, unresolved, missing-price, censored and terminal cases. Selection
and outcome status are separate. Reports include all-input, declared-population and actionable
declared-population denominators, complete coverage fraction, every status/reason, source-family
counts, issuer concentration and primary evidence snapshot counts. Unresolved vendor rows/versions
and repeated source facts are counted separately from canonical events and known unique events.
Multiple vendor observations do not create additional primary-family votes.

The allowlist is event type, canonical reported share quantity, and positive historically eligible
relationship context. A missing/late-known/current-only relationship is unavailable, never zero or
false. Occurrence date, public time, actionable time and collector observation remain distinct.
The declared availability policy must reproduce each selected event's actionable time. No feature
can use a vendor future return or unsupported field. Share quantities stay Decimal; SEC P/S does
not establish open-market venue, currency or execution price. No USD size bucket, inferred officer
cut, sector mapping or inferred household owner is emitted. Explicit reporting and owner roles stay
separate. Feature known-time is the existing decision instant for the derived value, not a claim
of additional source timestamp precision.

Security, listing, listing history and SPY fund-share identity must be explicit and source-backed;
names and symbols do not create identities. Issuer/security/listing mismatches and unusable entry
listing intervals are rejected before censoring. The existing engine alone calculates returns and
handles historical listing changes, adjustment consistency, terminal state, missing prices and
right censoring. Coverage must be a completed XNYS session at the declared as-of time. Missing
actionability or a future entry cannot receive a fabricated Outcome. A diagnostic run never
evaluates returns, even if prices are supplied.

Each result is written under `OUTPUT/SNAPSHOT_UUID/`: research_rows.parquet, scoped canonical
Outcome/Provenance Parquet, report.json, report.md, the snapshot manifest and result file hashes.
The methodology, row, feature, derived provenance and Outcome IDs are snapshot-scoped. Maturing
coverage creates a new snapshot/methodology and leaves earlier censored outcomes intact. Frozen
inputs are read-only and output/journal overlap is forbidden. Existing different output bytes fail
explicitly. Publication is single-writer/per-file; interrupted builds may leave resumable partial
output, never permission to overwrite it. Derived provenance's deterministic audit bound is the
maximum of declared as-of and supporting observation times; actual execution time is in the journal.

Statistics use exact Decimal fractions, including mean, median, min/max, nearest-rank 10th/90th
percentiles and positive fraction. Empty groups have n=0 and null statistics. These are descriptive
gross event returns, not fills, alpha, IID inference or a passed research decision standard.

## Proposed protocol and untouched evidence

`research/hypotheses/sec-p-s-v1.json` is an **unaccepted proposal**, not a preregistration. It
declares population, features, source-public policy, primary 60-session direction, secondary
20/90-session horizons, discovery 2016–2019, an embargo year, validation 2021–2023, issuer dependence,
coverage/sample minimums, a proposed clustered confidence-interval method and cost sensitivities.
The current descriptive engine does not implement its inference/cost tests and cannot pass it.
These windows and thresholds require supervisor acceptance before any real validation inspection.
The SEC acceptance-plus-five-minutes convention is an explicit research assumption, not measured
first dissemination or a guarantee of a collector's latency.

Validation builds require a separate immutable registration matching exact protocol, package source
and origin inventory hashes. `research-register` requires an explicit supervisor approval reference
and an uninspected attestation; running it is an operator-controlled review step, not automatic
acceptance. Proposals remain visibly proposals in JSON, with a separate registration artifact.
Discovery/validation builds reject undeclared periods/features/horizons and insufficient embargo.

Build attempts append separate immutable started/finished records. Real outcome inspection is
logged before assembly, including failed calculations and the actual entry/exit span; interrupted
attempts conservatively cover the potential price interval. Denied pre-inspection builds are logged
as denied. Registration examines prior real inspections across renamed hypotheses and refuses an
overlapping validation window. Use one persistent journal across experiments and preserve it; the
software cannot prove that an operator has not inspected data elsewhere or discarded a journal.
Log external/manual inspections there before an untouched attestation. Do not reclassify negative
results or rename a hypothesis to recover an untouched claim.

## Offline examples

Run from the repository using Python 3.12 and `uv sync --frozen`. Choose new external local paths
for PREPARED, FROZEN, OUTPUT and REGISTRY (arguments below are placeholders).

```text
uv run ragged-claws research-prepare-sec tests/fixtures/sec/0000950170-24-105263.txt --metadata tests/fixtures/sec/provenance.json --protocol research/hypotheses/sec-p-s-v1.json --output PREPARED
uv run ragged-claws research-freeze PREPARED --output FROZEN
uv run ragged-claws research-build FROZEN --output OUTPUT --registry REGISTRY
```

The exact previously recorded public SEC fixture is SHA256
`5eb55738b2b6e3a2e76cb6ffcbfb6e415dbc5c7af763c9c6ced9e30e7171e732` (14,338 bytes). It contains
three sale events from one issuer. The diagnostic retains all three at all horizons, with unresolved
security/listing/benchmark/owner mappings where unsupported; prices and distributions are unavailable.
This diagnostic window is September 2024, outside the proposed discovery/validation windows. It is
not real benchmark-priced research or evidence of representative source coverage.

For a separate clearly invented engineering example:

```text
uv run ragged-claws research-prepare-synthetic --protocol research/hypotheses/sec-p-s-v1.json --output SYNTHETIC_PREPARED
uv run ragged-claws research-freeze SYNTHETIC_PREPARED --output SYNTHETIC_FROZEN
uv run ragged-claws research-build SYNTHETIC_FROZEN --output SYNTHETIC_OUTPUT --registry REGISTRY
```

That helper substitutes an explicitly synthetic protocol/source family and eleven invented events,
source observations, entities, prices and controls. It exercises all statuses, duplicate vendor
observations, separate reporting/transaction owners, a historical listing change and unavailable
context. Three complete event outcomes per horizon have known exact SPY-relative arithmetic. No
invented identity/price graph can become a real result by changing only build mode. Tests also
exercise maturation, snapshot tampering, private rights, inspection history, registration mismatch,
unsupported features, coarse/missing knowledge and output conflicts. No real registration is created
by these examples; temporary test approvals are explicitly invented.

Real Alpaca benchmark prices, applicable access/terms, historical identity/terminal coverage and
accepted protocol/inference implementation remain future gates. This slice does not close #9 or
#10 and does not establish funding readiness.
