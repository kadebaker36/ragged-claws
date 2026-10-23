"""Analytic oracle, not stochastic calibration or a second return engine."""

from fractions import Fraction

import pytest
from pydantic import ValidationError

from ragged_claws.research.analysis_math import contrast
from research.methods.common_shock import Inputs, analytic_answer, declaration


def test_production_count_common_shock_oracle() -> None:
    spec, _ = declaration()
    assert spec.issuers * spec.events_per_issuer_per_arm == 1000
    # Independently enumerated expected answers, not bootstrap-generated test targets.
    assert analytic_answer(spec, -1) == (
        Fraction(-1, 100),
        Fraction(3, 100),
        Fraction(-1, 25),
        Fraction(-1, 80),
    )
    assert analytic_answer(spec, 1) == (
        Fraction(3, 100),
        Fraction(-1, 100),
        Fraction(1, 25),
        Fraction(11, 400),
    )
    assert (analytic_answer(spec, -1)[2] + analytic_answer(spec, 1)[2]) / 2 == 0
    # Every possible draw has200clusters of this same tuple. Extreme multiplicities
    # cannot supply a new calendar state. CI does not run a heavy random experiment.
    for sign in (-1, 1):
        purchase, sale, expected, _ = analytic_answer(spec, sign)
        group = (5, 5 * purchase, 5, 5 * sale)
        assert contrast((group,) * 200) == expected


def test_counterexample_input_is_fixed_and_not_a_general_return_adapter() -> None:
    spec, _ = declaration()
    for original, changed in [
        ('"issuers":200', '"issuers":2'),
        ('"bootstrap_seed":1729', '"bootstrap_seed":7'),
    ]:
        with pytest.raises(ValidationError):
            Inputs.model_validate_json(spec.model_dump_json().replace(original, changed))
    with pytest.raises(ValueError, match="two declared states"):
        analytic_answer(spec, 0)
