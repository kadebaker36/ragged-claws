# Quiver political/government context — bounded M1 engineering

## Reviewed contract and actual access

Reviewed 2026-10-22 from official public documentation only:

- [OpenAPI schema](https://api.quiverquant.com/docs/schema.json), OpenAPI3.0.3/APIv1,
  SHA-256 `72b5c480c44494371c318c88072319795bf8440600998d81d297b5cd3de17af2`,
  238296bytes, fetched2026-10-22T22:13:44.310511Z. Exact public documentation acquisition
  evidence is retained in the external supervisor artifacts directory, not as a vendor dataset fixture.
- [API docs](https://api.quiverquant.com/docs/),
  [Congress Trades](https://api.quiverquant.com/datasets/congress-trades),
  [Government Contracts](https://api.quiverquant.com/datasets/government-contracts),
  [Corporate Lobbying](https://api.quiverquant.com/datasets/corporate-lobbying).
- [Pricing](https://api.quiverquant.com/pricing/): Hobbyist advertises congressional trading,
  government contracts and corporate lobbying, with noncommercial rights. Dataset advertising
  and schema Tier1 tags do not establish an individual user's entitlement.
- [Website/API terms](https://www.quiverquant.com/termsofservice/) (modified2026-06-25):
  sections5–6 restrict retention/use and third-party distribution; section24 refers to a separate
  purchased API agreement. The applicable account agreement and its retention permissions have
  **not** been obtained/reviewed. This engineering review grants no contractual rights.

The user has no Quiver account, subscription or credentials. No licensed data endpoint was
called and no account/subscription was created. Live payload/entitlement/coverage, applicable
agreement and real-data research validation remain pending. Only the public schema was fetched.
Public fixtures are entirely invented, not recorded Quiver data. No Quiver connector is available.

## Endpoint subset

| Adapter selector | API GET | Reviewed response schema | Purpose |
|---|---|---|---|
| congress_v1 | `/beta/live/congresstrading` | CongressionalTrade[] | Recent reported trades; ReportDate, TransactionDate and an explicit Range where supplied |
| congress_v2 | `/beta/bulk/congresstrading?version=V2&page=1&page_size=20` | CongressionalTradeV2[] | One bounded historical page; separate Filed/Traded, vendor upload/curation and verbatim Subholding |
| contracts | `/beta/live/govcontractsall?page=1&page_size=20` | GovContractAll[] | Individual announcements, distinct contract-action dates and obligated amount |
| lobbying | `/beta/live/lobbying?page=1&page_size=20` | LobbyingRecord[] | Reported spending instances with vendor issue classifications |

The adapter accepts explicit positive page/page_size (maximum100) for the last three;
V2 requires exactly version=V2. V1 accepts no query parameters and has a local maximum500rows.
All inputs have a5MB bound. Other query keys, credentials in URLs, hosts, redirects and endpoints
are rejected. There is no automatic pagination, traversal or bulk expansion. Response arrays have
no documented row/page metadata beyond their records; no completeness assertion is made.
V1 and V2 are separate reviewed response contracts, not an inferred mix-and-match field alias set.
Holdings, profiles, quarterly aggregates, insider/trump/donor feeds and other datasets are deferred.

## Dates and facts

| Endpoint fields | Meaning retained in staging |
|---|---|
| TransactionDate / Traded | Transaction calendar date |
| ReportDate / Filed | Vendor-reported report/disclosure calendar date |
| Quiver_Upload_Time | Vendor scrape/processing audit time, never original publication |
| last_modified | Vendor curation audit time |
| Contracts Date | Announcement calendar date |
| Contracts action_date | Contract action calendar date, distinct from announcement |
| Lobbying Date | Date the spending instance was reported; not its activity period |

The schema labels several calendar-date fields date-time. The adapter preserves full raw text
but represents only their documented calendar-day meaning, including source midnight-like
datetime encodings. It never manufactures UTC midnight or intraday dissemination precision.
Malformed/partial dates and provable occurrence-after-report contradictions fail after raw capture.
Vendor audit clocks retain exact aware whole-second timestamps where supported; naive clocks or
unsupported subsecond precision remain raw/UNKNOWN. No timezone or missing reporting period is guessed.

These are vendor date assertions, without an independently supported publication/availability
instant. Response public_time and row public_time/known_from/actionability remain unknown.
There is no automatic historical feature or observed-time forward-use policy. A reviewed match
retains the **primary Event's** original timing, including any defensible actionable convention;
vendor dates/processing metadata never rewrite it. Source reported, occurrence, upload, curation,
collection and later review/derivation times remain distinct. The PIT snapshot regression rejects
a vendor feature with unknown known_from, including a case whose upload follows the next-day open.

Exact monetary tokens are parsed with Decimal. V1 Amount and V2 Trade_Size_USD are documented
lower bounds, not estimates or full transaction values. V1 Range can preserve independently
disclosed lower/upper bounds, with exact raw text and parser version. No midpoint, missing upper
bound, quantity or return is invented. Unknown range notation remains raw with explicit notes.
Contracts map obligated amount; lobbying maps reported spending, both USD per the documented
meanings. Unsupported transaction classifications remain excluded/countable.

Only reviewed fields enter typed normalized facts (FinancialValue, DisclosedRange and explicitly
Quiver-attributed EventAttribute assertions). Every other field is quarantined in staging and
retained in immutable raw bytes. This is an allowlist, not a list of known performance names.
ExcessReturn, PriceChange, SPYChange, excess_return and previously unseen nested future metrics
cannot enter canonical Event facts or predictive feature inputs. Quarantined staging is not a
research feature interface. Research/support code consumes canonical models only.

Subholding is documented only as a reported subholding. Its exact text (including self/spouse/
joint/dependent labels if present) is retained as `quiver_subholding`; it does not establish an
economic owner or household. Ownership remains explicitly unknown. No Owner field is documented
in these reviewed schemas; such an extra field is retained/quarantined without inventing semantics.
Party, chamber, district, state, asset-type, position status and lobbying issue labels remain
explicit vendor assertions rather than system classifications, conclusions or eligibility features.

## Identity, evidence and reconciliation

BioGuideID can create a source-asserted canonical person and evidence-specific identifier claim
under `us.congress.bioguide`. Its opaque UUID uses the immutable typed ID; names never identify
people or households. Existing exact source-backed bindings require persisted subjects, provenance,
observations and verified raw hashes. Conflicts fail; primary names/aliases/provenance stay unchanged.
Ticker is only a hint. No issuer/security/listing identity is inferred, even if a current ticker matches.

The four documented row schemas expose **no native transaction/award/filing row IDs or primary
document URLs**. Unknown extra identifiers/links are retained in quarantine/raw pending a reviewed
schema extension. The request identity names a captured response, not a source-native economic event.
Row indices are capture coordinates only; normalized fact hashes are comparison tools only. Neither
becomes a permanent event ID. Equal-valued rows remain separate and countable. Reordering/pages
can add response observations without creating or collapsing canonical economic events.

Default rows therefore have unresolved underlying-event identity and create no canonical Event.
An explicit `ReviewedRowLink` can associate a capture hash/row coordinate with an existing primary
canonical Event, primary observation, review time and review reference. This is a recorded operator
decision, **not** automated identity matching from dates, amounts, names or tickers. The primary
observation/raw hash, primary EventEvidence, provenance and underlying source family must exist.
Different rows cannot silently map to one event within a response. Contradictory type, supported
occurrence, amount/range/currency/unit or source-backed actor facts fail.

Identity comparisons apply only to the explicit primary `reporting_lawmaker` actor role.
The row's named lawmaker is not assumed to be a transaction_owner, economic owner or generic
filer. Separate primary owners/economic units remain unchanged; absence of a compatible reporting
role is not a contradiction. Subholding does not create an owner or family relationship.

Cross-source compatibility compares normalized financial facts and supported temporal components,
not source-specific raw date/range text or parser versions. Unknown precision or missing bounds
are never coerced to manufacture a match. Raw representations remain independently staged and
the stronger primary Event stays byte-for-byte unchanged. New EventEvidence rows link the vendor
observation by event_id; query the evidence table for all supporting observations, since the Event's
initial evidence-reference tuple is frozen. Provenance retains primary parents and review timing.

Underlying families are conservative internal categories: us.congress.disclosures,
us.government.procurement and us.government.lobbying_disclosures. The schema alone does not prove
that a particular procurement row came from USAspending or that a vendor row uniquely matches an
official filing. Unresolved linkage never gains an independent vote. The canonical-only
independent_primary_families helper counts primary families supporting one event; normalized copies
add no primary support. Existing SEC/vendor evidence regressions remain intact, and a simulated
primary-government-plus-Quiver-copy end-to-end test retains one event/one primary family.

## Persistence, corrections and restricted retention

Retrieval, immutable capture, strict parsing, observation/provenance, canonical mapping and
publication have separate boundaries. Same-byte replay reuses first-seen observation and frozen
mapping decisions, including unresolved status after later catalog enrichment. Different raw
responses coexist as snapshots. New observation/evidence does not overwrite a primary Event.
Changed allowlisted facts for an already linked event within the same endpoint fail explicitly
for reconciliation and retain new raw bytes. Unknown/performance or audit-clock-only changes do
not rewrite canonical facts. A source without native IDs cannot automatically identify unlinked
row revisions: those remain separate unresolved evidence, not guessed corrections or signals.
Changing an accepted snapshot's reviewed links also requires a separate reconciliation workflow.

Synthetic mode uses quiver.synthetic/INTERNAL/invented-test-data. Real mode requires an explicit
QuiverAccessReview containing the actual agreement fingerprint/review time, endpoint entitlement,
local raw/derived retention permission and a non-sync/shared-storage attestation. All persisted
state must be outside Git worktrees and known sync locations, including OneDrive. These checks
supplement the operator's contract review; they cannot independently establish entitlement or
detect every sharing system. Current applicable agreement/entitlement remain unestablished, so
no real capture is authorized by this work. Restricted derivatives remain private with raw data.

Real observations are RESTRICTED; license-review fingerprint and parser/adapter/transform versions
remain in the bundle. Credentials are headers only, never request parameters/manifests. Known
credential-bearing inputs and echoed credentials are rejected before capture; network errors are
redacted. Raw objects/manifests are immutable. Atomicity is per file; conflict preflight precedes
analytical writes, single-writer use is required, and there is no cross-file transaction. Frozen
bundles can recover their own interrupted datasets; external primary/identity dependencies must
be restored from their original captures.

No canonical model/schema bump or migration is introduced. New adapter staging schema1.0.0
uses existing canonical envelopes and generic curated datasets. DuckDB remains rebuildable.

## Local entry point and live smoke

```text
uv run ragged-claws ingest-quiver-fixture tests/fixtures/quiver/invented-contracts.json --endpoint contracts --source-url "https://api.quiverquant.com/beta/live/govcontractsall?page=1&page_size=20" --synthetic --data-dir data
```

This offline command requires an explicit invented-data attestation and reports snapshot ID,
row/mapping/reason counts, missing dates, unresolved subjects/security and zero emitted predictive
features. It is not a licensed-record importer, resolver or performance report. Accepted replay
reports original frozen mapping statuses, not a new-write count.

Default tests never call vendor endpoints. The optional test requires explicit
RAGGED_CLAWS_QUIVER_LIVE=1 plus QUIVER_API_TOKEN, QUIVER_AGREEMENT_REVIEW_PATH and
QUIVER_PRIVATE_DATA_ROOT. The latter must be private/local; the review JSON must describe the
actual applicable agreement/entitlement, not website terms alone. The HTTP helper makes one
supported request with no redirects/retries/challenge handling. This optional path was **not run**.

Remaining operational/research dependencies: user-established access and actual agreement review,
source payload validation, defended primary-event reconciliation and historical identity/price
coverage, then predeclared real-data validation. Synthetic tests establish engineering behavior,
not licensed access, historical signal availability, returns, alpha or funding readiness.
