# One anonymous BAC FIGI candidate capture

This is a separately authorized candidate-evidence slice for the earlier BAC diagnostic.
It does not resolve historical identity, apply claims or bind events. The separate three BAC
events, newer nine sale events and unresolved SPY requirement remain distinct.

## Authority and inputs

The new [acquisition declaration](../research/identity/bac-figi-acquisition-v1.json) is pinned by
SHA256 `e307471485149f17e3f507e46eb62d23a495c3545498916a0a6af445b2b59344` and pre-POST commit
`52fb96c8cc97ff0c721d0933d659db68d8f8b0ab`. It binds final work order18, the accepted proposal
and coverage-card hashes, all proposal input hashes and implementation version. The older
proposal/card stay `acquisition_authorized=false`; no old request budget is reused.

Before any request, verify the retained BAC 13G/A hash and reviewed byte spans, issuer CIK,
common-class assertion and CUSIP `060505104`. The only request is the exact anonymous 76-byte
POST body and URL already specified by the accepted proposal. A changed input, declaration or
unknown version fails before request/output. There is no default live CLI or discovery route.
Fixture tests use an explicit MockTransport; Git contains invented responses only.

The official [API documentation](https://www.openfigi.com/api/documentation),
[terms](https://www.openfigi.com/docs/terms-of-service) and
[FAQ](https://www.openfigi.com/about/faq) were rechecked October 24, 2026. Direct API-document
retrieval timed out; its official indexed text supplied the anonymous mapping schema and limits.
No mapping, enum, search or other data route was queried during documentation review. Identifier
reuse and open metadata do not certify accuracy, completeness or historical validity, and do not
grant blanket third-party-data rights. Actual payloads and reports stay private.

## Transport and evidence boundaries

The helper makes one POST/job/attempt, with no redirects, retries, substitutions or continuation.
Its standalone Request contains only the three declared application headers plus fixed Host and
Content-Length protocol headers. It does not merge client defaults, cookies, auth or browser state.
Client and transport disable environment trust and retries. An explicit TLS client context loads
the existing certifi CA bundle without ambient proxy, certificate or SSL key-log discovery. No
account, API key, actual contact or private configuration is read.

Caps are 512 request-body bytes, 1 MiB response entity, 16 KiB parsed response headers and 64 KiB
receipt evidence, within the declared 1,114,112 entity-plus-receipt bytes. Header counting sums
`len(name)+len(value)` for every raw parsed field occurrence, including duplicates. It excludes
status lines, delimiters, framing, TLS and wire overhead; it is not a total network-wire bound.
Header overflow stops before body processing and records an incomplete response. No response
header values, cookies or raw exception strings enter receipts.

At an entity cap without EOF proof, the exact retained prefix is oversized/incomplete, even if
it happens to parse. A 30-second HTTPX connect/read/write/pool timeout is configured, with elapsed
checks at delivered chunks and response completion. This is not a hard total network-wire deadline.
The one-request scope trivially respects the three-second serial start interval; no next attempt
exists. Aware attempt/finish clocks and actual failure status remain separate.

Acquisition uses fresh private local storage outside Git and known sync/shared roots. Initial and
interrupted checkpoints are separate immutable files; no previous acquisition path can resume.
Exact raw bytes and a restricted RawCaptureManifest are persisted before interpretation. A final
receipt binds the raw/manifest hash, size, completeness, clocks, source request and declaration.
Checkpoint-only replay reports unknown completion and exposes retained directory size; orphan raw
is not parsed or misrepresented as an empty provider result. Missing/resealed evidence or a
state/status/completeness contradiction rejects replay before output.

Denial, rate limit, redirect, timeout, transport, challenge, bounds, privacy and invalid payloads
consume the attempt and stop. No-result, provider error, ambiguity and partial metadata also end
this scope. Privacy-blocked bytes stay immutable in private evidence; replay rejects them before
creating output. All replay paths are private, and raw payloads are never copied to Git/cloud.

## Candidate interpretation and private replay

Validate the one-job envelope before calling the existing pure candidate parser. Exactly one
data/warning/error branch is allowed; mixed branches, duplicate JSON keys, missing fields, unknown
row fields and invalid types fail explicitly. Malformed identifiers use the existing typed
normalization boundary. Warning/no-result differs from provider error; raw error text is not
printed or copied into diagnostics. Valid empty data differs from no completed response.

The existing parser sorts its generic `instrument_figi` field. The diagnostic independently
retains original JSON row pointers/order, duplicate occurrences, exact provider fields and
missing/null/empty metadata. Distinct identifiers and share-class/composite groups are descriptive
only. The provider's `figi` label or equality with a composite value does not authenticate a venue
Listing or MIC. Even one candidate is not a resolved canonical identity.

No Entity, Security, Listing, ExternalIdentifier, control, event binding, Outcome or research state
is created. A restricted SourceObservation is embedded as private diagnostic lineage, with no
asserted historical public time or canonical catalog publication. Valid/known intervals, issuer
authentication, venue/MIC, terminal dates and SPY identity remain unknown. There are no prices,
returns, inferred source-family convergence votes or real elapsed forward observations.

Private report JSON, Markdown and output inventory have a combined 8 MiB bound fixed before the
request. If expansion exceeds it, retain raw and emit a bounded unavailable diagnostic with null
candidate count, rather than cropped rows or a complete-candidate claim. Reports bind request,
source, response, declaration, exact code/lock/runtime and output hashes. A fresh offline replay
needs no network, account, configuration or credentials:

```text
uv run --frozen python -m ragged_claws.ingestion.bac_figi_audit --declaration research/identity/bac-figi-acquisition-v1.json --repo . --captures PRIVATE_CAPTURE --output FRESH_PRIVATE_REPORT
```

Repeated raw evidence insertion is idempotent; reports require fresh output paths. Existing raw,
Parquet, declarations, proposal flags, failures, probes and handoffs remain unchanged. The external
BAC-FIGI-CAPTURE-HANDOFF.md records the actual zero-or-one attempt and private regeneration paths
after capture. No further acquisition or merge follows this slice without supervisor review.
Issues 9/10/15 and scientific, coverage, elapsed-forward, operational and funding gates remain open.
The November planning target is not a readiness date or deployment authority.
