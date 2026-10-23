"""Independent enumerated answers and strict decision boundaries; no real outcomes."""

from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
from pydantic import ValidationError

from ragged_claws.research.analysis_math import ARMS, bootstrap, contrast, decide, nearest_rank
from ragged_claws.research.analysis_models import AnalysisPlan, ArmSummary, Bootstrap

PLAN = Path(__file__).parents[2] / "research/analysis-plans/sec-p-s-v2.json"


def production_plan() -> AnalysisPlan:
    return AnalysisPlan.model_validate_json(PLAN.read_bytes())


def test_whole_cluster_multiplicity_event_weighting_and_enumerated_percentiles() -> None:
    # A: purchases .0,.2; sale .1. B: purchase .8; sales .2,.2.
    a = (2, Fraction(1, 5), 1, Fraction(1, 10))
    b = (1, Fraction(4, 5), 2, Fraction(2, 5))
    # Independent enumeration of the four equally likely two-cluster samples:
    assert contrast((a, a)) == 0
    assert contrast((a, b)) == Fraction(1, 6)
    assert contrast((b, a)) == Fraction(1, 6)
    assert contrast((b, b)) == Fraction(3, 5)
    # Repeated A retains all of its events twice, never averages issuer means.
    assert contrast((a, a, b)) == Fraction(9, 100)
    answers = [Fraction(0), Fraction(1, 6), Fraction(1, 6), Fraction(3, 5)]
    assert nearest_rank(answers, Fraction(1, 40)) == 0
    assert nearest_rank(answers, Fraction(39, 40)) == Fraction(3, 5)
    assert nearest_rank([Fraction(i) for i in range(1, 41)], Fraction(1, 40)) == 1
    assert nearest_rank([Fraction(i) for i in range(1, 41)], Fraction(39, 40)) == 39
    assert contrast(()) is None and nearest_rank([], Fraction(1, 40)) is None


def test_production_5000_path_fixed_seed_missing_arms_and_decimal_context() -> None:
    clusters = ((1, Fraction(1, 4), 1, Fraction(0)),) * 2
    with localcontext() as context:
        context.prec = 3
        result, low = bootstrap(clusters, production_plan())
    assert result.draws == result.valid_draws == 5000
    assert result.missing_arm_fraction == 0 and low == Fraction(1, 4)
    assert result.lower == result.upper == result.contrast == Decimal("0.25")
    # Independent fixed vector: G=2, 10000 accepted uint64 indices, no rejection possible.
    assert result.draw_indices_sha256 == (
        "889f868279da3ed9c38105538b59e0cf9ebf0cce2f54dc2cabb341437975ccb4"
    )
    assert bootstrap(clusters, production_plan())[0] == result
    # Single-arm clusters yield AA and BB samples without a contrast (~half).
    missing, _ = bootstrap(
        ((1, Fraction(1), 0, Fraction()), (0, Fraction(), 1, Fraction())), production_plan()
    )
    assert missing.missing_arm_draws > 50
    assert missing.valid_draws + missing.missing_arm_draws == 5000
    empty, low = bootstrap((), production_plan())
    assert empty.missing_arm_fraction == 1
    assert empty.lower is empty.upper is empty.contrast is None
    assert low is None


def summary() -> ArmSummary:
    return ArmSummary(
        selected=1000,
        selected_actionable=1000,
        complete=1000,
        distinct_complete_issuers=200,
        complete_coverage=Decimal(1),
        issuer_event_counts={},
        largest_issuer_fraction=None,
        gross_stock_mean=Decimal("0.1"),
        gross_spy_mean=Decimal(0),
        gross_excess_mean=Decimal("0.1"),
        net_excess_means_by_bps={"25": Decimal("0.0975")},
    )


def boot(missing: int = 0) -> Bootstrap:
    return Bootstrap(
        clusters=200,
        draws=5000,
        valid_draws=5000 - missing,
        missing_arm_draws=missing,
        missing_arm_fraction=Decimal(missing) / 5000,
        contrast=Decimal("0.1"),
        lower=Decimal("0.01"),
        upper=Decimal("0.2"),
        draw_indices_sha256="a" * 64,
    )


@pytest.mark.parametrize(
    ("complete", "issuers", "actionable", "missing", "low", "net", "expected"),
    [
        (1000, 200, 1000, 0, "0.01", "0.01", "positive"),
        (999, 200, 1000, 0, "0.01", "0.01", "insufficient"),
        (1000, 199, 1000, 0, "0.01", "0.01", "insufficient"),
        (1008, 200, 1120, 50, "0.01", "0.01", "positive"),  # exact .90 and .01 pass
        (1007, 200, 1120, 50, "0.01", "0.01", "insufficient"),
        (1000, 200, 1000, 51, "0.01", "0.01", "insufficient"),
        (1000, 200, 1000, 0, "0", "0.01", "negative"),
        (1000, 200, 1000, 0, "-0.00001", "0.01", "negative"),
        (1000, 200, 1000, 0, "0.01", "0", "negative"),
        (1000, 200, 1000, 0, "0.01", "-0.00001", "negative"),
    ],
)
def test_proposed_strict_boundaries(
    complete: int,
    issuers: int,
    actionable: int,
    missing: int,
    low: str,
    net: str,
    expected: str,
) -> None:
    arms = {a: summary() for a in ARMS}
    arms[ARMS[1]] = summary().model_copy(
        update={
            "complete": complete,
            "distinct_complete_issuers": issuers,
            "selected_actionable": actionable,
        }
    )
    verdict, reasons = decide(production_plan(), arms, boot(missing), Fraction(low), Fraction(net))
    assert verdict == expected
    assert bool(reasons) == (verdict != "positive")


def test_every_failure_reason_retained_and_production_gates_cannot_be_lowered() -> None:
    arms = {
        a: summary().model_copy(
            update={"complete": 0, "distinct_complete_issuers": 0, "selected_actionable": 0}
        )
        for a in ARMS
    }
    verdict, reasons = decide(production_plan(), arms, boot(5000), None, None)
    assert verdict == "insufficient" and len(reasons) == 8
    data = production_plan().model_dump_json()
    with pytest.raises(ValidationError, match="1000 complete"):
        AnalysisPlan.model_validate_json(
            data.replace('"minimum_complete_per_arm":1000', '"minimum_complete_per_arm":2')
        )
