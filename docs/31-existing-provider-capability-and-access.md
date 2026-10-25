# Existing Alpaca and Quiver capability/access decision

**Proposal; not preregistered; not evaluated; acquisition_authorized=false.**
The [decision card](../research/identity/existing-provider-capability-v1.json) pins the retained
schema, code, tests and prior decisions. Reviewed documentation does **not establish the complete
historical identity chain** required by docs14/28/30. It does document potentially useful reference
assertions; those should not be mistaken for continuous class/Listing validity or historical knowledge.
No provider data, prices, outcomes, accounts, credentials, contact or private configuration contents
were requested/read. No production, fixture, model, schema, dependency or engine change.

**One next action for supervisor review:** obtain a secret-free confirmation of the existing paid
Quiver product's REST API entitlement and applicable API agreement for the existing `contracts`
adapter. That missing user-specific evidence blocks a lawful adapter validation. No data probe is
justified or specified now; this is not another insufficient filing/mapping collection.

## Contract that remains unchanged

Issuer, strong Security/share-class identifier and venue Listing are distinct. Require an explicit
issuer/class association, permanent listing basis, dated venue evidence and independently reviewed
operating/segment MIC relation. Require supported half-open valid segments covering every elapsed
event-to-exit session, including transitions and terminal treatment. A current symbol/exchange,
opaque provider UUID, two matching covers or absence of an action cannot fill unknown bounds.

Public/known time, validity, collector observation and later derivation remain separate.
Retrospective price-label repair does not establish historical predictive eligibility, actual
collector possession or a decision at a past open. Prospective eligibility additionally depends
on actual timely receipt and a reviewed policy. No architecture relaxation is proposed.

PR34's SEC plan was accepted as documentation/insufficiency; its four-GET chain was declined for
execution. It must not be implemented or acquired here. BAC's separate one-POST budget remains0;
444primary/1nonnullshareclass/120composite candidate values do not bridge history. Earlier3BAC events,
the newer9sales/0purchases/3event issuers and unresolvedSPY remain distinct. Powell remains a valid
zeroP/S body;3exclusions,9unresolved Security/Listing and4unresolved owner occurrences remain visible.
The486uncollected groups and second index remain unknown. None validates a purchase strategy.

## Public sources actually reviewed

Current public pages below were read October25,2026UTC. Links identify documentation, not authority
to call their example endpoints. No linked data or authenticated interface was followed.

| Official source and sections read | Documented capability and limitation |
| --- | --- |
| [Alpaca Historical bars](https://docs.alpaca.markets/us/reference/stockbars), overview and query parameters `start/end/limit/adjustment/asof/feed` | Symbol aggregates with explicit adjustment and symbol-as-of mapping; predecessor-symbol bars may be relabeled. This helps price-label retrieval after identity review, not permanent class/venue or historical knowledge. |
| [Alpaca Corporate actions](https://docs.alpaca.markets/us/reference/corporateactions-1), overview/warning, `symbols/cusips/types/start/end/data_quality` and pagination | Action identifiers/dates can support later reviewed transition evidence. Queries use process-date bounds; availability can be delayed. Default “complete” can omit unprocessed incomplete records and still include processed incomplete ones. Absence proves neither no transition nor exhaustive terminal coverage. |
| [Alpaca Market Data](https://docs.alpaca.markets/us/docs/about-market-data-api), Subscription Plans/Trading API Equities | Advertises Basic IEX real-time and equities history since2016. These are neither this user's entitlement/retention rights nor empirical historical completeness. No upgrade is proposed. |
| [Alpaca documentation index](https://docs.alpaca.markets/us/llms.txt), Assets navigation | Describes a master list available for Alpaca trading/data. Detailed asset-reference pages were unavailable in this review; UUID permanence, historical versions and interval semantics remain unverified, not inferred. |
| [Quiver API pricing](https://api.quiverquant.com/pricing/), Hobbyist dataset/MCP/noncommercial labels | Advertises Congress/contracts/lobbying and10of18MCP tools. It does not establish that the user's paid product includes API access, exact REST endpoints, equivalent MCP contracts or retention permissions. |
| [Quiver terms](https://www.quiverquant.com/termsofservice/), sections5/6 and24Entire Agreement, modifiedJune25,2026 | Website retention/derivative and redistribution restrictions must be distinguished from the separate purchased API License Agreement. The applicable user agreement has not been reviewed; no permission follows from advertising or a software attestation. |
| [Quiver API Setup](https://www.quiverquant.com/api-setup/), Step1 and Step3's documentation/authentication explanation | Identifies the API service and key workflow. Its payment demo, packages and data-request examples were not followed. This supplies a safe reference for checking an existing API product, not permission to subscribe or run code. |

The public Quiver docs page yielded no readable body; no login/access workaround was attempted.
Use the exact retained [official OpenAPI schema](https://api.quiverquant.com/docs/schema.json):
OpenAPI3.0.3/APIv1,238,296bytes, retrieved2026-10-22T22:13:44.310511Z,
SHA256`72b5c480c44494371c318c88072319795bf8440600998d81d297b5cd3de17af2`.
Its acquisition record and reviewed file remain external and immutable. This is an explicitly dated
contract review, not a claim that today's schema, user entitlement or live payload was revalidated.
Unavailable asset/doc URLs and exact reviewed sections are recorded in the card.

## Historical reference capability: useful pieces, incomplete chain

The broader retained Quiver schema contains relevant fields beyond the four implemented endpoints:

- `DailyPrice` at `/beta/historical/dailyprices/{ticker}` documents dated ticker rows, optional
  `ShareClassFIGI`/`CompositeFIGI`, and action labels including ticker changes. Only `Date`/`Ticker`
  are required. This could supply retrospective class/composite candidates, not an authenticated
  issuer association, permanent venue Listing/MIC, explicit continuous intervals, historical known-time
  or guaranteed delisted/terminal coverage. No price response was requested or inspected.
- `EarningsDistortionScore` at `/beta/live/earningsdistortionscores/{ticker}` includes current and
  event-date CIK/exchange/MIC, generic `figi`/`perm_id`, `event_date` and client-publication text.
  It is a separate ratings-product schema, not an exhaustive securities-transition master; FIGI
  layer, permanent-ID subject, interval semantics and this user's rights remain unsupported.
  A ratings-data revision date is not automatically a listing-effective or primary-public timestamp.
- `SEC13FEntry` has CUSIP/period/class assertions, still discrete holdings evidence. The schema's
  `/beta/tickerdata` is explicitly internal; it is no public-access fallback. No new dataset importer,
  third provider, paid product or expanded query is proposed.

It would be inaccurate to say Quiver has no reference identifiers. The narrower conclusion is that
the reviewed documentation does not establish the **whole unchanged contract** for these issuers/SPY.
Optional fields, advertised coverage and a current successful answer would still need authenticated
subject/layer/venue, timing, transitions and empirical completeness. No hypothetical successful
response, merger, delisting or successor is asserted.

Existing `AlpacaHistoricalBarsAdapter` retrieves1Day bars with page lineage; `DailyBarRequest`
already requires canonical Security/Listing UUIDs, one historical symbol segment, valid bounds,
explicit in-segment `provider_asof`, adjustment and feed. It consumes identity; it does not create
it. There is no existing assets/corporate-actions importer. Vendor symbol mapping cannot bypass
that contract. Stock/benchmark price and terminal completeness remain separate prerequisites.

## What the existing Quiver adapter can validate for #9

| Existing selector / GET path | Supported fields and timing boundary |
| --- | --- |
| `congress_v1` / `/beta/live/congresstrading` | `TransactionDate` occurrence and `ReportDate` report calendar day; `Amount` lower bound and raw `Range` where supplied; `last_modified` vendor curation. Code accepts no query and caps500rows, so it is not a one-row probe. |
| `congress_v2` / `/beta/bulk/congresstrading` | Exact `version=V2`, explicit page/page_size; `Traded` occurrence, `Filed` disclosure day, `Quiver_Upload_Time` processing and `last_modified` curation. `Trade_Size_USD` lower bound; `Subholding` verbatim vendor assertion. |
| `contracts` / `/beta/live/govcontractsall` | Explicit page/page_size; `Date` announcement day distinct from `action_date`; `Amount` obligated dollars. Agency/description are sourced context, not identity or a market signal. |
| `lobbying` / `/beta/live/lobbying` | Explicit page/page_size; `Date` reported-spending day, no documented activity period; `Amount` reported spend; issue labels remain vendor classifications. |

The latter three code contracts accept page>=1/page_size1..100, with no automatic pagination or
extra query keys, although the public schema offers broader parameters. All four schemas lack
native economic-row IDs and primary filing/award URLs. Response request/raw hash identifies a
SourceObservation; row index is a capture coordinate, fact hash a comparison tool. Default rows
remain unresolved and create no economic Event. `ReviewedRowLink` needs the exact raw/row and an
existing primary Event, observation, evidence/provenance and review reference. A normalized copy
adds evidence, never another independent primary-family vote.

Date-time schema labels do not manufacture intraday publication. Preserve raw values and documented
calendar-day meaning; upload/curation/observed time cannot substitute for original public time.
Unknown public_time/known_from/actionability stay null; primary event timing remains unchanged.
BioGuideID refers to the reported lawmaker, not automatically the owner. Subholding text does not
merge self/spouse/joint/household identity; no reviewed `Owner` field exists in this subset.
Only allowlisted facts reach canonical models. `ExcessReturn`, `PriceChange`, `SPYChange`,
`excess_return` and every unknown/nested future metric remain in restricted raw/staging quarantine,
never features. New identifier/link fields also need review before interpretation. Engineering
tests prove these boundaries with invented data, not real entitlement, publication latency or alpha.

## Actual access and the one next step

Direct human facts supersede the old no-account sentence in doc17, which remains historical:
signed in to Alpaca/Cloudflare/Quiver; paidQuiver only; no further setup confirmed. Actual API
product/plan, endpoint entitlement, accepted agreement, key readiness and raw/derived/cloud rights
remain unverified. REST schemas and advertised MCP tools are not interchangeable contracts.

Authorized existence/type checks only: the known `alpaca.env` is absent; `alpaca.env.example` is a
regular file under `C:/Users/kcbni/AppData/Local/RaggedClaws/secrets/`. No contents or other paths
were searched/read. This does not establish absence of credentials elsewhere or account entitlement.
No Quiver key location was inspected, and no template, credentials or `QuiverAccessReview` was created.

**For the supervisor's later request, obtain one access-confirmation packet:** whether the existing
paid product is Quiver **API** access for `/beta/live/govcontractsall`, and the applicable API license
basis for local raw and derived retention. This advances #9 adapter-contract feasibility, not historical
identity or investment validation. No human question is sent during this assignment.

Secret-free setup sequence for that single review:

1. Using the existing service and [official setup reference](https://www.quiverquant.com/api-setup/),
   the human checks the current product/plan label and REST entitlement. Do not enroll, upgrade,
   enter payment or purchase anything. Consumer-only/no included API access means blocked; stop.
2. Make the applicable API license/retention clauses available for private review outside Git/OneDrive,
   without credentials or account identifiers. The reviewer must establish actual endpoint entitlement
   and raw/derived retention; website terms or a checked software box do not supply those facts.
3. Only after that review and separately approved credential setup, keep an existing key locally in
   an approved secret store/process environment outside Git/OneDrive; existing code expects
   `QUIVER_API_TOKEN`. Confirm readiness without posting its value. No key generation/rotation,
   new credential file/template or live smoke is requested now.

The existing model requires actual `agreement_sha256`, `reviewed_at`, `entitled_endpoints`, and
justified literal-True `local_raw_retention_permitted`, `local_derived_retention_permitted`,
`root_is_not_synced_or_shared`. A valid JSON object grants no rights. All these prerequisites and
explicit live authorization remain unresolved; do not create a fake review from pricing claims.
The existing HTTP helper's post-buffer5MB check is not a predeclared streaming/header/global receipt
budget. Any later tiny data validation needs a new reviewed exact scope/caps/privacy/clock/stop
contract; no automatic probe or pagination follows this access decision.

Stop for independent review. Issues9/10/15 stay open. No acquisition, price/outcome inspection,
registration, inference/calibration, paper/forward clock, cloud/runtime/schedule, charge, funds or
order. Scientific methods, untouched validation, surviving signal, source/benchmark/terminal coverage,
real elapsed forward evidence, durable failure audit and pilot/funding gates remain unmet. November
capital plans establish neither a readiness date nor deployment authority.
