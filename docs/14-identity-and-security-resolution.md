# Identity and Security Resolution

**Status:** M1 baseline

**Documentation review date:** 2026-09-22

**Scope:** Issue #7 only

## Resolution hierarchy

The resolver preserves three independent canonical layers:

```text
Issuer Entity
    -> Security / share class
        -> Listing / venue / effective-dated symbol
```

`IdentityCatalog` resolves exact typed identifier claims and historical listings. A successful
identifier match requires both a source-backed `ExternalIdentifier` and the referenced canonical
subject. Claims are never allowed to create an orphan resolution. Exact identifiers mapping to
more than one canonical subject return `CONFLICT`; multiple historically valid listings return
`AMBIGUOUS`; absent or temporally unusable evidence returns `UNRESOLVED`. Input/provider ordering
does not select a winner.

`EXACT` confidence is an evidence class, not a probability. It is used only for one exact typed
identifier or one unique security-scoped historical listing. The resolver does not assign numeric
confidence.

## Exact matching and canonical creation

CIKs are ASCII digits, normalized to ten digits with leading zeroes. SEC CIK resolves only an
issuer `Entity`; it never implies one Security or ticker. LEI also resolves only Entity. FIGI,
ISIN, CUSIP, and SEDOL subject-layer restrictions mirror the canonical model. Composite FIGI
requires an explicit market scope.

Names and symbols are metadata and candidate inputs only. The baseline contains no fuzzy company
matching and no permanent identity rule based on a company name, ticker, exchange-plus-symbol,
provider result order, or response index.

Previously unseen issuer creation from an SEC CIK is available only as the explicit
`deterministic_entity_id_from_cik` operation. Callers decide whether creation is appropriate; an
ordinary resolve request never creates a subject.

Dedicated UUIDv5 namespaces and exact rules introduced here are:

| Subject/claim | Namespace | UUID name |
|---|---|---|
| Entity from CIK | `6763f0c3-47fd-5b77-b98d-0eb4cd614c48` | `sec_cik:<10-digit CIK>` |
| Security from strong identifier | `8fc09b2d-e09e-5e2b-a9bf-b2d87d44b74c` | length-prefixed identifier type, normalized identifier, and explicit composite market scope |
| Listing from instrument FIGI | `1d0c8bb1-4968-5f63-b9b8-f9169588c86d` | `figi_instrument:<normalized FIGI>` |
| ExternalIdentifier evidence claim | `302cadd4-82cb-54c2-9a65-58cf0aa6af3e` | length-prefixed subject type/ID, identifier type/value, market scope, and source-observation ID |

Security creation is restricted to share-class FIGI, scoped composite FIGI, ISIN, or CUSIP.
Listing creation is restricted to instrument FIGI. Normal resolver fixtures generally supply
explicit canonical Security/Listing IDs; these helpers exist only where the strong source
identifier genuinely defines the canonical layer.

## Historical listings

Historical listing lookup requires canonical `security_id`, MIC, symbol, and an as-of
`TemporalValue`. Ticker alone is never accepted. Effective intervals are half-open:
`[effective_from, effective_to)`. Day precision compares only with day precision, and exact
timestamp precision compares only with exact timestamp precision. Month/year/unknown boundaries,
or mixed precision that cannot defend the boundary, fail closed as coarse validity rather than
inventing an instant.

This permits a ticker change to select the correct pre/post-change Listing and prevents the same
symbol reused by another issuer/security from merging the two. Overlapping evidence stays
ambiguous.

## Point-in-time knowledge

Validity and knowledge are separate. A Listing may have been valid at historical time T while the
supporting identifier claim became known later. With `known_at`, resolution uses the existing
conservative point-in-time eligibility rules and requires eligible source-backed identifier
evidence. `observed_at` never substitutes for `known_from`. Without `known_at`, retrospective
reconstruction is allowed, but the result still returns supporting claim, observation, provenance,
validity, known, and observed timing so later PIT filtering remains possible.

## OpenFIGI enrichment boundary

Official sources reviewed on 2026-09-22:

- [OpenFIGI API v3 documentation](https://www.openfigi.com/api/documentation)
- [FIGI allocation rules](https://www.openfigi.com/docs/figi-allocation-rules.pdf)

The current official documentation describes `POST /v3/mapping`, optional API keys with lower
unauthenticated limits, response fields `figi`, `shareClassFIGI`, and `compositeFIGI`, warnings for
no result, and explicit error results. The allocation rules distinguish trading-venue instrument,
country/market composite, and global share-class levels.

The fixture-first adapter therefore maps:

- response `figi` -> Listing-level `FIGI_INSTRUMENT`;
- `shareClassFIGI` -> Security-level `FIGI_SHARE_CLASS`;
- `compositeFIGI` -> Security-level `FIGI_COMPOSITE` only when the caller supplies defensible
  explicit `market_scope`.

A composite value without defensible scope remains in raw/staging source data and is not turned
into a misleading canonical claim. A warning/no-result produces no claims. An explicit OpenFIGI
error is an unavailable/error outcome, not a no-result. Ticker and name fields never become
identity. Default tests use invented local response fixtures; there is no live HTTP client or
default network call in issue #7.

## GLEIF enrichment boundary

Official source reviewed on 2026-09-22:

- [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api)

GLEIF documents filters, exact/single-field and full-text searches, fuzzy matching of names and
addresses, legal-entity data, and relationship data. LEI is Entity-level evidence only. An exact
lookup requires the expected normalized LEI and rejects a response for a different identifier.
Fuzzy/name results remain ordered candidates and cannot create or merge an Entity merely because
one ranks first.

Default tests use invented local GLEIF-shaped fixtures. Live GLEIF retrieval is deferred. Provider
failure or no result preserves the existing canonical records unchanged and never enables a fuzzy
name/ticker fallback.

## Provenance and persistence

Every canonical identifier produced by enrichment requires a source-observation ID, provenance
ID, observed time, and optional known/valid timing. No orphan identifier is created.

The canonical Parquet store now supports the identity products used by this issue: `Entity`,
`ExternalIdentifier`, `Security`, and `Listing`. Parquet remains authoritative and DuckDB remains
rebuildable. Identical writes are no-ops; same-ID/different-payload writes retain the existing hard
conflict behavior.

## Deliberate limitations

- No SEC Form 4 parser, market-data/outcome integration, LittleSis, Quiver, R2, or trading.
- No fuzzy entity merge, people/household resolution, corporate-action engine, or generalized
  identity platform.
- No live OpenFIGI/GLEIF network client. The pure provider boundaries are ready for a later
  raw-capture-aware client without making normal tests depend on network access.
- Identifier-format normalization checks representation and identity layer; it does not claim to
  replace provider validation or all identifier checksum rules.
