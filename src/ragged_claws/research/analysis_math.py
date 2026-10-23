"""Exact cost arithmetic and versioned whole-issuer pairs bootstrap; no return engine."""

from collections import Counter
from collections.abc import Iterable
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
from typing import cast

from ragged_claws.research.analysis_models import (
    AnalysisPlan,
    ArmSummary,
    Bootstrap,
    CostRow,
    HorizonAnalysis,
    Verdict,
)
from ragged_claws.research.models import ResearchRow
from ragged_claws.research.snapshot import ResearchError

ARMS = ("equity_purchase", "equity_sale")
BPS = (10, 25, 50)
Cluster = tuple[int, Fraction, int, Fraction]


def decimal(value: Fraction | None) -> Decimal | None:
    if value is None:
        return None
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        return Decimal(value.numerator) / Decimal(value.denominator)


def mean(values: Iterable[Decimal]) -> Fraction | None:
    items = tuple(Fraction(v) for v in values)
    return sum(items, Fraction()) / len(items) if items else None


def subtract(value: Fraction | None, cost: Fraction) -> Decimal | None:
    return decimal(None if value is None else value - cost)


def costs(row: ResearchRow) -> CostRow:
    outcome = row.outcome
    complete = row.status == "complete" and outcome is not None
    stock = outcome.security_return if complete and outcome is not None else None
    spy = outcome.benchmark_return if complete and outcome is not None else None
    excess = outcome.excess_return if complete and outcome is not None else None
    if complete and (stock is None or spy is None or excess is None):
        raise ResearchError("complete row has undefined stock/SPY/excess return")
    return CostRow(
        row=row,
        gross_stock=stock,
        gross_spy=spy,
        gross_excess=excess,
        net_stock_by_bps={
            str(b): subtract(Fraction(stock) if stock is not None else None, Fraction(b, 10000))
            for b in BPS
        },
        net_excess_by_bps={
            str(b): subtract(Fraction(excess) if excess is not None else None, Fraction(b, 10000))
            for b in BPS
        },
    )


def arm_summary(rows: tuple[CostRow, ...], arm: str) -> ArmSummary:
    selected = tuple(
        r for r in rows if r.row.event.event_type == arm and r.row.selection == "selected"
    )
    actionable = tuple(r for r in selected if r.row.timing_eligible)
    complete = tuple(r for r in actionable if r.row.status == "complete")
    if any(r.row.event.issuer_entity_id is None for r in complete):
        raise ResearchError("complete economic event requires explicit issuer for clustering")
    counts = dict(sorted(Counter(str(r.row.event.issuer_entity_id) for r in complete).items()))
    gross_excess = mean(r.gross_excess for r in complete if r.gross_excess is not None)
    return ArmSummary(
        selected=len(selected),
        selected_actionable=len(actionable),
        complete=len(complete),
        distinct_complete_issuers=len(counts),
        complete_coverage=decimal(Fraction(len(complete), len(actionable))) if actionable else None,
        issuer_event_counts=counts,
        largest_issuer_fraction=decimal(Fraction(max(counts.values()), len(complete)))
        if counts
        else None,
        gross_stock_mean=decimal(
            mean(r.gross_stock for r in complete if r.gross_stock is not None)
        ),
        gross_spy_mean=decimal(mean(r.gross_spy for r in complete if r.gross_spy is not None)),
        gross_excess_mean=decimal(gross_excess),
        net_excess_means_by_bps={str(b): subtract(gross_excess, Fraction(b, 10000)) for b in BPS},
    )


def contrast(clusters: Iterable[Cluster]) -> Fraction | None:
    """Each tuple is purchase n/sum and sale n/sum; repetition means multiplicity."""
    pn = sn = 0
    ps = ss = Fraction()
    for p_count, p_sum, s_count, s_sum in clusters:
        pn += p_count
        ps += p_sum
        sn += s_count
        ss += s_sum
    return ps / pn - ss / sn if pn and sn else None


def nearest_rank(values: list[Fraction], probability: Fraction) -> Fraction | None:
    if not values:
        return None
    rank = probability.numerator * len(values) + probability.denominator - 1
    rank //= probability.denominator
    return sorted(values)[max(1, rank) - 1]


def bootstrap(
    clusters: tuple[Cluster, ...], plan: AnalysisPlan
) -> tuple[Bootstrap, Fraction | None]:
    """SHA256 domain||uint64(seed)||uint64(counter), first uint64, unbiased rejection.

    Cluster ordering is sorted issuer UUID at the caller. Digest is the concatenated
    uint64 big-endian accepted draw indices, including draws missing either arm.
    """
    counter = 0
    draws_hash = sha256()
    values: list[Fraction] = []
    size = len(clusters)
    limit = (2**64 // size) * size if size else 0
    for _ in range(plan.resamples):
        sampled = []
        for _ in range(size):
            while True:
                content = b"ragged-claws-issuer-bootstrap/v1\0"
                content += plan.seed.to_bytes(8, "big") + counter.to_bytes(8, "big")
                candidate = int.from_bytes(sha256(content).digest()[:8], "big")
                counter += 1
                if candidate < limit:
                    index = candidate % size
                    draws_hash.update(index.to_bytes(8, "big"))
                    sampled.append(clusters[index])
                    break
        value = contrast(sampled)
        if value is not None:
            values.append(value)
    low = nearest_rank(values, Fraction(1, 40))
    return Bootstrap(
        clusters=size,
        draws=plan.resamples,
        valid_draws=len(values),
        missing_arm_draws=plan.resamples - len(values),
        missing_arm_fraction=cast(
            Decimal, decimal(Fraction(plan.resamples - len(values), plan.resamples))
        ),
        contrast=decimal(contrast(clusters)),
        lower=decimal(low),
        upper=decimal(nearest_rank(values, Fraction(39, 40))),
        draw_indices_sha256=draws_hash.hexdigest(),
    ), low


def decide(
    plan: AnalysisPlan,
    arms: dict[str, ArmSummary],
    boot: Bootstrap,
    exact_lower: Fraction | None,
    exact_purchase_net25: Fraction | None,
) -> tuple[Verdict, tuple[str, ...]]:
    insufficient = []
    for arm in ARMS:
        summary = arms[arm]
        if summary.complete < plan.minimum_complete_per_arm:
            insufficient.append(f"{arm}:complete_events_below_minimum")
        if summary.distinct_complete_issuers < plan.minimum_issuers_per_arm:
            insufficient.append(f"{arm}:complete_issuers_below_minimum")
        # Compare integers/rationals, never a rounded display fraction.
        if not summary.selected_actionable or (
            Fraction(summary.complete, summary.selected_actionable)
            < Fraction(plan.minimum_coverage_per_arm)
        ):
            insufficient.append(f"{arm}:actionable_coverage_below_minimum_or_undefined")
    if Fraction(boot.missing_arm_draws, boot.draws) > Fraction(plan.maximum_missing_arm_fraction):
        insufficient.append("missing_arm_resamples_above_maximum")
    if exact_lower is None or exact_purchase_net25 is None:
        insufficient.append("undefined_primary_statistics")
    negative = []
    if exact_lower is not None and exact_lower <= 0:
        negative.append("contrast_lower_not_strictly_positive")
    if exact_purchase_net25 is not None and exact_purchase_net25 <= 0:
        negative.append("purchase_net25_not_strictly_positive")
    reasons = tuple(insufficient + negative)
    return ("insufficient" if insufficient else "negative" if negative else "positive"), reasons


def analyze_horizon(rows: tuple[CostRow, ...], plan: AnalysisPlan, horizon: int) -> HorizonAnalysis:
    selected = tuple(r for r in rows if r.row.horizon_sessions == horizon)
    arms = {arm: arm_summary(selected, arm) for arm in ARMS}
    if horizon != plan.primary_horizon:
        return HorizonAnalysis(
            horizon=horizon,
            arms=arms,
            bootstrap=None,
            conditional_verdict="not_evaluated",
            reasons=("secondary_descriptive_endpoint_cannot_rescue_primary",),
            equal_cost_contrast_by_bps={},
        )
    groups: dict[str, list[CostRow]] = {}
    for row in selected:
        if (
            row.row.selection == "selected"
            and row.row.timing_eligible
            and row.row.status == "complete"
            and row.row.event.event_type in ARMS
        ):
            groups.setdefault(str(row.row.event.issuer_entity_id), []).append(row)
    clusters = []
    for issuer in sorted(groups):
        p = [
            Fraction(r.gross_excess)
            for r in groups[issuer]
            if r.row.event.event_type == ARMS[0] and r.gross_excess is not None
        ]
        s = [
            Fraction(r.gross_excess)
            for r in groups[issuer]
            if r.row.event.event_type == ARMS[1] and r.gross_excess is not None
        ]
        clusters.append((len(p), sum(p, Fraction()), len(s), sum(s, Fraction())))
    boot, exact_lower = bootstrap(tuple(clusters), plan)
    purchase = mean(
        r.gross_excess
        for r in selected
        if r.row.event.event_type == ARMS[0]
        and r.row.selection == "selected"
        and r.row.timing_eligible
        and r.gross_excess is not None
    )
    verdict, reasons = decide(
        plan, arms, boot, exact_lower, None if purchase is None else purchase - Fraction(25, 10000)
    )
    return HorizonAnalysis(
        horizon=horizon,
        arms=arms,
        bootstrap=boot,
        conditional_verdict=verdict,
        reasons=reasons or ("all_proposed_conditions_met_conditional_only",),
        equal_cost_contrast_by_bps={str(b): boot.contrast for b in BPS},
    )
