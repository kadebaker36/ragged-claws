# Dependence audit and proposed validation design

**Status: proposal; no registration, real outcomes, calibration or production estimator.**
The machine-readable declaration is [design-v1.json](../research/methods/design-v1.json).
Existing hypotheses v1/v2, production AnalysisPlan and all canonical/artifact models stay unchanged.

## Decision

Issuer-only analysis may remain descriptive. It cannot currently support an accepted significance
claim. A single shared residual state can defeat its interval even with 200 issuers and 1000 events
per arm. The one calendar sensitivity below is a descriptive veto, not a replacement confidence
interval. The 2021–2023 proposal is **insufficient under that sensitivity's period screen** before
any return is viewed. A different design needs independent review and genuinely untouched evidence;
neither more code nor silent extension of the historical window supplies that evidence.

## What is being estimated

For complete, selected, timing-eligible 60-session events, let `Y` be the existing engine's stock
return minus SPY return. The observed statistic is the event-weighted purchase mean minus the
event-weighted sale mean. Issuers with more economic events contribute more weight; vendor copies
do not create more events. This complete-outcome association is conditional on resolution and price
coverage. It does not identify the mean for unresolved/missing events without extra assumptions.

Subtracting SPY does not fit factor exposures or establish risk-adjusted alpha. Event rows need
not correspond to feasible capital allocations, independent positions or rebalancing; sale rows
are long-stock outcomes. Neither the contrast nor an episode average is an investable portfolio
return or a causal effect of the reported behavior. Disclosure/participation/issuer selection is
nonrandom. Timing, risk exposure and omitted variables can generate an association.

Whole-issuer resampling retains repeated-event dependence within an issuer. It needs sufficiently
independent, representative clusters and a usable sampling approximation, with no dominant clusters
or pathological missing arms. Those assumptions are unverified here. Shared market/sector shocks,
partially overlapping holding windows, persistent regimes, repeated issuers across dates and arm
concentration can connect many issuers. More issuers cannot manufacture independent time episodes.
Report event and issuer concentration in each arm alongside calendar coverage; no count threshold
proves independence or removes selection bias.

## Primary sources actually reviewed

Page references below use one-based PDF pages, not journal pagination.

- **Cameron–Miller (2015), February author PDF:** introduction pp.1–2, section **II.F** pp.11–12,
  and VI.C.3 pp.28–29. These describe across-cluster assumptions, whole-cluster resampling and
  cautions about degenerate/missing bootstrap values. They do not certify this event-weighted
  percentile interval. II.F, rather than the III.B reference in earlier project prose, is the
  pairs-bootstrap section. The original author hostname timed out in this audit; the same named
  [PDF on the author's faculty hostname](https://faculty.econ.ucdavis.edu/faculty/cameron/research/Cameron_Miller_JHR_2015_February.pdf)
  was read. No secondary summary is substituted.
- **Kothari–Warner (May 19, 2006),** sections 4.3.2 pp.29–32 and 4.4.2 pp.34–39 discuss
  weighting differences, cross-correlation, overlapping return supports and specification limits.
  Their multi-year examples are not numerical calibration for this 60-session endpoint. Their
  discussion also cautions about calendar-time methods in nonrandom samples; changing to such
  portfolios changes weighting and does not automatically solve this problem.
  [Full chapter reviewed](https://mba.tuck.dartmouth.edu/bespeneckbo/cfhandbook/VOLUME_1/CH1-EVENT/ECKBO-CH1-EVENT.pdf).
- **Lyon–Barber–Tsai (1999), Journal of Finance 54(1), pp.165–201:** only the publisher's
  **abstract**, not the article's full text, was reviewed. It distinguishes random-sample
  performance from pervasive nonrandom-sample misspecification.
  [Publisher abstract](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00101).

These are narrow methodological cautions, not a universal correction or an endorsement of this card.

## Declared common-shock counterexample

This construction and the card must be committed before numerical execution. No market prices,
ResearchRows, registrations or actual investment evaluations are inputs. There are 200 issuers,
five events per arm per issuer, and one common equiprobable state `S=-1,+1`. Each purchase excess
is `b+S*h`, each sale excess `b-S*h`, with `b=.01`, `h=.02`. The unconditional contrast is zero.
There is one calendar episode; issuer counts meet the existing proposal while the calendar screen
is insufficient in both states.

Analytic proof: any whole-issuer draw has the same arm means, however often issuers are repeated.
Thus all 5000 contrasts and both nearest-rank interval endpoints equal `2*S*h`: -.04 or +.04.
Purchase net25 is -.0125 or +.0275. Equal 10/25/50-bps stock costs cancel from the contrast.
Under the existing descriptive proposal's conditions, one state is negative and one misleadingly
conditional positive. Exact enumeration gives positive-declaration probability 1/2 and interval
coverage of the unconditional zero contrast 0. These are properties of this declared null, not
Monte Carlo rejection-rate estimates or the actual system's false-positive rate.

Use the unchanged production bootstrap algorithm, 5000 draws, seed1729 and exact arithmetic.
Record both states, every missing/degenerate diagnostic, and the insufficient calendar status.
The mechanism is cross-issuer dependence, not a two-issuer small-sample problem. No shock/seed/
threshold optimization is permitted. A mathematical failure of an uncertainty calculation says
nothing about whether the economic hypothesis succeeds or fails in actual markets.

## Exactly one calendar/overlap sensitivity

**Guarded paired-episode veto:** anchor at the first XNYS session on/after the declared validation
start. Each cycle has a 120-session episode and a 60-session guard gap. Admit entries only in
the first 60 episode sessions, so every 60-session exit is inside its episode. Include all issuers
and both arms together. Do not wrap, move spills into another episode or use a partial final one.
Keep every omitted/boundary/guard event and its original primary status visible.

Hand-worked one-based boundaries: episode1 is sessions1–120; entries1–60 exit61–120.
Entry60→exit120 is admitted; entry61→121 is excluded from this sensitivity. Entry180 is in
the guard; entry181 starts episode2 and exits241. Episode2 spans181–300: if observation stops
at250, it is a partial episode, even though a few individual outcomes have matured.

Each full episode must have both arms, >=20 complete events and >=10 complete issuers per arm,
and >=90% complete/actionable coverage per arm. Require at least12 usable paired episodes;
any full planned empty/one-arm/inadequate episode makes the sensitivity insufficient, rather
than being dropped. Floors and lengths are conservative operational proposals, not calibrated
independence guarantees. Empty means remain undefined. Within an episode, use event-weighted
arm means; then equally weight episode contrasts and purchase-net25 means. Nonpositive means
veto a positive robustness interpretation. A positive sensitivity is not inferential acceptance.

This restricted-entry, equal-episode estimand differs from the full event-weighted contrast.
The extra 60-session gap removes mechanical cross-episode horizon overlap, not persistent common
shocks. Issuers may recur across episodes; issuer maps/concentration remain necessary. Separate
issuer and calendar passes are not valid multiway inference. Even12 episodes do not prove
independence. A simple block bootstrap is therefore not proposed as a complete two-dimensional fix.

Three years have fewer than840 regular sessions even using a weekday upper bound, hence at most
four full episodes with this geometry. Twelve require `11*180+120=2100` sessions. The current
window fails the screen independently of outcomes. More future elapsed observations or a different
independently justified design are separate decisions; do not reuse inspected discovery history.

## Family, timing and missingness policy

The proposed primary family is a conjunction: `Delta60>0 AND purchase-net25>0`, with composite
null `Delta60<=0 OR purchase-net25<=0`. Proposed family alpha is **one-sided .025**. Require both
valid one-sided97.5% lower bounds >0. Under either component null, joint rejection is a subset of
rejecting that true component, so an intersection-union rule preserves its level without assuming
independence. The current purchase point-mean gate alone is not this component test. A two-sided
95% percentile lower bound >0 is not automatically a one-sided5% test, or even correctly calibrated.
No accepted component inference is supplied here: formal inference remains not_evaluated.

The card makes20/90 horizons, feature/role/size/lag/context cuts and cost scenarios descriptive.
It fixes a pre-inspection `.025/K` family budget if a separately reviewed K-family design is
ever authorized; K=1 here. No alpha recycling, favorable endpoint substitution or renamed fresh
trial. Keep denied/failed/negative/external inspections. Post-inspection amendments require a
separate version and genuinely untouched evidence; this card is not a preregistration.

Availability baseline remains SEC acceptance+5min as an assumption. The single stronger sensitivity
moves baseline actionable entry one additional XNYS session forward, using the existing resolver/
engine later. Preserve source timestamps, precision, baseline entry and source-event selection;
report shifted maturity/censoring and episode-boundary changes. This does not measure dissemination
or prove historical latency bounds. Unknown timing remains unknown.

Report each arm's total/selected/actionable/unknown/nonactionable and all outcome statuses/reasons.
The declared missingness sensitivity shifts the hypothetical unavailable purchase-group mean down
.10 and sale-group mean up .10; report sign tipping points too. It is an aggregate scenario,
not invented prices, terminal returns or canonical-row imputation. Ninety percent coverage does
not remove selection bias. Without restrictions on missing returns, full-population bounds may
be uninformative/unbounded. The card specifies denominators, formulas and insufficient/veto states.

## Later calibration and next dependency

The card predeclares one falsification baseline, not a method tournament: the existing issuer
draws, with joint contrast/purchase lower bounds and this descriptive veto. It fixes five
dependence structures, two null frontiers and one signal alternative, 200 issuers/1000 events per
arm, B=4/12, 2000 replications per cell and fixed data/bootstrap seeds. Unequal sizes, shared daily
overlap and a persistent global state are included. Exact binomial Monte Carlo uncertainty,
familywise diagnostic intervals, nominal size/coverage, finite-MC tolerances, degeneracy counts,
power reporting, budget and stopping conditions are explicit. This broad numerical work is
**not authorized or run** here. The global-state analytic failure may already reject the baseline.

Finite synthetic calibration cannot establish market validity, empirical independence, coverage,
causal identification or forward evidence. Next: independently review whether the assumed
population/time dependence and feasible prospective window justify *any* inferential procedure.
Rejecting the present candidate/window is an acceptable outcome. Only then authorize a bounded
research-only implementation/calibration, if still useful. Price access/terms, identity/terminal
coverage, reconciled history, method acceptance, real untouched evidence and elapsed forward
observation remain unmet. No production/cloud/runtime activation or funding conclusion follows.
