"""Forward benchmark-relative outcome calculation."""

from ragged_claws.outcomes.engine import (
    OUTCOME_NAMESPACE,
    SUPPORTED_HORIZONS,
    ForwardOutcomeEngine,
    OutcomeCalculationError,
    SurvivorshipAudit,
    build_survivorship_audit,
)

__all__ = [
    "OUTCOME_NAMESPACE",
    "SUPPORTED_HORIZONS",
    "ForwardOutcomeEngine",
    "OutcomeCalculationError",
    "SurvivorshipAudit",
    "build_survivorship_audit",
]
