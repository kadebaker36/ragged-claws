# Fifth Third historical identity: bounded SEC proposal

**Decision: insufficient for historical identity; acquisition is not authorized.**
The [versioned proposal](../research/identity/fifth-third-sec-identity-proposal-v1.json)
defines one possible later locator-to-filing diagnostic. It neither declares an acquisition
nor supplies a defensible complete class/Listing chain. Review this plan before deciding
whether its limited evidence value warrants a new declaration and implementation. No source
data, prices or outcomes were requested for this planning slice; only two official documentation
pages were read. No importer, canonical record, binding, schema or existing artifact changed.

## Fixed case and retained evidence

Choose the first source-ordered nonzero issuer in the accepted four-body capture, independently
of outcomes: Fifth Third Bancorp, typed issuer CIK `0000035527`, accession
`0000035527-24-000224`. This is a deterministic diagnostic, not representative sampling or an
investment preference. The retained 7,359-byte body has SHA256
`201da8f67532cb538c386bf6172dc6eb4cb77ff1b8a3603b7384e314aee12523`.

| Source row in `wk-form4_1725999144.xml` | Event | EventEvidence |
| --- | --- | --- |
| `nonDerivativeTable/nonDerivativeTransaction[1]` | `5107e231-7210-502d-b1cb-7f5a88a3c9d6` | `de31967e-477f-5f4b-afdd-0cc972de9864` |
| `nonDerivativeTable/nonDerivativeTransaction[2]` | `8814055a-cfed-5d5c-bc30-b98205cbd1ea` | `e47bbe96-bbbe-5f7d-9e0e-9a69ceb596e9` |

Both are `S`, occurrence date September9,2024, title `Common Stock`. Row3 is an excluded `G`,
never a third sale. Both retain issuer Entity `271534d6-e26a-562d-9e64-c15b168a60e8`,
SourceObservation `1ba4b1c8-d002-5821-87d9-49b6ad0a5c70`, and Provenance
`7fd35c44-8bcd-5683-9393-8cb4a25af7e6`. No Security/Listing is resolved from `FITB`, title or CIK.
The card pins the original scope, reference context, receipt, body and accepted coverage card.

Raw acceptance `20240910161231`, America/New_York, becomes source time
`2024-09-10T20:12:31Z`. Official filing date remains September10. The unchanged acceptance+5minute
**assumption** yields20:17:31Z and source-label actionability September11at13:30Z. Actual recorded
retrieval is `2026-10-24T09:51:40.342160Z`; first historical collector receipt, actual decision and
policy entry remain unknown/null. Reconstructing identity now cannot create an eligible 2024
feature, historical possession or an actual decision.

Entry is session0. Existing hypothetical requirements remain:

| Sessions after entry | Exit close UTC | Required half-open date coverage |
| ---: | --- | --- |
|20|2024-10-09 20:00|[2024-09-11,2024-10-10)|
|60|2024-12-05 21:00|[2024-09-11,2024-12-06)|
|90|2025-01-22 21:00|[2024-09-11,2025-01-23)|

The newer slice remains9sales/0purchases from3issuers, Powell valid zeroP/S,3excluded rows,
9unresolved Security/Listing bindings and4unresolved owner occurrences. The486uncollected groups
and second index remain unknown. Those sales do not validate the proposed purchase strategy.
Earlier3BAC events remain separate; its one request is exhausted. Its444primary candidate values,
1nonnullshare-class value across443rows and120composite values establish no historical continuity.

## Claim contract before any retrieval

CIK identifies an issuer. A class requires a strong sourced permanent identifier tied explicitly
to that issuer/class. A venue Listing additionally needs an instrument identifier or separately
reviewed permanent creation basis, dated official venue evidence and an independently reviewed
operating/segment MIC relation. Exchange text alone supplies no MIC.

Require explicitly bounded half-open valid segments covering every elapsed entry-to-exit session,
including supported class/symbol/venue transitions and terminal facts. A gap, overlap, conflicting
class or unknown boundary stays unresolved. Neither one annual cover nor matching covers at two
dates proves uninterrupted validity. Do not turn an unknown end into an open-ended Listing.
Retain source-public precision, valid time, collector-observed time and later derivation/review
time separately. A retrospective identity repair cannot enter historical predictive features
without defensible historical known-time; actual collection/decision eligibility remains separate.
Missing symbols/prices never establish merger, delisting, successor or a terminal return.

## Official documentation actually reviewed

Read October24,2026UTC:

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces):
  introductory access paragraphs, **data.sec.gov/submissions/** and **Update Schedule**. This
  documents a ten-digit CIK endpoint, current metadata, recent columnar history and additional
  files/date ranges. It does not provide a complete formal field schema or historical identity
  certificate. Exact field guards below are this proposal's acceptance contract; changed shapes stop.
- [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data):
  **Fair access**, **Business hours and dissemination**, **Post-acceptance corrections and deletions**,
  **CIK**, **Paths and directory structure**. These support declared-contact moderation and filing
  path construction; accession prefixes may belong to filing agents. Current archives can reflect
  corrections. Current bytes/metadata are not proof of unchanged original historical bytes.

No data links on those pages were followed. No new filing, index, submissions, companyfacts,
search-result data, mapping, provider, asset or price response was fetched. An unavailable SEC
search-user-guide URL was attempted as documentation only and is not cited or relied upon.

## One proposed future chain, at most four GETs

1. Start only at `https://data.sec.gov/submissions/CIK0000035527.json`. Require exact typed CIK,
   `filings.recent` columnar arrays and `filings.files` descriptors. Preserve current symbols and
   exchange metadata only as current assertions. Validate equal required array lengths, ISO dates,
   order, safe identifiers, duplicate/conflict rules and bounded JSON depth.
2. Fix the desired filing before retrieval: exact `10-K`, filed January1–March31,2024 inclusive,
   report date December31,2023, issuer35527. No amendments, later annual report or alternate form.
   Use recent only when it spans that entire date window and no historical descriptor overlaps it.
   Otherwise recent must contain zero window rows and begin after March31. Only then may exactly
   one historical descriptor intersect **and fully enclose** the entire window. Validate returned
   `name`, positive `filingCount`, `filingFrom` and `filingTo`; zero matches stops no-result, partial
   or overlapping/multiple matches stop without a request. The basename must fullmatch
   `CIK0000035527-submissions-[0-9]{3}\.json`; append the exact returned name to the submissions root,
   never invent an ordinal. Fetch at most that one file, validate counts/ranges and select exactly
   one qualifying accession. No recursive history, merging partial sources or choosing latest/first.
3. Build the selected accession's documented filing-index URL under
   `https://www.sec.gov/Archives/edgar/data/35527/`, with suffix `-index.html`. Verify issuer, form,
   accession, filed/report dates and the unique `10-K` document row against returned metadata.
   Do not require the accession prefix to equal the issuer CIK. Missing/conflicting evidence stops.
4. Fetch exactly the metadata `primaryDocument` basename confirmed by that index, under the
   same CIK and dashless-accession directory. Safe HTTPS path/host and basename rules forbid
   traversal, query, fragment or alternate document. Select exactly one cover registration row
   whose inline `Security12bTitle`, after whitespace/case normalization only, equals `Common Stock`.
   Qualifiers, missing inline facts or ambiguity stop; no substring or title-to-class inference.
   Capture exact raw bytes and reviewed field spans before interpretation. Other classes stay distinct.

The card contains the exact structural and URL guards. No accession, archive ordinal or primary
filename is guessed here. This deliberately narrow annual selector may miss useful evidence;
that is an explicit no-result/unsupported outcome, not authority to widen it. Even a found strong
identifier or cover venue is a discrete assertion. If permanent Listing/MIC/continuous intervals
are unsupported, return **insufficient** and stop after this one chain. No attachments, second
annual filing, current ticker lookup, provider fallback or additional evidence requests follow.

## Bounds, reusable components and authority

Proposed caps, not current permission:4GETs/0POSTs, one attempt/resource, serial finish before
next start and at least1second between starts. Per-stage entity caps:1MiB submissions,2MiB optional
history,256KiB index,16MiB primary; total20,185,088bytes. Each response permits16KiB parsed header
fields (64KiB total). All checkpoints/receipts/manifests together permit256KiB; reports together1MiB.
Raw+metadata retention is20,447,232bytes; including reports21,495,808bytes. Raw entity objects are
counted separately from metadata, never hidden or double-counted. No header values/contact/exception
text enter public receipts. These are entity/parsed-field limits, not total TLS/wire bounds.

Future implementation must enforce45second stage and240second whole-run application deadlines,
including throttling/interpretation,15second I/O timeouts and30second report processing. I/O timeout
alone is insufficient. No redirects/retries/substitutions. Denial/rate limit, transport/deadline,
challenge, privacy, oversize, incomplete/invalid shape or pin/context mismatch globally stops.
No-result/ambiguity/partial consume the attempt; unused stage capacity is neither transferable nor
renewable. Record unattempted, interrupted, denied and incomplete separately from complete empty.
Use fresh private non-sync AppData storage, exact content-addressed bytes/manifests and immutable
receipts; blocked raw remains private and replay rejects before output. Public handoff: hashes/counts only.

Reuse `capture_raw_bytes`, `RawCaptureManifest`, SourceObservation/provenance conventions, SecThrottle,
retained Form4 extraction and reviewed parent-hash/byte-span conventions. Existing Form4/BAC scopes
and the fixed BAC identity importer cannot ingest this chain. The missing bounded submissions/archive/
annual-index/cover verifier and cumulative privacy/time enforcement need a separately reviewed
implementation; no production code is added. Default retry behavior must not be reused.

Only a new supervisor-approved declaration binding proposal/input/code/lock/runtime hashes, selectors,
caps and a fresh private root could authorize later requests. SEC contact-use requirements apply then;
this plan reads no contact/config. No old SEC or BAC budget resumes. No new account, purchase or user
fact is needed for this SEC-only planning slice. Current facts: signed in to Alpaca/Cloudflare/Quiver,
paidQuiver only; exact API plans/agreements/key readiness/retention/derivative/cloud rights unverified.

Stop for independent review. SPY identity, price/terminal coverage and eventual execution rights
remain independent prerequisites. Accepted methods, reconciled untouched validation, surviving signal,
real elapsed forward evidence, durable failure audit and pilot/funding gates remain unmet. No inference,
calibration, registration, price/outcome inspection, paper/forward start, cloud/runtime/schedule,
charge, funds or order is authorized. Issues9/10/15 remain open; October250/November500 and November
timing remain capital plans, not readiness or deployment authority.
