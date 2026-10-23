# Predeclared analysis mechanics (proposal, not methodological acceptance)

Issue #10 now has a separate `analysis-plan/1.0.0` artifact and an immutable
`analysis-result/1.0.0`. Canonical domain models/schemas and research Protocol,
BuildConfig, Snapshot and Registration v1 serialization are unchanged. Existing
`research/hypotheses/sec-p-s-v1.json` is preserved. The new v2 proposal clarifies
**at least 90% complete 60-session outcomes separately in EACH arm** among selected
actionable events. This prevents coverage in one arm from masking missing outcomes
in the other. It is a pre-outcome proposal amendment, not a preregistration.

`research/analysis-plans/sec-p-s-v2.json` binds the v2 protocol hash, hypothesis/version,
validation window, feature list, source families, SPY, provider, feed and adjustment.
The format declares 60 primary, 20/90 secondary, 1000 complete events and 200 distinct
complete issuers per arm, coverage, costs, bootstrap seed/algorithm/percentiles and
missing-arm limits. Production sample gates cannot be lowered within this format.
The separately labeled invented engineering plan uses two events/two issuers per
arm to exercise mechanics, never to meet the production proposal.

## Verified inputs and exact costs

`research-evaluate` accepts only a current-environment frozen snapshot and its sealed
builder result. It verifies snapshot/graph/raw/origin hashes, every result file hash,
exact file inventory, unique economic Event ID/horizon, all ResearchRows, report,
persisted Outcomes and derived Provenance. Semantic verification reassembles through
the existing canonical builder/ForwardOutcomeEngine and compares records. A resealed
corrupt result is rejected. There is no CSV/vendor-return calculator or current ticker
filter. Synthetic provenance anywhere cannot become real support by changing mode.
Old environment snapshots remain recoverable, but cannot execute under new code.

Semantic verification also reuses the builder's `completed_coverage` precondition before
reading result rows or reassembling returns: the cutoff must be an XNYS regular session
whose close is at or before the declared as-of. Recomputed seals cannot authorize an
unfinished or future cutoff. Valid completed cutoffs retain the engine's complete and
right-censored statuses; evaluation does not rewrite them to conceal invalid timing.

Every evaluation preserves the entire original report and ResearchRows, including
all denominators, statuses/reasons, timing, features/unavailable features, identities,
listings, evidence, primary families, normalized vendor count and Outcome provenance.
The pinned snapshot contains price observations and raw dependencies. Every output
includes input snapshot/result/protocol/plan hashes, plan contents, source/lock/runtime
versions and any approval hash. No timestamp or price identity is guessed.

For complete rows only, net stock return and net SPY-excess return equal gross minus
round-trip stock bps/10000, at 10/25/50 bps. Gross stock, SPY and excess remain separate.
**SPY benchmark costs are zero** in this proposal. Incomplete outcomes retain null
gross/net values; a missing outcome never becomes zero or incurs a fabricated cost.
Sales remain long-stock event outcomes, not profitable shorts or positions.
Daily-open/close fills and constant costs are assumptions, not execution evidence.

Equal constant stock costs in both arms cancel exactly in purchase-minus-sale excess,
including every bootstrap draw and its interval. The report shares that one interval
across scenarios. Three costs are not three independent robustness tests. Purchase
mean net excess at 25 bps remains a separate strict positive condition.

## Issuer dependence and deterministic arithmetic

Use only complete selected timing-eligible primary events. Sort issuer UUIDs and group
all their events; sample G whole issuer clusters with replacement G times per draw.
A repeated draw retains all events again with multiplicity. Compute event-weighted
purchase and sale means, then subtract. Never average issuer means or resample rows
independently. Report both arms' event/issuer counts, issuer count maps and largest
issuer share. Vendor copies do not add economic events or independent clusters.

Use 5000 draws and seed 1729. Algorithm `issuer-pairs-sha256-counter/1` hashes
ASCII `ragged-claws-issuer-bootstrap/v1` followed by a zero byte, unsigned 64-bit
big-endian seed and unsigned 64-bit big-endian counter (starting at zero). Interpret
the first eight digest bytes as an unsigned big-endian integer; reject values at or
above floor(2^64/G)*G, otherwise select integer modulo G. Increment counter on every
candidate. Record SHA256 of concatenated accepted uint64 big-endian cluster indices.
This avoids dependence on Python/random or NumPy RNG versions and modulo bias.

Arithmetic uses exact rational representations of Decimal inputs for sums, means,
cost subtraction, contrast ordering, nearest ranks and decision comparisons. Export
as 50-significant-digit Decimal, ROUND_HALF_EVEN, independent of ambient context.
Percentile rank is ceil(p*n), one-based, for p=.025/.975 among valid draws. Count all
draws lacking either arm and report the fraction. More than 1% is insufficient; such
a distribution cannot support a passed conditional decision. Empty/undefined groups
and intervals are null. Tests independently enumerate small cluster samples and
exercise the same production 5000-draw path without real data or network.

## Conditional states and inspection gates

Insufficient takes priority when sample/issuer/coverage/missing-arm gates fail or
primary statistics are undefined. Preserve all insufficiency and negative reasons.
Otherwise nonpositive interval lower bound or nonpositive purchase net25 yields
negative; both strictly positive yields positive **conditional on the proposal**.
Diagnostic mode is not_evaluated. Secondary 20/90 descriptive tables cannot rescue
the primary endpoint. All outputs retain `investment_validation=not_evaluated`.
No result is a funding verdict or permission to search thresholds/windows/seeds.

Real validation builds now require both the existing matching protocol registration
and a separate `analysis-approval/1.0.0` supplied after supervisor review. Real analysis
also requires it before return inspection. It binds protocol, plan, code, lock,
origin inventory, exact snapshot bytes, deterministic result snapshot scope and the
absolute persistent registry path. Review references must address calendar dependence,
multiplicity and availability/coverage sensitivity. The input scope is approved before
building outcomes; the exact result seal hash is then recorded in each evaluation.
Reassembly prevents substituting a different favorable result within that scope.

Approval attests preserved prior journal files/hashes and reconciliation of unpublished
or external inspections. Anchored history must remain byte-identical. New journal
entries must belong to the same approved snapshot/protocol/plan; unrelated, missing,
or unfinished unscoped history requires renewed supervisor review. Started/finished
attempts use the existing append-only inspection journal so prior real inspections
still prevent renamed untouched claims. Analysis scope sidecars pin plan/result hashes.
Denials/failures are retained, and post-inspection failures conservatively cover the
entire potentially observed price interval. Outputs use deterministic IDs and write-once
bytes, so negative or insufficient results cannot be overwritten by a favorable rerun.

The shared builder marks both discovery and validation as potentially inspected before
snapshot verification or input parsing can read prices. A later verification, price-contract,
or completed-coverage failure therefore retains inspection history and prevents an overlapping
renamed/versioned validation proposal from claiming untouched status. Validation authorization
denials still occur before that boundary and remain uninspected. This hardens an existing
shared discovery boundary; the completed-coverage verifier correction did not introduce it.

These files are operator attestations, not cryptographic authorization, proof that no
external inspection occurred, or permission for a developer to self-approve.
`research-register` alone is insufficient. No real registration, acceptance or real
discovery/validation inspection was performed for this change. Rights/private-output
rules still apply. Approval supports only a reviewed persistent operator workspace
outside Git/sync/shared paths. **Ephemeral production remains inactive under #15**:
a retained local quarantine is not durable audit after an ephemeral machine disappears.

## Durability and historical compatibility decision

New analysis results belong in `research/analyses/EVALUATION_UUID` when assembling a
durable layout. The current durable generation format deliberately **does not support**
analysis artifacts or `.analysis.json` scope sidecars: exporting a layout containing
them fails, rather than dropping them. Top-level `analyses` is also rejected explicitly.
Keep all local analysis outputs and journals in persistent operator storage pending a
separately reviewed durable format/failure-audit change. Do not publish a partial
generation after omitting new analysis history. Prior frozen reports/registrations and
started/finished journals remain readable/restorable with original bytes/hashes;
normal execution still requires an exact environment match.

## Methodological limits and bounded next proposal

[Cameron and Miller (2015), sections I, III.B and VI.C](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf)
distinguish dependence within clusters from independence across clusters, describe
whole-cluster resampling, and caution about problematic bootstrap distributions and
missing replications. This supports checking dependence and resampling diagnostics;
it does not endorse this particular percentile interval or certify its coverage.

Issuer-only clustering does not settle common calendar/market shocks, overlapping
holding periods, errors, selection or multiple hypotheses. Before inspecting real
validation outcomes, a separate bounded methods review should predeclare one calendar
dependence sensitivity (calendar blocks/overlap treatment and block length justified
without validation-return optimization), one hypothesis-family/multiplicity rule, and
availability-delay and per-arm coverage/terminal sensitivity tables. Compare interval
calibration on a separate invented dependence simulation and freeze the accepted plan
and family before any real validation inspection. Do not add an unreviewed multiway
model or choose whichever method produces significance. Actual price access, coverage,
method acceptance, forward evidence and funding gates remain unmet.

## Offline commands

Use fresh persistent external paths (DEMO etc. are placeholders), Python 3.12 and the
locked environment. No keys/accounts/network are needed:

```text
uv run --frozen ragged-claws analysis-offline-demo --proposal research/hypotheses/sec-p-s-v2.json --output DEMO
uv run --frozen ragged-claws research-evaluate DEMO/positive/frozen --result DEMO/positive/research/SNAPSHOT_UUID --plan DEMO/positive/analysis-plan.json --output DEMO/positive/analyses --registry DEMO/positive/registry
```

The four cases produce positive, negative, insufficient (one arm missing) and
insufficient (no complete outcomes), always marked invented/not investment validation.
Repeated evaluation preserves identical artifact bytes and appends another attempt.
The recorded SEC diagnostic remains three unresolved events with no invented prices
or evaluated success verdict; its separate diagnostic plan must bind its actual window.
