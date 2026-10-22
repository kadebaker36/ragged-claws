"""Timestamp-safe forward outcomes from normalized daily bars."""

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from importlib.metadata import version
from typing import cast
from uuid import UUID, uuid5

import exchange_calendars as xcals  # type: ignore[import-untyped]

from ragged_claws.market_data import DailyBar
from ragged_claws.market_data.listings import listing_bounds
from ragged_claws.models import (
    Event,
    Listing,
    Outcome,
    OutcomeMethodology,
    OutcomeStatus,
    PriceAdjustment,
    Security,
)
from ragged_claws.models.base import CanonicalModel

OUTCOME_NAMESPACE = UUID("741922cd-327e-5a32-b640-823c0c665a90")
SUPPORTED_HORIZONS = frozenset({5, 20, 60, 90, 120})
RETURN_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)


class OutcomeCalculationError(RuntimeError):
    """Raised when market-data or calendar semantics disagree explicitly."""


class SurvivorshipAudit(CanonicalModel):
    """Counts every requested outcome state so records cannot disappear silently."""

    qualifying_events: int
    outcome_rows: int
    complete: int
    right_censored: int
    unresolved_security: int
    missing_price: int
    terminal_delisted: int
    explicit_exclusions: int
    distinct_security_count: int
    distinct_issuer_count: int


class ForwardOutcomeEngine:
    """Calculate the V0 open-to-Nth-following-session-close convention."""

    def __init__(
        self,
        *,
        methodology_id: UUID,
        methodology_version: str,
        adjustment: PriceAdjustment,
        benchmark_security: Security,
        benchmark_listing: Listing,
        feed: str,
        calendar_name: str = "XNYS",
    ) -> None:
        if benchmark_listing.security_id != benchmark_security.security_id:
            raise ValueError("benchmark listing must belong to benchmark security")
        if adjustment is PriceAdjustment.OTHER:
            raise ValueError("V0 outcomes require a concrete price adjustment")
        self.methodology_id = methodology_id
        self.methodology_version = methodology_version
        self.adjustment = adjustment
        self.benchmark_security = benchmark_security
        self.benchmark_listing = benchmark_listing
        self.feed = feed
        self.calendar_name = calendar_name
        self.calendar_version = version("exchange-calendars")

    def calculate(
        self,
        *,
        event: Event,
        horizon_sessions: int,
        security: Security | None,
        listing: Listing | None,
        security_bars: Sequence[DailyBar],
        benchmark_bars: Sequence[DailyBar],
        coverage_through: date,
        provenance_id: UUID,
        terminal_delisted: bool = False,
        exclusion_reason: str | None = None,
        listing_history: Sequence[Listing] = (),
    ) -> Outcome:
        if horizon_sessions not in SUPPORTED_HORIZONS:
            raise ValueError(f"unsupported horizon: {horizon_sessions}")
        if event.actionable_at is None:
            raise OutcomeCalculationError("event has no actionable timestamp")
        if (security is None) != (listing is None):
            raise OutcomeCalculationError("security and listing must resolve together")
        if listing_history and listing is None:
            raise OutcomeCalculationError("listing history requires resolved identity")
        if security is not None and listing is not None:
            if (
                event.issuer_entity_id is not None
                and event.issuer_entity_id != security.issuer_entity_id
            ):
                raise OutcomeCalculationError(
                    "event issuer disagrees with resolved security issuer"
                )
            if listing.security_id != security.security_id:
                raise OutcomeCalculationError("listing does not belong to the supplied security")
            if event.security_id is not None and event.security_id != security.security_id:
                raise OutcomeCalculationError("event security disagrees with resolved security")
            if event.listing_id is not None and event.listing_id != listing.listing_id:
                raise OutcomeCalculationError("event listing disagrees with resolved listing")
            for segment in listing_history:
                if segment.security_id != security.security_id:
                    raise OutcomeCalculationError("listing history belongs to another security")
                if segment.exchange_mic != listing.exchange_mic:
                    raise OutcomeCalculationError("listing history requires one compatible venue")
        if exclusion_reason is not None:
            return self._outcome(
                event=event,
                horizon=horizon_sessions,
                security=security,
                listing=listing,
                status=OutcomeStatus.EXCLUDED,
                provenance_id=provenance_id,
                exclusion_reason=exclusion_reason,
            )
        if security is None or listing is None:
            return self._outcome(
                event=event,
                horizon=horizon_sessions,
                security=None,
                listing=None,
                status=OutcomeStatus.UNRESOLVED_SECURITY,
                provenance_id=provenance_id,
            )
        if terminal_delisted:
            return self._outcome(
                event=event,
                horizon=horizon_sessions,
                security=security,
                listing=listing,
                status=OutcomeStatus.TERMINAL_DELISTED,
                provenance_id=provenance_id,
            )

        entry_date, exit_date, entry_at, exit_at = self._sessions(
            event.actionable_at, horizon_sessions
        )
        if coverage_through < entry_date or not self._is_session(coverage_through):
            raise OutcomeCalculationError(
                "coverage_through must be the latest completed regular session"
            )
        bindings = self._listing_bindings((listing, *listing_history))
        benchmark_bindings = self._listing_bindings((self.benchmark_listing,))
        if not self._valid_on(listing, entry_date):
            raise OutcomeCalculationError("entry listing is not valid on the entry session")
        self._validate_coverage(bindings, entry_date, min(exit_date, coverage_through))
        security_by_date = self._index_bars(security_bars, bindings)
        benchmark_by_date = self._index_bars(benchmark_bars, benchmark_bindings)
        providers = {
            bar.provider_namespace for bar in (*security_bars, *benchmark_bars)
        }
        if len(providers) > 1:
            raise OutcomeCalculationError(
                "security and benchmark bars require one compatible price provider"
            )
        entry = security_by_date.get(entry_date)
        benchmark_entry = benchmark_by_date.get(entry_date)
        if entry is None or benchmark_entry is None:
            sources = tuple(
                sorted(
                    {
                        value.source_observation_id
                        for value in (entry, benchmark_entry)
                        if value is not None
                    },
                    key=str,
                )
            )
            return self._outcome(
                event=event,
                horizon=horizon_sessions,
                security=security,
                listing=listing,
                status=OutcomeStatus.MISSING_PRICE,
                provenance_id=provenance_id,
                entry_at=entry_at if entry is not None else None,
                entry_price=entry.open if entry is not None else None,
                source_ids=sources,
            )
        entry_sources = tuple(
            sorted({entry.source_observation_id, benchmark_entry.source_observation_id}, key=str)
        )
        if exit_date > coverage_through:
            return self._outcome(
                event=event,
                horizon=horizon_sessions,
                security=security,
                listing=listing,
                status=OutcomeStatus.RIGHT_CENSORED,
                provenance_id=provenance_id,
                entry_at=entry_at,
                entry_price=entry.open,
                source_ids=entry_sources,
            )

        exit_bar = security_by_date.get(exit_date)
        benchmark_exit = benchmark_by_date.get(exit_date)
        if exit_bar is None or benchmark_exit is None:
            available_sources = {
                entry.source_observation_id,
                benchmark_entry.source_observation_id,
            }
            if exit_bar is not None:
                available_sources.add(exit_bar.source_observation_id)
            if benchmark_exit is not None:
                available_sources.add(benchmark_exit.source_observation_id)
            return self._outcome(
                event=event,
                horizon=horizon_sessions,
                security=security,
                listing=listing,
                status=OutcomeStatus.MISSING_PRICE,
                provenance_id=provenance_id,
                entry_at=entry_at,
                entry_price=entry.open,
                source_ids=tuple(sorted(available_sources, key=str)),
            )

        source_ids = tuple(
            sorted(
                {
                    entry.source_observation_id,
                    exit_bar.source_observation_id,
                    benchmark_entry.source_observation_id,
                    benchmark_exit.source_observation_id,
                },
                key=str,
            )
        )
        with localcontext(RETURN_CONTEXT):
            security_return = exit_bar.close / entry.open - Decimal(1)
            benchmark_return = benchmark_exit.close / benchmark_entry.open - Decimal(1)
            excess_return = security_return - benchmark_return
        return self._outcome(
            event=event,
            horizon=horizon_sessions,
            security=security,
            listing=listing,
            status=OutcomeStatus.COMPLETE,
            provenance_id=provenance_id,
            entry_at=entry_at,
            exit_at=exit_at,
            entry_price=entry.open,
            exit_price=exit_bar.close,
            security_return=security_return,
            benchmark_return=benchmark_return,
            excess_return=excess_return,
            source_ids=source_ids,
        )

    def _sessions(
        self, actionable_at: datetime, horizon: int
    ) -> tuple[date, date, datetime, datetime]:
        probe = actionable_at.astimezone(UTC).date()
        calendar = xcals.get_calendar(
            self.calendar_name,
            start=probe - timedelta(days=7),
            end=probe + timedelta(days=400),
        )
        local_date = actionable_at.astimezone(calendar.tz).date()
        try:
            entry_session = calendar.date_to_session(local_date)
            expected_open = cast(datetime, calendar.session_open(entry_session).to_pydatetime())
            expected_open = expected_open.astimezone(UTC)
            if actionable_at.astimezone(UTC) != expected_open:
                raise OutcomeCalculationError(
                    "event actionable timestamp is not the reviewed regular-session open"
                )
            exit_session = calendar.sessions_window(entry_session, horizon + 1)[horizon]
            exit_close = cast(datetime, calendar.session_close(exit_session).to_pydatetime())
            return (
                expected_open.astimezone(calendar.tz).date(),
                exit_close.astimezone(calendar.tz).date(),
                expected_open,
                exit_close.astimezone(UTC),
            )
        except OutcomeCalculationError:
            raise
        except Exception as exc:
            raise OutcomeCalculationError("XNYS session indexing failed") from exc

    def _index_bars(
        self, bars: Sequence[DailyBar], bindings: Mapping[UUID, Listing]
    ) -> dict[date, DailyBar]:
        indexed: dict[date, DailyBar] = {}
        for bar in bars:
            listing = bindings.get(bar.listing_id)
            if listing is None or bar.security_id != listing.security_id:
                raise OutcomeCalculationError("bar canonical identity disagrees with its binding")
            if not self._valid_on(listing, bar.session_date):
                raise OutcomeCalculationError("bar is outside its canonical listing interval")
            if not self._is_session(bar.session_date):
                raise OutcomeCalculationError("bar date is not a configured regular session")
            if bar.adjustment is not self.adjustment or bar.feed != self.feed:
                raise OutcomeCalculationError(
                    "security and benchmark bars require the configured adjustment and feed"
                )
            previous = indexed.get(bar.session_date)
            if previous is not None and previous != bar:
                raise OutcomeCalculationError(f"conflicting bar for {bar.session_date}")
            indexed[bar.session_date] = bar
        return indexed

    @staticmethod
    def _valid_on(listing: Listing, session: date) -> bool:
        start, end = listing_bounds(listing)
        return (start is None or start <= session) and (end is None or session < end)

    @staticmethod
    def _listing_bindings(listings: Sequence[Listing]) -> dict[UUID, Listing]:
        bindings: dict[UUID, Listing] = {}
        try:
            for listing in listings:
                previous = bindings.get(listing.listing_id)
                if previous is not None and previous != listing:
                    raise OutcomeCalculationError("conflicting canonical listing binding")
                listing_bounds(listing)
                bindings[listing.listing_id] = listing
            ordered = sorted(
                bindings.values(), key=lambda value: listing_bounds(value)[0] or date.min,
            )
            for previous, current in zip(ordered, ordered[1:], strict=False):
                end = listing_bounds(previous)[1]
                start = listing_bounds(current)[0]
                if end is None or start is None or start < end:
                    raise OutcomeCalculationError("overlapping canonical listing bindings")
        except ValueError as exc:
            raise OutcomeCalculationError(str(exc)) from exc
        return bindings

    @staticmethod
    def _validate_coverage(bindings: Mapping[UUID, Listing], start: date, end: date) -> None:
        cursor = start
        for listing in sorted(
            bindings.values(), key=lambda value: listing_bounds(value)[0] or date.min,
        ):
            lower, upper = listing_bounds(listing)
            if upper is not None and upper <= cursor:
                continue
            if lower is not None and lower > cursor:
                break
            if upper is None or upper > end:
                return
            cursor = upper
        raise OutcomeCalculationError("canonical listing coverage gap across outcome horizon")

    def _is_session(self, value: date) -> bool:
        calendar = xcals.get_calendar(
            self.calendar_name,
            start=value - timedelta(days=7),
            end=value + timedelta(days=7),
        )
        return bool(calendar.is_session(value))

    def _methodology(self, source_ids: tuple[UUID, ...]) -> OutcomeMethodology:
        return OutcomeMethodology(
            methodology_id=self.methodology_id,
            methodology_version=self.methodology_version,
            calendar_id=self.calendar_name.lower(),
            calendar_version=self.calendar_version,
            entry_convention="actionable_regular_session_open",
            exit_convention="nth_following_regular_session_close",
            price_adjustment=self.adjustment,
            price_source_observation_ids=source_ids,
        )

    def _outcome(
        self,
        *,
        event: Event,
        horizon: int,
        security: Security | None,
        listing: Listing | None,
        status: OutcomeStatus,
        provenance_id: UUID,
        entry_at: datetime | None = None,
        exit_at: datetime | None = None,
        entry_price: Decimal | None = None,
        exit_price: Decimal | None = None,
        security_return: Decimal | None = None,
        benchmark_return: Decimal | None = None,
        excess_return: Decimal | None = None,
        source_ids: tuple[UUID, ...] = (),
        exclusion_reason: str | None = None,
    ) -> Outcome:
        if event.actionable_at is None:
            raise OutcomeCalculationError("event has no actionable timestamp")
        security_id = security.security_id if security is not None else None
        listing_id = listing.listing_id if listing is not None else None
        components = (
            str(event.event_id),
            str(security_id or "unresolved"),
            str(listing_id or "unresolved"),
            str(horizon),
            str(self.methodology_id),
            self.methodology_version,
        )
        identity = "".join(f"{len(value)}:{value}" for value in components)
        return Outcome(
            outcome_id=uuid5(OUTCOME_NAMESPACE, identity),
            event_id=event.event_id,
            security_id=security_id,
            listing_id=listing_id,
            actionable_at=event.actionable_at,
            entry_at=entry_at,
            exit_at=exit_at,
            horizon_sessions=horizon,
            entry_price=entry_price,
            exit_price=exit_price,
            security_return=security_return,
            benchmark_listing_id=(
                self.benchmark_listing.listing_id
                if security_id is not None and listing_id is not None
                else None
            ),
            benchmark_return=benchmark_return,
            excess_return=excess_return,
            status=status,
            methodology=self._methodology(source_ids),
            exclusion_reason=exclusion_reason,
            provenance_id=provenance_id,
        )


def build_survivorship_audit(
    outcomes: Sequence[Outcome],
    *,
    issuer_by_event: Mapping[UUID, UUID] | None = None,
) -> SurvivorshipAudit:
    """Summarize all outcome rows, retaining unresolved and incomplete categories."""
    counts = Counter(outcome.status for outcome in outcomes)
    issuers = issuer_by_event or {}
    return SurvivorshipAudit(
        qualifying_events=len({outcome.event_id for outcome in outcomes}),
        outcome_rows=len(outcomes),
        complete=counts[OutcomeStatus.COMPLETE],
        right_censored=counts[OutcomeStatus.RIGHT_CENSORED],
        unresolved_security=counts[OutcomeStatus.UNRESOLVED_SECURITY],
        missing_price=counts[OutcomeStatus.MISSING_PRICE],
        terminal_delisted=counts[OutcomeStatus.TERMINAL_DELISTED],
        explicit_exclusions=counts[OutcomeStatus.EXCLUDED],
        distinct_security_count=len(
            {outcome.security_id for outcome in outcomes if outcome.security_id is not None}
        ),
        distinct_issuer_count=len(
            {issuers[outcome.event_id] for outcome in outcomes if outcome.event_id in issuers}
        ),
    )
