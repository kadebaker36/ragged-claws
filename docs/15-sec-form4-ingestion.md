# SEC Form 4 ingestion — issue #5

## Scope and source review

This slice ingests explicit complete-submission bytes or explicit ownership XML/metadata. Only
Form 4, Table I non-derivative transaction codes P and S emit events. Forms 3/5/4-A, derivative rows,
holdings and other codes retain explicit exclusion reasons in source staging; no amendment
reconciliation, discovery/crawler, warehouse, research score, runtime or trading is implemented.

Official sources checked October 22, 2026:

- [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data):
  declared User-Agent/contact, 10-request/second ceiling, Eastern operating hours, corrections.
- [Webmaster FAQ](https://www.sec.gov/files/about/webmaster-faq.htm): public filing reuse, header
  definitions, acceptance versus official filing date, variable dissemination delay and the absence
  of a timestamp for first availability on sec.gov.
- [Technical specifications](https://www.sec.gov/submit-filings/technical-specifications): current
  Ownership XML v5.5, March 18, 2026. The linked
  [v5.5 archive](https://www.sec.gov/files/edgar/filer-information/specifications/ownershipxmltechspec-v5-5.zip)
  was retrieved; its reduced-content Form 4/common schemas confirm reporting owners, Table I rows,
  footnotes and optional price values. This parser supports the narrow normalized subset rather
  than claiming complete XSD validation.
- [Linked PDS specification](https://www.sec.gov/info/edgar/specifications/pds_dissemination_spec.pdf):
  complete-submission header/document structures. The linked March 2025 PDF is labeled **DRAFT**;
  it is not represented here as a newly finalized 2026 specification.
- [SEC Form 4 instructions](https://www.sec.gov/files/form4.pdf): P/S cover open-market **or private**
  purchases/sales. A source code alone does not establish an execution venue.
- [SEC Release 33-11159](https://www.sec.gov/files/rules/final/2023/33-11159.pdf): EDGAR filing times
  operate in Eastern standard/daylight time in effect.

## Parsing, staging and evidence

`SecForm4Adapter` separates capture, normalization, SourceObservation construction, canonical mapping
and persistence. `SecFilingClient` is a separate HTTP boundary. Exact source bytes go to existing
content-addressed raw storage before parsing; manifests record source locator/accession, retrieval,
explicit metadata, public retention, hashes and adapter/parser versions. Collection does not replace
public timing. Malformed/contradictory inputs retain raw captures but publish no partial events.

A complete submission must have agreeing caller/header/root accessions; exactly one ownership XML
document; agreeing header/document/XML forms and issuer/owner CIKs; and safe document identity.
Missing/duplicate fields, malformed XML, DTD/entities and ambiguous ownership documents fail
explicitly. UTF-8 and a 5 MB parser size bound are supported. The bare-XML path requires explicit
accession, document name and form type; official filing and acceptance metadata are optional,
untrusted inputs the caller must source. Missing metadata is never inferred from transaction dates.

Staging preserves all reporting owners with source-stated role flags/titles, all supported table
children with row coordinates and exclusion reasons, direct/indirect ownership, A/D flags,
security titles, optional exact Decimal shares/prices, references and footnote text. The complete
raw document preserves additional fields, remarks, footnotes and unsupported content. A staged
mapping bundle also preserves policy/actionability results and unresolved owner CIKs. Missing
prices, including footnote-only prices, remain `None`; zero is retained only when explicitly stated.
Price is a canonical Decimal event attribute because the XML supplies no currency assertion.
No USD amount or inferred transaction total is manufactured.

## Canonical identity and owner uncertainty

Issuer creation uses the existing exact CIK-to-Entity operation. Existing canonical subjects with
exact CIK claims are reused; every new filing adds separate observation/provenance/identifier
evidence rather than changing a subject's first provenance, display name or collection state.
The regression covers two distinct accessions for the same issuer and known owners.

Reporting-owner names and role flags do not establish whether a CIK denotes a person, fund or
organization. The existing canonical Entity model requires a concrete type and has no unknown
variant. Consequently this adapter **does not auto-create typed owner Entities**. It links owners
only to existing canonical Entities with exact source-backed CIK claims. Otherwise normalized owner
records, CIKs/names/roles and explicit unresolved CIKs remain in staging and normalized event
attributes. The event is still emitted once per transaction row and can remain actionable at issuer
level. This is explicit unresolved attribution, not a discarded event or fabricated owner type.

The real recorded fixture therefore emits three events with two unresolved owner identities by
default. A separately labeled invented catalog test proves two known owner links on each of three
events, without doubling the transaction population. Actors mean `reporting_owner`, not that each
person independently executed the transaction. No household/spouse/economic-unit allocation is
inferred. Security/Listing remain unset; CIK and trading symbol never manufacture instrument identity.
CIK evidence added by this adapter has unknown `known_from`: retrospective type resolution is not
proof a typed identity claim was historically knowable.

## Timestamp and availability policy

The FAQ and linked PDS document use the shorthand “EST” for acceptance. The broader official
operating rules use Eastern standard/daylight time in effect. This discrepancy is preserved rather
than silently interpreting every clock with a fixed UTC-05 offset. The parser requires the caller
to explicitly confirm `acceptance_timezone="America/New_York"` for the Eastern-clock convention.
Without that confirmation, raw acceptance is retained with `acceptance_timezone_unconfirmed` and
no normalized public/actionable time. Invalid/missing clocks and ambiguous/nonexistent DST clocks
also remain non-actionable with a counted reason. Future acceptance relative to collection is rejected.

With confirmation, source text, named source timezone and UTC are separate. Winter and summer use
the zone's historical offset; UTC date boundaries are retained. No developer-machine timezone is used.
This is a documented interpretation policy, not a claim that the PDS draft resolved every ambiguity.

Acceptance is an EDGAR system timestamp, not measured first-publication time. Default policy
`sec_acceptance_plus_five_minutes`, version 1.0.0, adds an explicit five-minute research delay through
the existing `AvailabilityPolicy`. SEC describes variable lag and supplies no guaranteed maximum;
five minutes is an assumption, **not a guaranteed safe publication bound**. A different explicit
policy can be supplied, and the mapping bundle records it. Use measured forward observations or
a separately justified policy before treating historical labels as funding-readiness evidence.

The shared calendar-backed resolver derives actionability from effective availability. At/after-open
availability goes to the next session; date-only official filing metadata is never promoted to public
time. Source occurrence, official filing date, acceptance evidence, observed collection, effective
availability and actionable time remain distinct. Tests cover winter/summer, DST ambiguity, UTC date
crossing and a delay that moves pre-open acceptance exactly to the open.

## IDs, corrections and persistence

Adapter/parser/transform versions are `sec-form4/1.0.0`, `sec-ownership-xml/1.0.0` and
`sec-form4-mapping/1.0.0`. Deterministic UUIDv5 inputs are:

| Object | Namespace | Exact UUID name |
| --- | --- | --- |
| Filing group | `c4915726-7a86-43f8-960b-aa0f8df3f041` | `sec_accession:<dashed-accession>` |
| Event | `3ccf9ea0-633b-4b78-af1f-782ad2ae4eaa` | `<accession>:<document-sequence>:<table>/<row-tag>[<1-based-child-index>]` |
| Provenance | `dc94edf2-b05f-4742-9a3d-66f5a5677b64` | `<observation-uuid>:sec-form4-mapping/1.0.0` |
| Event evidence | `0c7ec7a4-8765-4dd5-92d1-d4cab404aa97` | `<event-uuid>:<observation-uuid>` |

SourceObservation reuses the M0 provider/native-ID/content-hash rule with provider `sec.edgar`,
native accession and full captured-byte SHA256. Issuer CIK identities and identifier claims reuse
doc 14's namespaces. Equal-valued rows remain distinct by source row coordinate. Names, prices,
tickers and owner order do not define event/subject identity. Changing source row positions within
one accession is a correction conflict, not an implicit match or deletion.

Repeated identical ingestion reuses the first canonical observation after semantic comparison;
later retrieval creates only another capture manifest. New accessions reuse verified subjects and
add independent source claims. Changed bytes for an already-persisted accession are rejected even
when no P/S events were emitted. Same-ID/different-payload storage remains strict. Changing timing,
owner-resolution or methodology configuration requires deliberate reprocessing/version handling;
the original mapping is not overwritten.

The entire filing mapping and every existing target dataset are validated for ID/payload conflicts
before writes. Each Parquet file is atomically replaced through existing storage. There is **no
cross-dataset transaction or concurrent-writer guarantee**; a crash/I/O failure can leave a partial
publication, requiring validation and an idempotent rerun. This slice does not add distributed
locking or promise crash-atomic multi-file state. Raw captures survive rejection/crash. Parquet is
authoritative and DuckDB remains rebuildable. No canonical/schema change or migration is required;
only adapter-owned staging envelope schemas are new, version 1.0.0.

## HTTP and reproducible entry points

`SecFilingClient` requires a declared contact, restricts access to explicit HTTPS SEC Archives
filing text/XML URLs, rejects redirects/denials, and does not crawl. A shared process-local limiter
serializes default clients at four requests/second. All concurrent processes must share an external
budget or be run serially; this is not a distributed limiter. Three bounded attempts cover transport
and selected transient failures. Numeric/HTTP-date Retry-After is respected; an invalid/excessive
wait stops instead of retrying early. Clock, sleep and httpx transport are injectable for offline
tests. Contacts/headers are not written to manifests. Reserved example contacts are rejected for
default live-client construction.

Local complete-submission ingestion (no network):

```text
uv run --frozen ragged-claws ingest-sec-form4 tests/fixtures/sec/0000950170-24-105263.txt --accession 0000950170-24-105263 --source-url https://www.sec.gov/Archives/edgar/data/70858/000095017024105263/0000950170-24-105263.txt --acceptance-timezone America/New_York --data-dir data
```

Output counts events, reporting/unresolved owners, filing exclusions and row exclusions. Omit timezone
confirmation to retain unconfirmed timing. Python callers can separately fetch/capture/normalize/
map/persist, use explicit XML metadata, or supply a reviewed availability policy.

All normal tests are offline. `test_sec_live_smoke.py` runs only with `SEC_LIVE_SMOKE=1`, a real
configured `SEC_USER_AGENT`, and an explicit `SEC_LIVE_FILING_URL`. It does not load local config
automatically. See `tests/fixtures/sec/README.md` and its hash manifest for recorded versus invented
fixture provenance. Keep actual contact configuration ignored and out of Git and reports.
