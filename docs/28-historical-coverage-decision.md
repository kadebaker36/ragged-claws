# Historical identity and source-access coverage decision

**Decision: keep historical event/benchmark bindings unresolved; propose one anonymous BAC
CUSIP-to-FIGI candidate probe, not acquisition permission.** The versioned
[decision card](../research/identity/historical-coverage-v1.json) binds retained source hashes,
all Event IDs, provenance and dates. The separate
[request declaration](../research/identity/bac-openfigi-proposal-v1.json) has
`acquisition_authorized=false`. No production code, canonical identity/Event, control, Outcome,
snapshot, ResearchBuild or price data is created. #9/#10/#15 stay open.

## Retained scope and requirements

| Body reference | Body issuer CIK / name | Raw symbol / class metadata | P/S Events |
| --- | --- | --- | ---: |
| 0000035527-24-000224 | 0000035527 / FIFTH THIRD BANCORP | FITB / Common Stock | 2 |
| 0000060086-24-000179 | 0000060086 / LOEWS CORP | L / Common Stock | 6 |
| 0000080420-24-000066 | 0000080420 / POWELL INDUSTRIES INC | POWL / Common Stock | 0 |
| 0000101778-24-000120 | 0000101778 / MARATHON OIL CORP | MRO / Common Stock | 1 |

These are nine sales, zero purchases from three event issuers; they do not validate a purchase
strategy. Powell is a successfully parsed zero-event filing, not missing evidence. Exact excluded
rows are Fifth Third nonDerivativeTransaction[3], codeG; Loews nonDerivativeHolding[7]; Powell
nonDerivativeTransaction[1], codeF. The card preserves coordinates/reasons and raw hashes.
Four reporting-owner occurrences and all nine Security/Listing bindings remain unresolved.
The other486of490Form4reference groups and the second index remain uncollected/unknown.
Neither P/S codes nor reported transaction prices prove venue, market quotes, currency/amount,
affordable size or fills. Symbols/title strings identify no permanent Security or Listing.

| Existing source Event ID | Accession | Source transaction row | Code |
| --- | --- | ---: | --- |
| `5107e231-7210-502d-b1cb-7f5a88a3c9d6` | 0000035527-24-000224 | 1 | S |
| `8814055a-cfed-5d5c-bc30-b98205cbd1ea` | 0000035527-24-000224 | 2 | S |
| `9b0e8778-d275-597b-b342-4e80e645275b` | 0000060086-24-000179 | 1 | S |
| `e706c178-27b7-5f09-a967-3bdf83edd6dc` | 0000060086-24-000179 | 2 | S |
| `52e8553a-c4f1-50b3-aa2d-b8d56bb9d113` | 0000060086-24-000179 | 3 | S |
| `20a2c166-1140-533e-854f-95c412987af9` | 0000060086-24-000179 | 4 | S |
| `23b2cf65-776b-5fd1-a6f4-5301aca0c5c5` | 0000060086-24-000179 | 5 | S |
| `e28a9169-3014-5199-8ef7-348875443294` | 0000060086-24-000179 | 6 | S |
| `4b33a28f-022e-5e29-8415-31b835cbbc9e` | 0000101778-24-000120 | 1 | S |

Each card row references its original EventEvidence/SourceObservation/provenance IDs and raw body.
Issuer CIK claims remain separate from class identity. Existing identifier `known_from` nulls are
preserved. Filings retain raw/UTC acceptance with second precision, official filing and occurrence
dates with day precision,2026observation/retrieval clocks and the existing acceptance+five-minute
availability assumption. Class/listing valid bounds and historical known time remain unknown;
first-ever collector receipt, actual historical decision and policy entry remain unknown/null.
Current reconstruction cannot manufacture collector possession or an eligible2024decision feature.

All nine source-label entries are September11,2024at13:30UTC; entry is session0:

| Horizon after entry | Required exit close UTC | Required date coverage, half-open |
| ---: | --- | --- |
|20|2024-10-09 20:00|[2024-09-11,2024-10-10)|
|60|2024-12-05 21:00|[2024-09-11,2024-12-06)|
|90|2025-01-22 21:00|[2024-09-11,2025-01-23)|

These are hypothetical support requirements from locked exchange_calendars4.13.2/XNYS, not
observed positions, elapsed forward evidence or completed outcomes. Resolve the union of dated
Listing segments across every elapsed session, then require usable entry-open/exit-close data and
honest missing/censored/terminal accounting. Powell has no P/S horizon requirement; its source
class remains in the diagnostic. SPY is an **unresolved benchmark label**, requiring independent
fund/issuer/class identity, Listing, MIC, intervals and compatible price provenance. No SPY UUID,
CUSIP, venue or assumed history is created from its ticker.

For each issuer's common-class requirement and benchmark, the shared card contract requires:

- Strong sourced permanent class identity tied to issuer, and instrument/venue Listing identity or
  a separately reviewed permanent creation basis; neither CIK nor title/name/symbol suffices.
- Dated official venue evidence and a reviewed operating/segment MIC mapping. OpenFIGI exchCode
  and a country/market composite are not interchangeable with a MIC or a venue instrument.
- Explicit half-open valid intervals covering entry through each elapsed exit, class/symbol/venue
  transitions and sourced effective/known/observed timing. Equal covers at two dates do not bridge
  the intervening interval. Unknown endpoints must not become unbounded Listing convenience.
- Source evidence for termination, merger or successor terms before terminal classification.
  No actual transition or delisting is asserted here. A missing bar is missing evidence, never
  delisting proof or an invented zero/-100%/last-price return.

The present outcome engine requires explicit `listing_history` for successor bindings. It permits
reviewed same-Security symbol segments on a compatible MIC, not arbitrary venue transfers or
different-Security corporate actions. The legacy external test that omitted history remains a
preserved failed artifact; no inference from bar UUIDs, outcome fix or retroactive green claim.

## Source capability, rights and access decision

Eight official documentation pages were read October24,2026UTC; sections and dates are in the
card. Existing SEC Form4/identity reviews in docs14/15/22 are reused, not new filing retrievals.

| Source / primary documentation | Capability and rights basis | Decision and limit |
| --- | --- | --- |
|[SEC access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), Fair access/paths/corrections; retained docs15/22 public-filing reuse basis|The retained filings establish sourced issuer/class/title/symbol/date assertions, including BAC's separate CUSIP/cover evidence. Public SEC filing reuse does not grant vendor-data rights.|No class/listing interval, transaction venue, continuous coverage or original historical-byte guarantee follows. No new SEC data requested.|
|[OpenFIGI API](https://www.openfigi.com/api/documentation), mapping/jobs/fields/rate limits|Anonymous mapping supports typed input and FIGI candidates, warning/error states and unlisted-equity inclusion. Published anonymous limit is25requests/minute;10jobs/request.|No historical-validity parameter. A current result is a new observed assertion; retain all candidates, absent values and provider failures.|
|[Overview](https://www.openfigi.com/about/overview), Permanent/metadata; [Equity allocation rules](https://www.openfigi.com/about/allocation-rules)|Permanent identifiers have distinct share-class/global, composite/market and venue/instrument levels; metadata can change. Listed-fund hierarchy is also documented.|A composite is not a unique venue Listing. Persistent identifiers after delisting do not date a terminal event or authenticate a past interval.|
|[Terms](https://www.openfigi.com/docs/terms-of-service),1/3/6; [FAQ](https://www.openfigi.com/about/faq), third-party identifiers/Usage and Fees|FIGI identifiers are reusable; FAQ describes symbology/metadata as open. Third-party proprietary identifiers have separate restrictions; accuracy is not guaranteed.|Do not extend this to all third-party data or endorse bulk redistribution. Proposed exact request/response stays private for review; no Git/cloud export is proposed.|
|[Alpaca bars](https://docs.alpaca.markets/us/reference/stockbars), request fields/401/403|Documents daily aggregation, inclusive bounds, pagination, feed, adjustment and symbol `asof`; `asof` performs provider symbol mapping.|This is not a historical class/Listing validity certificate. Existing adapter needs reviewed canonical segments, explicit in-segment `provider_asof`, feed/adjustment and page lineage.|
|[Alpaca plans](https://docs.alpaca.markets/us/docs/about-market-data-api), Trading API/Equities|Advertises equities history since2016 and plan/feed differences; Basic real-time equities are IEX.|Availability is not completeness, terminal coverage or this user's entitlement. No plan, accepted agreement, local retention/derivative, cloud or redistribution permission is authenticated here.|

For later price work, preserve each request's exact Listing, bounded historical symbol interval,
provider `asof`/feed/adjustment, raw page hash and actual observation. Audit stock and benchmark
entry/exit, transition and terminal gaps separately. HTTP401/403, transport/limit failure, provider
error, no-result and unknown completeness remain distinct. Never filter to today's active universe
or infer terminal treatment from an empty response. Private local retention is separate from
cloud/redistribution rights; actual agreement review is a prerequisite, not assumed permission.

Current human facts supersede old no-account text: signed in to Alpaca/Cloudflare/Quiver, paid
Quiver only. Exact API plan/agreement/entitlement, key readiness, bucket/retention/derivative/cloud
rights and setup remain unverified. The setup guide is pending, not proof of ready keys. Supervisor
needs actual feed/agreement/allowed-use confirmation and private scoped key-readiness confirmation
before later Alpaca data; no secret values or already-known email are requested. The chosen
anonymous OpenFIGI probe needs neither those keys nor another subscription. USD250October and
500/month change affordability questions, not validation or authority to invest.

## One bounded next action

Choose the **separate BAC diagnostic**, not a merge into these nine sales. Retained13G/A accession
0001104659-24-020016 asserts CIK0000070858, Common Stock and CUSIP060505104 at verified byte
span[2704,2713), SHA252953852009256b2506304a8c213db7791243b5f6b524b4d271dda4897d6f71.
The dossier already has one CUSIP-based candidate; it has no defensible spanning Listing or event
binding. This is the sole retained strong class identifier, making a one-job probe smaller and less
assumptive than ticker mapping or a new SEC discovery sequence for all four issuers/SPY.

Proposal: **one anonymous POST** to `https://api.openfigi.com/v3/mapping`, exact76-byte body:

```json
[{"idType":"ID_CUSIP","idValue":"060505104","includeUnlistedEquities":true}]
```

No discovery stage or unknown URL is needed. Verify bound evidence hashes, issuer/class/CUSIP span
and request-body hash before the request. No guessed FIGI/CUSIP, MIC/currency/live-listing filter,
enum request or ticker search. Including unlisted equities initially avoids a second request and
today-active-only filter. Multiple instruments may share one class; retain all and never select the
first. Even a unique result establishes only a current candidate linkage; historical validity,
venue/MIC, event binding and benchmark/price coverage remain unresolved. It cannot establish any
of the new nine Event bindings or validate a return hypothesis. No API result is fabricated here.

Exact caps:1request/1POST/0GET/1job/1attempt;512request-body bytes,1MiB response entity,
16KiB response headers,64KiB receipt,1,114,112retained entity+receipt bytes maximum. Serial minimum
3seconds between starts and prior finish<=next start;30second timeout; no redirects/retries or
substitutions. Stop globally on any denial/429/transport/challenge/oversize/privacy/invalid-shape
or reference contradiction. Completed no-result/ambiguous output also exhausts this scope. No
automatic retry suggested by provider docs is adopted. Incomplete capture is unknown, not absent.

Use a fresh private non-sync AppData directory, immutable content-addressed exact bytes and an
honest attempt/finish/status/hash/size/completeness receipt. No credentials/cookies/actual contact
or config discovery; no private headers/exception text in public metadata. Blocked bytes remain
private and public replay rejects before output. Retain all error/no-result/candidate distinctions.
Existing capture_raw_bytes/RawCaptureManifest/SourceObservation lineage and pure
`parse_openfigi_mapping_response` can consume a later reviewed capture; there is no existing live
OpenFIGI client. Any future bounded capture requires separate implementation review/authorization.
Typed identifier helpers/IdentityCatalog cannot apply a Listing or claim until subject, layer,
venue, intervals and knowledge are independently defensible. No new source allowlist or client now.

**Single next action:** supervisor review the decision and exact proposal; only a later explicit
authorization can permit that one anonymous request. This work order authorizes documentation
review only and has made zero data requests. Existing raw/Parquet, scopes/declarations/flags,
receipts/failures/probes/handoffs and histories remain immutable. Scientific design/untouched
validation/surviving signal, actual identity/price/terminal coverage, elapsed forward evidence,
operational durability and pilot/funding gates remain unmet. No acquisition, outcome/inference,
registration, paper/forward clock, cloud/runtime/schedule, charges, funds or orders are activated.
