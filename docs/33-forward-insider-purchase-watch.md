# Forward insider purchase watch

This bounded forward operational aid advances #10 without validating the investment hypothesis
or closing #9, #10 or #15. It answers which source-backed reporting actors have disclosed supported
purchases, what is unresolved, and when the existing canonical actionability policy permits their
use. It starts no schedule, paper clock, durable-cloud runtime or orders.

Broad market drawdowns are external market context. They do not change which actor behavior qualifies as a Ragged Claws signal.

## Canonical input and qualification

`watch/` consumes canonical Parquet Event, EventEvidence, SourceObservation, Provenance, Entity,
ExternalIdentifier, Security and Listing. It never opens ownership XML/SGML or price/outcome state.
`watch/contracts.py` isolates the interpretation of existing normalized Event attributes. Future
canonical sources can implement `PurchaseContract` and pass contracts to `CanonicalWatch`; shared
PIT filtering, identity checks, economic-event counting and clusters remain unchanged. No future
source integration, including politicians/Quiver, is activated here.

The initial contract requires `equity_purchase`, canonical transaction code **P**, a Table I
`nonDerivativeTable/nonDerivativeTransaction[N]` coordinate, and visible primary `sec.ownership`
evidence produced by the reviewed `sec-form4/1.0.0` adapter. That adapter alone establishes supported
Form 4 semantics. S, gifts, grants, exercises, holdings, derivatives, unsupported forms and inferred
purchase-like records do not qualify. Automatic-plan text cannot override a non-P transaction;
existing supported canonical P semantics are preserved without a second plan classifier.

A resolved canonical Security of type `common_stock` establishes common-stock qualification.
Other resolved types are excluded. Missing/not-yet-observed Security evidence produces a visible
**unresolved** row, never a confirmed common-stock purchase. Missing or unusable Listing evidence
is separately categorized; issuer-level common-stock qualification can remain known without a
Listing. Canonical issuer/security/listing contradictions fail explicitly. No title, name, ticker,
current symbol universe or remote identity lookup supplies a missing binding. The watch does not
write or repair canonical identity. Existing SEC ingestion normally leaves Security/Listing unset;
those rows therefore remain unresolved until an independently supported canonical binding exists.

“Informed actor” here is only a source-backed Form 4 reporting owner. Source-stated CIK/name,
officer/director/10% flags and title remain source facts. No subjective elite tier, inferred role,
spouse/household, independent executor or economic-owner allocation is added. All filing owners
may support the same row; their presence does not mean each independently spent personal cash.
Canonical owner IDs are exposed only when already present in Event reporting-owner roles and
supported by a visible exact CIK claim. Otherwise the source CIK reference remains useful and
explicitly unresolved as a typed Entity.

SEC code P means open-market **or private** purchase under Form 4 instructions. V0 cannot prove
execution venue, absence of financing or whose personal capital funded every jointly reported row.
The output states this limit instead of labeling every P row a verified personal open-market trade.

## Public, observation and actionable timing

The ledger preserves Event `occurrence_time`, `public_time` and `actionable_at` unchanged. It does
not derive any of them from index/filing dates. Public time must be eligible under the existing
precision-aware PIT rules, and `actionable_at <= as_of`. Event mapping provenance, parent provenance
and supporting evidence/observations must also have been derived/observed/retrieved by `as_of`.
Later evidence is omitted until observed; later collection never creates earlier collector knowledge.
Identity records need visible provenance too. A later observed identity cannot qualify a prior report.
A missing public/actionable time is counted as withheld, never fabricated. Reports use explicit aware
ISO timestamps, normalized to UTC, independently of desktop timezone.

The existing SEC acceptance plus five-minute policy is an **assumption**, not measured first
publication or a guaranteed SEC dissemination bound. Its source-derived session label and actual
first observation remain separate. An archival Event collected today cannot appear in an old report.
The watch creates no historical decision, fill or elapsed forward-validation evidence.

## Financial unknowns

Shares and reported per-share price remain Decimal. SEC ownership XML does not assert currency,
so currency stays null. A reported Decimal price remains visible without claiming market execution.
Exact shares times exact reported price yields a Decimal numeric transaction value only when both
are present, finite and nonnegative and neither disclosed ranges nor referenced footnotes require
further exactness review. Multiplication uses sufficient local Decimal precision, not ambient caller
rounding. The result has unknown currency; it is not a USD amount. V0 conservatively withholds the
total for *any* referenced footnote (including harmless ones), because weighted-average prices and
footnote qualifications need a separate reviewed contract. Missing price is null, never zero.
Ranges remain ranges in canonical state; no midpoint, USD assumption or size score is created.

## Window, deduplication and clusters

The configurable default is **five XNYS regular sessions**: include Events whose canonical actionable
time lies from the oldest included session's open through `as_of`, inclusively. The newest session
is the latest whose open has occurred. Before an open, on weekends and holidays, use the preceding
session. Accept 1–252 sessions. Calendar/library version and UTC window start are recorded.

Sort by actionable time, then Event UUID. Each canonical Event appears once irrespective of evidence
or vendor count; distinct transaction rows remain distinct Events. Vendor copies retain their
underlying family and never create additional purchases or independent convergence. Optional issuer
summaries count confirmed common-stock Events only, distinct source reporting CIKs, distinct primary
accessions, and first/latest actionable timestamps within this explicit window. One insider repeated
across rows/filings counts once. Unresolved rows stay in the ledger but do not inflate confirmed
clusters. Source CIKs distinguish reporting actors without guessing their Entity type or treating
co-reporters as independent trade executions. No composite score, inference, ranking model or alpha
claim is made. Same-economic-event reconciliation remains the canonical layer's responsibility.

## SEC discovery and incomplete-scan accounting

The official daily **master index** is the initial daily-index variant. Its pipe-separated schema
retains raw/normalized filed date, exact form, filer CIK/name, exact archive path and accession for
every reference to a discovered Form 4. `capture_index` stores exact bytes before parsing in existing
content-addressed raw storage with capture ID, hash, source locator and aware retrieval clock.
The discovery checkpoint links that capture; no index row becomes a canonical purchase observation.

Group by accession, sort accession lexically and retain all physical references, including exact
duplicates. Different filer CIK paths may reference one filing; select the literal reference with
lowest numeric filer CIK, then lexical path, once. This is a deterministic retrieval address, not
an issuer inference or claim that aliases have equal bytes. Conflicting forms or official dates in
a group produce an explicit rejected group with all references retained, without a filing request.
The historical audit declarations, rejected receipts and reference proposals remain unchanged.
This forward rule is separate from their fixed scopes and does not resume those acquisitions.

Complete-submission bytes pass through the existing `SecForm4Adapter`: raw capture → existing parser
→ canonical Event/evidence/provenance/staging → ledger. The index date supplies none of transaction,
acceptance/public/actionable timing, Security identity or purchase qualification. Index filers may
be owners rather than the body's issuer. Unsupported/malformed filing bodies are counted rejected;
a valid no-P filing is successfully ingested with zero P Events. Other forms are discovery exclusions.

Each checkpoint records a deterministic next cursor, processing clocks and per-filing status/Event
IDs. Each completed filing advances it atomically; transport/denial/oversize failure stops the batch
and leaves that filing unprocessed. A later explicit run retries the same cursor, without selecting
a replacement. Idempotent canonical ingestion handles a crash after ingestion but before checkpoint.
Conflicting canonical payloads stop rather than overwrite accepted state. On resume, the raw hash,
index identity and exact reference list are reverified. Storage is single-writer; canonical publication
remains per-file atomic, without a multi-file transaction or concurrent-writer guarantee.

JSON and Markdown expose discovered unique Form 4 accessions, processed, remaining/unprocessed,
rejected, successfully ingested, visible qualifying common-stock P Events, visible unresolved P
Events and cursor. These P counts reflect the report as-of, not unknown unprocessed bodies. Processing
clocks prevent later progress leaking into earlier completeness summaries. A scan captured after
report as-of cannot be attached. No supplied scan means **coverage unknown**. `index_processing_complete`
means only that this captured index's accession list was processed. **Market coverage always remains
unknown**, even for an empty index or exhausted cursor. Daily indexes can lag, change or omit later
corrections; this implementation does not certify a complete-market census or automatically revisit
updated index versions. Use a separate checkpoint for a deliberately recaptured index.

## HTTP and live access

The narrow watch method in existing `ingestion/sec_http.py` reuses `SecFilingClient` contact
validation, httpx and `SecThrottle`. Only explicit official HTTPS daily-master-index and literal
index submission paths are accepted. A watch client must use an interval of at least one second;
CLI requests run serially with no redirects, retries within an invocation, substitutions or fallback.
Bounds: 2 MiB index, 5,000,000-byte submission, 10-second I/O timeouts, 30-second response-loop
deadline checked between chunks (a blocking I/O can run until its timeout). An oversize response
retains at most bound+1 bytes, explicitly as a failed response, never a parsed complete filing.
Failure bytes/status category remain raw evidence, and unprocessed counts remain honest. No request
headers/contact or transport exception text enters receipts. Compressed responses are unsupported;
requests declare identity encoding to preserve exact response entity bytes. These are entity bounds,
not TLS/wire-byte or cross-process global limits. Run one writer/process at a time.

Live discovery requires **all three**: command `--live`, `RAGGED_CLAWS_SEC_LIVE=1` and an externally
supplied declared `SEC_USER_AGENT` with a real contact. Contacts are never invented, loaded from
random files, printed or committed. Missing configuration skips live acquisition. Default tests are
network-free; this slice adds no live smoke test. No desktop, OneDrive or Windows-local dependency
exists. Live access, if used, is solely public SEC acquisition; no vendor payloads or keys are needed.

## Regeneration and CLI examples

Use Python 3.12 and `uv sync --frozen`. DATA, OUTPUT, SCAN and FILINGS below are caller-chosen portable
paths; choose a fresh OUTPUT for each different report. Identical regeneration preserves JSON and
Markdown bytes. Offline reporting is read-only on canonical state:

```text
uv run ragged-claws watch-insider-purchases --data-dir DATA --as-of 2026-11-05T22:00:00Z --lookback-sessions 5 --output OUTPUT
uv run ragged-claws watch-insider-purchases --data-dir DATA --as-of 2026-11-05T22:00:00Z --scan SCAN.json --output OUTPUT
```

Local index/complete-submission ingestion (explicit capture clock; FILINGS contains accession.txt
basenames). Transaction/public clocks still come exclusively from the complete submission:

```text
uv run ragged-claws discover-sec-purchases --index-day 2026-11-04 --index-file master.20261104.idx --retrieved-at 2026-11-05T08:00:00Z --filings-dir FILINGS --checkpoint SCAN.json --data-dir DATA --max-filings 10 --acceptance-timezone America/New_York
uv run ragged-claws discover-sec-purchases --index-day 2026-11-04 --filings-dir FILINGS --checkpoint SCAN.json --data-dir DATA --max-filings 10 --acceptance-timezone America/New_York
```

With the two environment variables explicitly supplied by the operator, live first batch/resume:

```text
uv run ragged-claws discover-sec-purchases --live --index-day 2026-11-04 --checkpoint SCAN.json --data-dir DATA --max-filings 10 --acceptance-timezone America/New_York
```

Repeat that exact live command to process the next bounded batch from the captured index. Timezone
confirmation is explicit; omitting it preserves unconfirmed timing and yields no actionable candidates.
JSON includes all candidate source-observation/evidence/provenance IDs and filing references.
Markdown is a concise evidence feed. No BUY/SELL labels or recommendations are generated.

## Limits and verification boundary

No market bars are required or fetched. Optional future PIT price context must remain separate, use
existing market-data models/feed/adjustment semantics and prices knowable by the decision instant;
today's ticker must never become a fallback. V0 adds no price context, outcomes, valuation, scoring,
portfolio sizing, automated trading, political integration, LittleSis expansion, R2 activation or
scheduled Actions. Existing hypotheses, inspection histories and validation results are untouched.
No canonical model/schema/migration, dependency or investment thesis changes are required.

Regression fixtures are explicitly invented purchases/indexes constructed in-memory from the
attributed SEC fixture through the existing parser; they are not real insider-purchase discoveries.
Tests cover P/S/exclusions, distinct rows, duplicate evidence, PIT and late collection, exact/missing/
range/footnoted numbers, identity states, actors/clusters, partial scans/resume, raw capture/unsafe
references, response bounds/denials, deterministic JSON/Markdown and portable paths/timezones.
The implementation is an operational evidence capability, not issue #10's validation result.
