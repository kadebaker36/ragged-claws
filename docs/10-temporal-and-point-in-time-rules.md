# Temporal and Point-in-Time Rules

Issue #3 implements the temporal business-rule layer without adding ingestion, persistence,
market-data retrieval, return calculation, or trading behavior.

## Temporal axes

Ragged Claws keeps these axes separate:

- **valid/effective time**: when a fact was true in the world;
- **source-public time**: the source's publication, acceptance, or disclosure evidence;
- **effective availability**: when the system may treat that evidence as publicly usable under an
  explicit availability policy;
- **observed time**: when a collector or upstream snapshot saw the datum;
- **actionable time**: the first permitted daily-bar market entry.

Observed time, transaction time, and valid time never substitute for missing public/known time.

## Availability policy

`AvailabilityPolicy` is immutable, named, versioned, and carries an explicit non-negative delay,
rationale, and optional source-family scope. Zero delay is explicit rather than implicit. A positive
delay can be applied only to an exact timestamp; applying a duration to a date/month/year would
manufacture precision and therefore fails.

`AvailabilityResult` retains the original `TemporalValue` unchanged and records the policy plus the
separate effective timestamp or date. Exact timestamps are normalized to UTC for comparison and
serialization while `raw_value` and `source_timezone` retain source evidence.

## V0 actionable convention

The resolver uses the `XNYS` regular-session calendar from `exchange_calendars`. The library aliases
the compatible Nasdaq calendar names to this U.S. equity schedule.

1. Exact effective availability strictly before a regular-session open uses that session's open.
2. Exact availability at or after open uses the next regular session's open.
3. Date-only availability uses the next regular session after that calendar date.
4. Month, year, and unknown precision return an explicit non-actionable result.
5. Calendar failures raise; no weekday or local-time fallback invents a session.

Results retain the source-public evidence, effective availability, availability policy, calendar
package version, and actionable-convention ID/version.

## Historical eligibility

Knowledge intervals are half-open: `[known_from, known_to)`. A datum is eligible only when it has a
defensible `known_from` no later than the snapshot and the known interval has not ended. Valid-time
checks are optional and independent; an old `valid_from` cannot overcome later or missing knowledge
timing. `observed_at` is accepted for audit context but never substitutes for `known_from`.

Coarse interval bounds are conservative and compared against UTC snapshots: a coarse start becomes
usable only after its complete day/month/year, while a coarse end stops eligibility at the beginning
of its stated period. Unknown precision fails closed. `eligible_features_at` filters candidate features, and
`validate_feature_snapshot` rejects represented snapshots containing ineligible features.

## Compatibility note

Exact canonical datetime fields now normalize to UTC before serialization. Raw timezone-bearing
source evidence remains in `TemporalValue.raw_value` and `source_timezone`. The JSON Schema shape is
unchanged, and there is no persisted-data migration because persistence is deferred to issue #4.
