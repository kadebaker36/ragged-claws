# M1 acceptance fixes — local review handoff

Date: October 22, 2026. Branch: `codex/m1-acceptance-fixes`.

Worktree: `C:/Users/kcbni/OneDrive/Desktop/Codex/ragged-claws-supervisor/integration-review`.
Base: local combined merge `a2924d5813cb64e82818045226b941e3958b20e0`, containing exact PR #16
head `892c068ee3208e8172cd2b0a8b31ea7fd9212add` and PR #17 head
`ca4965de49fa19e522c0e479081a38e33ccaeead`. Origin main remained
`0b7e392e3deb79016cf317194baeaa353806882d` when implementation began.

## Findings and evidence

1. Historical listing resolution now includes canonical Listing provenance alongside sorted unique
   claim provenance. Bare provenance creates no source observation or known/observed timestamp.
   `known_at` continues to require eligible identifier evidence. Regressions cover no-claim lineage,
   deterministic claim union, and existing late-known/coarse/reuse/ambiguity behavior.
2. Event issuer must agree with supplied Security issuer before any result status. Existing
   Event/Security/Listing checks now also precede exclusions. Ten parametrized regressions cover
   issuer-only and security-bound contradictions across complete, excluded, terminal, censored and
   missing-price paths. A consistent issuer-only event retains exact hand-calculated returns.
3. Optional `listing_history` supplies additional same-Security, same-venue canonical bindings.
   Entry Listing remains the Outcome binding; bars retain actual segment UUIDs. The engine checks
   membership, validity, overlap/conflicts, elapsed coverage gaps, session dates, adjustment, feed
   and provider. `DailyBarRequest.from_listing` clips separate requests to canonical segments;
   requests can no longer assign two symbols to one Listing UUID. The older adapter rename test
   now uses two real Listing bindings and preserves both request identities.

The integration regression resolves OLD on July 3, 2024 and NEW on July 11, retrieves invented bars
through MockTransport, computes five-session security/SPY/excess returns of exactly
`0.1` / `0.01` / `0.09`, retains both source-observation IDs and roundtrips Outcome with Entity,
Security, both Listings and price observations through authoritative Parquet. It also proves
idempotency and same-ID/different-payload conflict. Storage registrations were unchanged.
Negative cases cover ticker reuse by another Security, wrong-security bars, unknown or relabeled
Listing IDs, overlap, coverage gap, coarse boundary, conflicting binding and incompatible venue.
Missing-price and censored rename inputs remain explicit.

## Verification

Baseline external probes reproduced **3 failures, 1 pass** before fixes.
Final local Windows / Python 3.12.14 results:

- `uv sync --frozen`: passed with process-local `UV_LINK_MODE=copy`.
- `uv run --frozen pytest`: **187 passed**.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy src tests`: passed, 59 files.
- `uv run --frozen python -m ragged_claws.schema_generation --check`: 19 schemas current.
- `uv run --frozen ragged-claws version`: `0.1.0`.
- `git diff --check`: passed.

Independent probes: **4 passed** in a temporary copy at
`C:/Users/kcbni/AppData/Local/Temp/ragged-claws-acceptance-utxw8pwz/test_acceptance_edges.py`.
The sole adaptation adds `listing_history=(new,)` after `listing=old` in the rename call. All original
behavioral assertions remain intact. The equivalent supported invocation is:

```python
outcome = engine.calculate(
    event=event, horizon_sessions=5, security=security, listing=old,
    listing_history=(new,), security_bars=security_bars, benchmark_bars=benchmark_bars,
    coverage_through=date(2024, 7, 11), provenance_id=provenance_id,
)
```

The original external probe file remains unchanged at
`../review_tests/test_acceptance_edges.py`, SHA256
`3fccc1e45d4ab6c9da49193d0ef9d5ca21ae40c09faf9eb3a85a1e3ae9eb7432`.
Its original rename call omits the NEW binding and must now fail explicitly for missing canonical
coverage; UUIDs in bars alone cannot supply a defensible validity interval.

## Compatibility, limits and proposed disposition

No canonical model/schema or persisted-data migration. Outcome ID convention remains unchanged.
Existing single-listing calls remain usable. Multi-symbol request callers must issue one request
per Listing; renamed series must explicitly supply the canonical history. Same-ID/different-payload
storage remains a hard conflict; deliberate methodology/research versioning is required when
recomputing changed labels. Docs 13/14 describe the updated contracts.

This is daily, same-Security, same-venue rename support. Precise intraday/coarse boundaries, venue
transfers, general corporate actions and terminal-return reconstruction remain unsupported. Missing
listing coverage raises an auditable input error; callers must retain/count that error rather than
drop the event. No live providers, credentials, SEC/R2 work, push, remote PR update or merge occurred.
Hosted Ubuntu/Windows CI for the original heads does not validate these corrections; new hosted CI
remains required before merge.

Proposed disposition: hold original PRs #16/#17 pending supervisor review of this combined branch.
After review, publish a combined successor PR and run its Ubuntu/Windows CI; only then consider
superseding the original PRs and merging. This avoids accepting the uncorrected heads independently.
The original branches/worktrees and remote PR state remain untouched by this assignment.
