# Ragged Claws

> “Show me the incentive and I will show you the outcome.”  
> — Charlie Munger

Ragged Claws is a public-information investment research system.

Its purpose is straightforward:

**Identify publicly observable behavior that may contain useful information about future asset prices, test it rigorously, and use validated signals to improve investment returns.**

The project focuses on economic actors and institutions with potentially informative incentives, access, capital, or relationships. Relevant observations may include:

- corporate insider transactions
- household and beneficial ownership changes
- institutional capital movement
- government contracts and spending
- lobbying activity
- political financial disclosures
- corporate governance changes
- economically relevant network relationships
- market-price and volume behavior

Ragged Claws is not an investigative journalism project, political project, or morality engine.

It does not need to determine why an actor behaved a certain way unless motive itself can be measured reliably and improves predictive performance.

The governing question is:

> **Given only information publicly available at time T, can observable behavior identify securities with materially different forward risk-adjusted returns?**

## Principles

1. Incentives matter.
2. Observable behavior matters more than narrative.
3. Public timestamps are inviolable.
4. Economic relationships matter more than names on forms.
5. Convergence of independent signals matters more than celebrity.
6. Every hypothesis must survive empirical testing.
7. A model that does not outperform an appropriate benchmark has not earned the right to deploy capital.
8. No trade is preferable to a weak trade.

## Initial operating model

Ragged Claws is intended to become a low-turnover, long-only research and investment system.

The initial live experiment will use approximately $500 of new capital per month after historical and forward validation.

The system should observe continuously and act selectively.

It is not intended to become an options day-trading platform.

## Documentation

- `docs/00-project-charter.md`
- `docs/01-research-philosophy.md`
- `docs/02-methodological-guardrails.md`
- `docs/03-source-and-evidence-policy.md`
- `docs/04-research-roadmap.md`
- `docs/05-system-scope-and-architecture.md`
- `docs/06-data-source-register.md`
- `docs/07-bootstrap-cost-strategy.md`
- `docs/08-implementation-roadmap.md`
- `docs/09-adversarial-architecture-review.md`

See `AGENTS.md` before making implementation changes. The adversarial review hardens integration and point-in-time assumptions that must be honored during M0/M1 implementation.

## Development

Ragged Claws targets Python 3.12 and uses
[`uv`](https://docs.astral.sh/uv/) for dependency and environment management.

```text
uv sync --frozen
uv run pytest
uv run ruff check .
uv run mypy src tests
uv run ragged-claws version
uv run python -m ragged_claws.schema_generation --check
```

The same checks run in GitHub Actions on Ubuntu and Windows with Python 3.12.
