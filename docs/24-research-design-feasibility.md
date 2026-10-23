# Research-design feasibility before confirmation

**Decision: defer confirmation; proposal, not preregistered or evaluated.**
The separate [decision card](../research/methods/feasibility-v1.json) changes no existing
hypothesis, plan, method or acceptance gate. Exactly one alternative is assessed below.
It is a prospective portfolio-accounting design, not an accepted inferential procedure.
No returns, new population counts, simulations, registrations or forward observations
were produced. This does not reject the economic hypothesis or establish funding readiness.

## 1. The existing question and the investment gap

Let P and S be unique, selected, timing-eligible purchase/sale events with complete
60-session outcomes. For each event, Y is its stock return minus its matched SPY return
under the existing entry-open/60th-following-session-close convention. Existing estimates are
`Delta = mean_P(Y) - mean_S(Y)` and `mu_P_net25 = mean_P(Y) - 25/10000`.
They are event-weighted complete-outcome associations: repeat issuers carry more weight;
vendor copies add no economic events. Unresolved, censored, missing and terminal cases
remain in the population accounting, not in a fabricated complete-return mean.

Equal stock costs cancel in Delta. A positive Delta could arise because sales do worse,
even if purchases lose to SPY. Conversely, purchases could outperform SPY without a positive
Delta. Requiring both is a different scientific claim from either alone; the proposed
conjunction still lacks accepted component inference. The existing point-mean net25 gate
does not supply an uncertainty bound for purchase performance. Fixed 25-bps costs and
zero benchmark costs are assumptions, not observed fills or an affordability assessment.

Neither mean allocates scarce capital to concurrent events, compounds wealth, earns cash
interest, pays implementation costs or resolves repeat-issuer capacity. Sales are long-stock
outcomes, not short positions or a randomized control. SPY subtraction is market adjustment,
not fitted risk-adjusted alpha; nonrandom event selection supplies no causal identification.
A realizable strategy additionally needs fixed sizing, entry/exit, issuer limits, overlap and
cashflow rules, executable identity/valuation, fees/minimum notionals and missing/terminal
treatment. The small human budget changes affordability, not statistical validity. Planned
contributions are not deposits or permission to invest.

## 2. Primary methods evidence actually read

Page numbers are one-based PDF pages, also matching the manuscript's printed numbering.
The linked full texts were accessible; only the sections listed were reread for this decision.

| Source and sections | Narrow support and limit |
| --- | --- |
| [Cameron–Miller, February 2015 author manuscript](https://faculty.econ.ucdavis.edu/faculty/cameron/research/Cameron_Miller_JHR_2015_February.pdf), introduction pp.2–3; II.F pp.11–12; VI.C.3 pp.28–29 | Cluster inference needs assumptions across clusters; whole-cluster resampling preserves within-cluster groups. Bootstrap diagnostics matter. These sections do not certify independent issuer clusters or this project's percentile rule. |
| [Kothari–Warner, May 19, 2006 manuscript](https://mba.tuck.dartmouth.edu/bespeneckbo/cfhandbook/VOLUME_1/CH1-EVENT/ECKBO-CH1-EVENT.pdf), 4.3.2 pp.29–32 and 4.4.2 pp.34–37 | Calendar portfolios change weighting and contain contemporaneous co-movement in portfolio variability. The authors also report problems for nonrandom samples. Their multi-year examples do not calibrate our 60-session setting or validate the policy below. |

No result in either paper certifies this nonrandom event population. Other papers cited
inside them were not independently read here. In particular, no new full-text claim is made
for Lyon–Barber–Tsai; the prior review read only its publisher abstract. An attempted NBER
Newey–West PDF returned 403 and an attempted Lo author PDF was inaccessible; neither is
relied on, retried through an access workaround, or used to select an estimator.

## 3. Exactly one alternative: a prospective cash-constrained purchase portfolio

This is **a different estimand in the same research family**, not a rescue or a fresh
untouched trial under a new name. The sale-arm contrast remains descriptive in the original
ledger. Consider one policy Pi, fully fixed before future return inspection, over future
unique SEC Table I purchase events under the unchanged public/actionable convention.
P/S still does not establish open-market venue. No role, size, context or return-based filter
is added. All candidates, unresolvable identities, exclusions and capacity blocks are logged.

Proposed accounting skeleton: rank same-open eligible events by public/actionable time,
then permanent Event ID; buy only with available cash and an explicit fee reserve, at most
one live exposure per issuer; a repeat event neither enlarges nor extends that holding.
Exit at the existing 60-session close. Fix an affordable ticket rule, issuer weight cap,
slot limit, terminal/failed-fill rules and cash/flow valuation convention **before use**.
Their numerical values are deliberately unresolved, not defaults or success hurdles.
They require the outcome-blind feasibility audit below. No implementable policy is frozen
by this card. There is no borrowing, short sale or compulsory full investment.

For a fixed Pi, let R_Pi,t be its daily unitized NAV return from a self-financing ledger,
including actual declared costs and idle cash. External flows issue/redeem units at a
predeclared valuation instant; deposits are not profit. Let R_B,t be a separate SPY
benchmark ledger with the same external flows, its own explicit fills/costs and valuation
convention. It is not a short position. Define `D_t = R_Pi,t - R_B,t` for every planned
regular session, including cash-only/no-event days. Target `theta_Pi = E[D_t]` under a
specified stable joint event/return/execution process; proposed null `theta_Pi <= 0`.
An arithmetic calendar mean weights days equally, not events or issuers. It is not the
original Delta, a Jensen regression intercept, causal effect or terminal wealth difference.
Report both complete wealth paths separately: compounding means a positive arithmetic
mean difference alone need not imply superior terminal wealth or acceptable risk.

The target is conditional on this source scope, policy and joint process, not all issuers
or future regimes. Concurrent holdings share shocks. Holding overlap and issuer recurrence
enter the portfolio path and can induce serial dependence; counting assets or nonoverlapping
entry groups does not remove it. Portfolio concentration, idle cash, turnover and blocked
signals must be exposed, not optimized away after outcomes. Historical identity, price,
terminal and feed/adjustment coverage remain unproven. A held security without a defensible
mark makes the affected NAV/comparison unresolved; never drop that day, insert zero, or
claim a complete target from only conveniently marked intervals. Unknown selection and
missingness need explicit identification assumptions, not a coverage percentage alone.

## 4. Why confirmation is not feasible on current evidence

Calendar accounting improves the definition of a capital-feasible question; it does not
create independent time replication. Any future mean inference needs a justified stable
target, finite moments and dependence restrictions sufficient for its stated sampling/limit
theorem and uncertainty calculation. Stationarity alone, a finite covariance estimate,
guard gap or bootstrap label is not offered as such a theorem. No variance estimator or
test is selected here, and transport beyond the observed regime needs separate support.

An exact symbolic illustration suffices: for any a>0, let one latent S be equally likely
to be -1 or +1 and persist for the entire series, with `D_t=a*S` for every t. Then
`E[D_t]=0`, `mean(D)=a*S` and `Var(mean(D))=a^2` for every T, because every pair has
covariance a^2. This strictly stationary process is not ergodic. Observing a constant +a
path is compatible with this zero-unconditional-mean model as well as an always-positive
model; more issuers or more days on that path do not reveal the unsampled state mixture.
This refutes shrinking-IID-precision reasoning, not every conceivable conservative test.
It is an algebraic dependence example, not a return simulation, market model, power
estimate or claim that real returns follow it. No executable oracle is necessary.

The current information supplies neither a complete Pi nor justified time-dependence and
coverage assumptions. Confirmation is therefore **deferred**, and the candidate does not
yet merit numerical falsification/calibration. No numerical oracle plan or execution is
authorized by this card. A synthetic pass could not establish those missing premises.
The old 30-cell issuer-only card stays archived/unapproved; do not run it to repair this
decision. The old 120/60/60 geometry and 12-episode screen remain proposals, not independent
period guarantees or an eight-year funding rule. No new count floor, power figure,
profitable sample size, alpha allocation, stopping rule or readiness date is invented here.

## 5. Single next dependency and useful prospective description

**Next dependency: a separately authorized, outcome-blind event-population/identity and
timing-capacity audit over an explicitly bounded source scope.** It should establish what
was collected versus merely absent, all unique candidate counts/statuses by day and issuer,
source/public-time precision, unresolved identity, repeat issuers, and overlapping potential
60-session holding intervals. Counts alone cannot establish dollar capacity, available
prices, dependence strength or power; report those as unknown. Do not inspect returns,
filing-price-based invented dollar sizes or broker/provider data in this order. This is a
future evidence request, not an acquisition instruction or a chosen validation window.

Before returns, review can settle the scientific question, sampling frame, ledger rules,
eligibility, costs to measure, missingness policy and how all blocked events will be retained.
Population/coverage counts require actual bounded evidence; dollar affordability requires
verified execution capabilities and valuation; uncertainty requires justified dependence
assumptions and genuinely untouched observations; paper performance requires real elapsed
time. None implies a guaranteed duration or bypasses the others.

If separately authorized later, prospective descriptive collection can test completeness,
latency and immutable decision accounting. A later frozen paper policy could record intended
and blocked decisions, cash, fills, costs and benchmark paths without claiming confirmation.
Keep descriptive development, synthetic calibration, untouched validation and real forward
observation distinct. Planning or historical replay starts no forward clock. Retain all
existing denied, failed, inspected and rejected histories; reconcile external inspections
and preserve the same family across amendments. Earlier outcomes do not become untouched
by renaming the policy. No registration, schedule, broker integration or paper run starts here.
Actual access/rights, source/price/terminal coverage, accepted methods, surviving validation,
elapsed forward evidence, durable unpublished-inspection audit and pilot gates remain unmet.
