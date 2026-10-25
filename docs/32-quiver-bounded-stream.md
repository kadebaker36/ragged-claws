# Bounded Quiver response retrieval

This is fixture-tested engineering for #9, not acquisition permission or an access agreement.
The supervisor has now verified an active Hobbyist API plan and provisioned an existing token
under human authorization. Earlier unknown-plan/key statements remain historical. Dev did not
read credentials, private storage, accounts or the credential Sheet. Actual endpoint entitlement
and applicable raw/derived-retention agreement remain pending; no real QuiverAccessReview,
data request, live smoke, new CLI or credential loader is introduced.

`retrieve_quiver` retains its endpoint/query allowlist, explicit opt-in, nonempty supplied token,
actual reviewed agreement/endpoint entitlement and private non-sync/non-Git storage gates before
dispatch. Nonempty client-default query parameters reject so they cannot silently alter the
allowlisted request. A caller may lower `max_body_bytes`; only positive integers through 5,000,000 are accepted
(booleans rejected). Synthetic reviews and invented tokens in tests attest to no actual user rights.

The helper uses one synchronous HTTPX stream context, no retry/pagination/alternate endpoint loop,
no redirects and no client-default authentication flow. The caller still owns its supplied client
and transport; transport retries/hooks or buffering must not be treated as helper-controlled wire
behavior. This is one helper dispatch, not a new live declaration or global rate-limit contract.

Before body iteration it checks:

- Aggregate parsed header bytes <=65,536, counting `sum(len(name)+len(value))` over every
  `response.headers.raw` occurrence, including duplicate field names. Status line, colon/CRLF,
  framing, compression and TLS/wire overhead are excluded. HTTPX has already parsed the headers;
  this is not a pre-parser wire/header allocation limit.
- Only HTTP200 and one `application/json` Content-Type (case-insensitive media type, parameters
  allowed). Redirect, denial, rate-limit and HTML/challenge MIME responses reject without body
  iteration. A body falsely labeled JSON can only be rejected after inspecting its content.
- Request `Accept-Encoding: identity`; accept absent or one `identity` Content-Encoding only.
  Encoded, empty, compound or duplicate encoding headers reject before iteration. No decompression
  feature or compressed-size guarantee is introduced.
- Optional Content-Length must be a single nonnegative ASCII decimal after SP/HTAB trimming.
  Duplicate fields, even equal, comma lists, invalid syntax, or Content-Length together with
  Transfer-Encoding reject. Leading zeroes are allowed. Declared length above the chosen body cap
  rejects before iteration. Absent length does not disable the actual-size limit.

Each delivered entity chunk is counted before retaining it. The first chunk that crosses the
chosen cap, or a smaller declared length, rejects and leaves the iterator tail unconsumed. EOF
shorter than Content-Length also rejects; protocol/transport truncation errors reject and close.
Exactly-at-cap content succeeds only with EOF and valid JSON. `iter_bytes` under the enforced
identity policy yields uncompressed entity bytes and also supports already-buffered synthetic
HTTPX responses used by existing tests. Real transports may deliver an already allocated chunk;
the helper is not a strict socket/wire-memory bound, nor a guarantee against a caller's buffering
hooks/transport. Retained-body cap and transient JSON/copy allocations are different quantities.

A rolling overlap detects literal credential echoes across chunk boundaries and stops before any
remaining tail. After EOF a bounded JSON syntax/privacy pass inspects decoded keys and strings,
including Unicode escapes, UTF16/32 JSON representations and duplicate object members without
discarding earlier values. Escaped echoes reject before bytes can be returned for capture.
Independent review exposed a gap for numeric-only tokens in UTF16/32 JSON: conversion to Decimal
hid the original token text from string-only inspection. A bounded encoding-aware scan now checks
the decoded entity text before JSON scalar conversion, using the same encoding detection as
`json.loads(bytes)`. It catches original numeric/exponent/boolean/null lexemes without trying to
reconstruct their spelling from parsed values. Safe response bytes are returned unchanged; the
existing escaped-string/key inspection remains. Original failing probes and handoff stay immutable.
Malformed/nonfinite/deep JSON fails closed. This is not a canonical row parser: existing schema,
duplicate-key and normalization rules remain in the adapter/parser. No partial/failed response
is returned or persisted. Retrieval writes no raw, Parquet or canonical files.

All paths close the response context. Operational exceptions and response rejections use fixed
nonsensitive errors with suppressed chaining; no server body/header/location/exception text or
token is reflected. Finite30second HTTPX connect/read/write/pool timeouts override an unbounded
client timeout. These bound individual I/O waits, not total response duration. No new elapsed
deadline or hard wall-clock guarantee is claimed.

Reviewed October25,2026: official [HTTPX streaming documentation](https://www.python-httpx.org/quickstart/#streaming-responses)
and the installed frozen HTTPX0.28.1 interface. No documentation sample requests were executed.
Tests use MockTransport/custom SyncByteStream only and assert actual iterator consumption/closure,
at/over entity/header limits, length/encoding/MIME/status failures, midstream exception redaction,
literal/escaped echoes and zero-dispatch preconditions. Original tests and supervisor probes remain
unchanged. Live smoke remains opt-in and was not run locally.

Raw/evidence/provenance, row-coordinate versus economic-event identity, unresolved class/Listing,
owner distinctions and future-return quarantine are unchanged. Credential storage authorization
does not grant vendor-data retention/cloud rights. PR34's SEC chain remains declined, BACbudget0;
no price/outcome/identity acquisition, inference/registration, paper/forward clock, runtime/cloud/
schedule, charges, funds or orders. Issues9/10/15 and all scientific/coverage/untouched-validation/
real elapsed-forward/operational/pilot/funding gates remain open.
