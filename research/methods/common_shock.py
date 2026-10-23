"""Invented aggregate counterexample only. Never reads prices, ResearchRows or credentials."""

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from typing import Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from ragged_claws.research.analysis_math import ARMS, bootstrap, contrast, decide, decimal
from ragged_claws.research.analysis_models import AnalysisPlan, ArmSummary
from ragged_claws.research.snapshot import digest, encoded, environment, write_once

ROOT = Path(__file__).resolve().parents[2]
CARD = "research/methods/design-v1.json"
SCRIPT = "research/methods/common_shock.py"


class Inputs(BaseModel):
    """Only the fixed invented declaration is executable; not a general data adapter."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    format_version: Literal["common-shock-input/1.0.0"]
    purpose: Literal["invented_statistical_counterexample_not_market_returns"]
    issuers: Literal[200]
    events_per_issuer_per_arm: Literal[5]
    states: tuple[Literal[-1], Literal[1]]
    state_probabilities: tuple[Literal["1/2"], Literal["1/2"]]
    base_excess: Literal["0.01"]
    arm_shock: Literal["0.02"]
    candidate_calendar_episodes: Literal[1]
    bootstrap_resamples: Literal[5000]
    bootstrap_seed: Literal[1729]
    bootstrap_algorithm: Literal["issuer-pairs-sha256-counter/1"]
    production_plan: Literal["research/analysis-plans/sec-p-s-v2.json"]
    production_plan_sha256: Literal[
        "796e7d582c2cc4f2f9d0043c1697834954e64abbd08b613d8a108be46ba43c40"
    ]
    stock_round_trip_bps: tuple[Literal[10], Literal[25], Literal[50]]
    benchmark_round_trip_bps: Literal[0]
    units: str


def declaration() -> tuple[Inputs, bytes]:
    content = (ROOT / CARD).read_bytes()
    card = json.loads(content)
    if (
        card["format_version"] != "methods-design/1.0.0"
        or card["status"] != "proposal"
        or card["execution"]["this_turn"] != "common_shock_exact_enumeration_only"
        or card["execution"]["calibration_authorized"] is not False
        or card["execution"]["real_validation_authorized"] is not False
    ):
        raise ValueError("only the declared invented counterexample is executable")
    return Inputs.model_validate_json(json.dumps(card["counterexample"])), content


def analytic_answer(spec: Inputs, state: int) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    """No sampling: all within-state observations in each arm are identical."""
    if state not in (-1, 1):
        raise ValueError("only the two declared states exist")
    purchase = Fraction(spec.base_excess) + state * Fraction(spec.arm_shock)
    sale = Fraction(spec.base_excess) - state * Fraction(spec.arm_shock)
    return purchase, sale, purchase - sale, purchase - Fraction(25, 10000)


def state_result(spec: Inputs, plan: AnalysisPlan, state: int) -> dict[str, object]:
    purchase, sale, expected, net25 = analytic_answer(spec, state)
    n = spec.events_per_issuer_per_arm
    cluster = (n, n * purchase, n, n * sale)
    clusters = (cluster,) * spec.issuers
    boot, lower = bootstrap(clusters, plan)  # Unmodified production 5000-draw algorithm.
    # This independent constant-arm identity applies to EVERY possible draw.
    assert contrast(clusters) == expected
    assert lower == expected and boot.lower == boot.upper == decimal(expected)
    assert boot.valid_draws == 5000 and boot.missing_arm_draws == 0
    arms = {}
    for arm, value in zip(ARMS, (purchase, sale), strict=True):
        arms[arm] = ArmSummary(
            selected=1000,
            selected_actionable=1000,
            complete=1000,
            distinct_complete_issuers=200,
            complete_coverage=decimal(Fraction(1)),
            issuer_event_counts={f"invented-issuer-{i:03d}": n for i in range(spec.issuers)},
            largest_issuer_fraction=decimal(Fraction(1, spec.issuers)),
            gross_stock_mean=None,
            gross_spy_mean=None,  # No stock or SPY price calculation.
            gross_excess_mean=decimal(value),
            net_excess_means_by_bps={
                str(b): decimal(value - Fraction(b, 10000)) for b in spec.stock_round_trip_bps
            },
        )
    verdict, reasons = decide(plan, arms, boot, lower, net25)
    return {
        "state": state,
        "probability": "1/2",
        "purchase_excess": str(decimal(purchase)),
        "sale_excess": str(decimal(sale)),
        "purchase_net25": str(decimal(net25)),
        "analytic_contrast_and_both_interval_endpoints": str(decimal(expected)),
        "bootstrap": boot.model_dump(mode="json"),
        "current_rule_conditional_verdict": verdict,
        "reasons": reasons,
        "calendar_sensitivity": "insufficient: one episode, proposed minimum twelve",
        "degenerate_within_state_interval": True,
        "investment_validation": "not_evaluated",
        "equal_cost_contrasts": {str(b): str(decimal(expected)) for b in spec.stock_round_trip_bps},
    }


def git_bytes(revision: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)


def run(output: Path, declaration_commit: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", declaration_commit):
        raise ValueError("provide the full pre-execution declaration commit")
    if output.resolve().is_relative_to(ROOT) or output.is_symlink():
        raise ValueError("use a new external artifact folder outside this repository")
    spec, card = declaration()
    if git_bytes(declaration_commit, CARD) != card:
        raise ValueError("card differs from the committed pre-execution declaration")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    code = (ROOT / SCRIPT).read_bytes()
    if git_bytes(head, SCRIPT) != code or git_bytes(head, CARD) != card:
        raise ValueError("commit the declared script/card before full numerical execution")
    plan_content = (ROOT / spec.production_plan).read_bytes()
    if digest(plan_content) != spec.production_plan_sha256:
        raise ValueError("production proposal bytes changed")
    plan = AnalysisPlan.model_validate_json(plan_content)
    if (plan.resamples, plan.seed, plan.algorithm) != (
        spec.bootstrap_resamples,
        spec.bootstrap_seed,
        spec.bootstrap_algorithm,
    ):
        raise ValueError("production resampling declaration mismatch")
    source, lock, runtime = environment()
    identity = {
        "design_declaration_commit": declaration_commit,
        "code_commit": head,
        "card_sha256": digest(card),
        "script_sha256": digest(code),
        "production_plan_sha256": digest(plan_content),
        "source_sha256": source,
        "dependency_lock_sha256": lock,
        "runtime_versions": runtime,
    }
    target = output / digest(encoded(identity))
    write_once(target / "input-card.json", card)
    started = datetime.now(UTC).isoformat()
    timer = perf_counter()
    states = tuple(state_result(spec, plan, state) for state in spec.states)
    probability = sum(
        (
            Fraction(1, 2)
            for state in states
            if state["current_rule_conditional_verdict"] == "positive"
        ),
        Fraction(),
    )
    true_mean = sum(
        (Fraction(1, 2) * analytic_answer(spec, state)[2] for state in spec.states), Fraction()
    )
    coverage = sum(
        (
            Fraction(1, 2)
            for state in states
            if Fraction(str(state["analytic_contrast_and_both_interval_endpoints"])) == true_mean
        ),
        Fraction(),
    )
    assert true_mean == 0 and probability == Fraction(1, 2) and coverage == 0
    result = {
        "format_version": "common-shock-result/1.0.0",
        "identity": identity,
        "notice": "INVENTED EXACT ENUMERATION; NOT MARKET RETURNS OR SYSTEM CALIBRATION",
        "states": states,
        "unconditional_contrast": str(decimal(true_mean)),
        "exact_positive_fraction_in_this_declared_null": str(probability),
        "exact_interval_coverage_of_unconditional_zero": str(coverage),
        "calibration_executed": False,
        "investment_validation": "not_evaluated",
    }
    content = encoded(result)
    write_once(target / "results.json", content)
    report = (
        "# Invented common-shock counterexample\n\n"
        "Exact two-state enumeration, 200 issuers and 1000 events per arm.\n"
        "Issuer intervals are point masses at -.04 / +.04; unconditional contrast is zero.\n"
        "Current conditional states: negative / positive. Calendar adequacy: insufficient.\n"
        "Exact positive fraction 1/2 and unconditional interval coverage 0 belong ONLY to "
        "this declared DGP. They are not Monte Carlo estimates or the system's market error rate.\n"
        "No ResearchRows, prices, real validation or broad calibration were used.\n"
    )
    write_once(target / "results.md", report.encode())
    write_once(
        target / "attempts" / f"{uuid4()}.json",
        encoded(
            {
                "started_at": started,
                "elapsed_seconds": perf_counter() - timer,
                "results_sha256": digest(content),
                "success": True,
            }
        ),
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--declaration-commit", required=True)
    args = parser.parse_args()
    target = run(cast(Path, args.output), cast(str, args.declaration_commit))
    print(json.dumps({"boundary": "INVENTED_COUNTEREXAMPLE_ONLY", "artifact": str(target)}))


if __name__ == "__main__":
    main()
