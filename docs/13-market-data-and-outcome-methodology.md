# Market Data and Forward-Outcome Methodology

Issue #6 adds a deliberately narrow historical daily-bar boundary and V0 forward-outcome
calculator. It does not resolve identity, parse SEC filings, build portfolios, or implement trading.
Canonical `Security` and `Listing` identities must already be supplied by an upstream process.

## Provider-neutral contract

`DailyBarRequest` is anchored to canonical security and listing UUIDs. Historical symbols are
effective-dated request attributes, never permanent identity. Their intervals are half-open
`[valid_from, valid_to)`, with `None` representing a genuinely open current end rather than an
invented future date. Each segment also requires an explicit provider `asof` date. The adapter
converts the half-open interval to Alpaca's request boundary only at retrieval. `DailyBar` preserves
canonical IDs, session date, exact `Decimal`
OHLC values, optional volume, provider namespace, page-level `SourceObservation`, adjustment, and
feed. Research logic consumes these normalized values and never Alpaca JSON.

The protocol is intentionally limited to historical regular-session daily bars. It is not a generic
financial-data framework.

## Alpaca documentation review

Official Alpaca documentation was re-reviewed on **2026-09-22**:

- [Historical stock bars reference](https://docs.alpaca.markets/us/reference/stockbars) documents
  `GET /v2/stocks/bars`, `1Day`, explicit `adjustment`, explicit `asof`, `feed`, `limit`,
  `page_token`, and response `next_page_token`.
- [About Market Data API](https://docs.alpaca.markets/us/docs/about-market-data-api) documents the
  free Basic plan, U.S. equity historical coverage since 2016, IEX real-time equity coverage, and
  the current Basic request-rate posture.
- [Historical stock data](https://docs.alpaca.markets/docs/historical-stock-data-1) documents feed
  selection and that an unsubscribed user can use the IEX feed.

The adapter therefore sends `timeframe=1Day`, adjustment, feed, and `asof` on every request. It does
not rely on provider defaults. Alpaca's inclusive `end` is sent as the last permitted session date,
and a response outside the canonical historical-symbol interval fails closed. Pagination tokens are
followed; repeated tokens and a bounded-page safety limit fail closed.
Alpaca `asof` is only a convenience for provider symbol mapping; it never replaces canonical
listing identity. The bootstrap research window is 2016-present when Basic coverage is used.

Live retrieval uses direct `httpx`. Credentials are required at adapter construction, carried only
in headers, and never written to manifests. Default tests use invented `MockTransport` payloads and
make no network calls. A response page is captured byte-for-byte through the existing immutable raw
layer before parsing. A page-level `SourceObservation` supplies normalized bars with provenance.
Alpaca payload retention is classified conservatively as restricted and remains outside Git.

## Adjustment and feed semantics

The adapter maps canonical `raw`, `split`, `dividend`, `spinoff`, and `all` values explicitly,
including canonical `spinoff` to Alpaca's `spin-off` spelling;
canonical `other` fails. A calculation requires security and SPY bars to use the configured same
adjustment, feed, and provider namespace. Mismatch raises instead of mixing conventions. Feed
configuration remains versioned adapter/engine configuration because the current canonical
`OutcomeMethodology` has no feed field; price observation IDs retain the concrete provider pages.
This is a documented V0 limitation, not a silent default.

## Entry, exit, and calendar

The engine consumes the existing Event `actionable_at`; it does not recalculate disclosure
actionability. That timestamp must equal an XNYS regular-session open established by the reviewed
local `exchange_calendars` schedule.

- Entry is that session's regular-session open.
- Horizon 1 exits at the next regular session's close.
- Horizon N exits at the close of the Nth regular session **after** the entry session.
- Required horizons are 5, 20, 60, 90, and 120 sessions.

The entry session is index zero and is never counted as horizon one. Weekends, holidays, DST, and
early closes come from the same local XNYS calendar used by the temporal layer, not Alpaca.
Existing actionability regressions cover premarket, at-open, intraday, after-hours, weekend,
holiday, DST, and early-close disclosure behavior; outcome fixtures exercise the resulting
actionable open and holiday/weekend session indexing.

`coverage_through` means the latest **completed regular session** included in the provider-coverage
assessment. It must itself be an XNYS session and cannot precede entry. If the required exit session
is later, the result is right-censored. If that session has elapsed but a required bar is absent,
the result is missing-price. This explicit cutoff prevents a missing response from being mislabeled
as future censoring.

## Return math and benchmark

SPY is supplied as an explicit canonical benchmark `Security`/`Listing` binding; no generic code
contains a magic SPY UUID. For complete outcomes:

```text
security_return  = security_exit_close / security_entry_open - 1
benchmark_return = SPY_exit_close / SPY_entry_open - 1
excess_return    = security_return - benchmark_return
```

All inputs and results are `Decimal`. Calculation uses a local 50-significant-digit,
round-half-even Decimal context so repeating division is deterministic across callers. Results are
not quantized or presentation-rounded; the produced Decimal is persisted exactly. Terminating-ratio
fixtures prove exact hand calculations, and a repeating-ratio regression fixes the deterministic
context behavior.

Sector-relative outcomes are deferred until a point-in-time-safe sector mapping exists.

## Status and survivorship rules

- `complete`: identity, entry, exit, benchmark, provenance, and return state are present.
- `unresolved_security`: canonical security/listing is absent; no ticker fallback is attempted.
- `missing_price`: a required entry or elapsed exit price is absent or unusable.
- `right_censored`: entry is valid but the requested future exit session has not elapsed.
- `terminal_delisted`: used only when an explicit upstream flag says the listing terminated and no
  reliable terminal return exists. Missing bars never imply delisting, and no zero, -100%, or
  last-price return is invented.
- `excluded`: requires an explicit methodology exclusion reason.

`SurvivorshipAudit` reports distinct qualifying events, all outcome rows, each status count, and
distinct resolved security/known issuer counts. No inconvenient record disappears. Reliable
terminal returns and broad corporate-action reconstruction remain deferred and affected rows stay
visible.

## Deterministic identity and persistence

Outcome IDs use UUIDv5 namespace `741922cd-327e-5a32-b640-823c0c665a90`. The UUID name concatenates
these UTF-8 components in order, each encoded as `<character-count>:<value>`:

1. event UUID;
2. security UUID or `unresolved`;
3. listing UUID or `unresolved`;
4. horizon session count;
5. methodology UUID;
6. methodology version.

No symbol or display name participates. `OutcomeMethodology` records methodology/version, local
calendar/version, exact entry/exit conventions, adjustment, and all available price-page
observation IDs that affected the result. The curated Parquet store registers the existing
canonical `Outcome` model. Identical writes are no-ops; a same-ID/different-payload write remains a
hard canonical conflict.

There is no canonical-model or JSON Schema shape change in issue #6.
