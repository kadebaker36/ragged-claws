# Validated durable generations and inactive runtime

The additive [analysis archive extension](23-analysis-archive.md) supports pinned
analysis artifacts and scope sidecars under an explicit private archival review.
Layouts without that extension still reject those files. Prior generations remain
recoverable without changing manifests, serialization defaults or hashes. This
extension does not provide durable audit of unpublished ephemeral inspections.

**Status:** bounded offline engineering for #15. No R2 account, bucket, credentials, GitHub secrets,
production acquisition or schedule is configured or validated. #15 remains open. Local recovery
tests are not real R2 recovery, research validation, elapsed forward observation or funding readiness.

## Boundary and authority

Canonical models, source adapters and DataLayout remain filesystem-based. `ragged_claws.durable`
adds bounded object GET and conditional PUT around that layout. `MemoryObjects` is an atomic
in-process test store; `LocalObjects` is a disk fake for isolated, externally serialized offline
rehearsals. Neither is a distributed storage service. Concurrent processes using a disk fake are
outside its supported contract. `S3Objects` maps the boundary to boto3; no bucket/list/copy/delete,
multipart upload, distributed lease, server or new database is introduced.

Boto3 and its locked dependencies supply supported S3 request validation/signing and
bounded StreamingBody access. SDK tests use Stubber and invented credentials with user AWS config,
shared credential files and instance metadata disabled. No default test makes a network request.
The only factory for a real client requires explicit isolated non-production configuration, supplies
credentials explicitly from environment variables, and sets finite timeouts and one total attempt.
There is no production cloud CLI or automatic credential-chain fallback.

Object layout, scoped by a caller-selected private bucket/prefix:

```text
blobs/SHA256                    immutable exact bytes, deduplicated across generations
generations/GENERATION_ID.json  immutable complete manifest with pinned parent
authority/current.json         conditional authoritative pointer
```

Generation IDs hash deterministic canonical manifest content except the ID field. Manifests record
parent, explicit source/cloud policy and review reference, code/schema/lock/runtime versions,
every file path/hash/size, canonical record counts and license notices. These are sync artifact
version1.0.0, not a new canonical domain schema. Canonical schema1.0.0 and the existing 19 generated
schemas remain unchanged. Unsupported schema/codec/model versions fail explicitly; there is no
automatic migration or reinterpretation of historical state.

Restore requires a caller-pinned generation ID. It never selects a newest object or guesses
authority from a listing. It checks manifest identity, bounded parent-manifest history, paths,
every object size/hash, typed Parquet envelopes and IDs, exact raw addresses/capture IDs,
evidence/provenance references, rights, and research manifests before yielding a new owned
temporary DataLayout. Invalid state is rejected; no existing caller directory is overwritten or
repaired. Runtime workspaces must use private roots outside Git/shared/known-sync locations. A
successful owned workspace is cleaned when its context ends; a failed/indeterminate workspace is
retained privately with a failure receipt, including any unpublished inspection journals. It is
never automatically uploaded as a failure artifact or treated as validated authoritative state.

Dependency closure follows actual loader locations: the operational root and each frozen
`snapshots/UUID/data` layout must independently contain their own canonical references and exact
raw/manifests. An archive cannot supply a missing root file, and the root cannot supply a missing
archive dependency. A scoped research result may use its own records plus only the explicit matching
frozen inputs named by its snapshot manifest, never unrelated root/other-snapshot records. Global
unique-record counts remain inventory summaries, not closure authority. Snapshot-only generations
with an empty operational root are supported; restore does not implicitly copy archive files into it.

## Publication ordering and failure semantics

`run_pipeline` checks the expected parent, restores it into owned temporary state, invokes existing
local ingestion/research, then publishes only if all phases succeed. Direct `publish` independently
validates the candidate, restores/validates its expected parent, and compares their full inventories.
Every parent durable file must remain represented. Root curated/staging Parquet may append only
new IDs: existing IDs must retain identical validated payloads. All raw files, frozen snapshots,
scoped research results and journal/registration files are immutable. Same state is a no-op, not a
new generation. A policy change requires separate namespace review rather than silently changing
the rights of an existing history.

File retention also preserves inspection knowledge: a previously published real start without
a finish cannot gain an uninspected denial or a finish narrowing its potential interval.
Publication compares the parent; pinned restore enforces this against all ancestors using
the retained immutable starts. Initial pre-read denials remain valid, and an inspected
completion covering the published interval is supported. No reconciliation override is added.

All local rights/lineage/schema/parent-conflict checks finish before the first PUT. File bytes are
captured and checked for changes during validation; uploads use those exact validated bytes.
Immutable blob/manifest creation uses If-None-Match:*; a known conditional conflict permits only
a verified identical-byte no-op. Existing different bytes are never overwritten. After upload,
the complete candidate is restored from remote objects and validated again before pointer CAS.
Parent monotonicity is rechecked against those actual restored bytes as well.
The pointer uses its exact observed opaque ETag with If-Match, or If-None-Match:* for initial state.
Stale parents and conditional conflicts stop; there is no last-write-wins fallback.

Pipeline/validation failure or interrupted upload before pointer commit leaves previous authority
unchanged. Uploaded orphan blobs/manifests are harmless and are not promoted by age or listing.
No garbage collection or rollback overwrite is implemented. If a pointer write commits but its
response is lost, the caller receives an indeterminate-write error: a complete new generation may
be authoritative, while the old generation remains addressable. Stop and reconcile from explicit
generation IDs and pointer evidence. Do not automatically retry, declare a negative read final,
or claim that every failed request left the pointer unchanged.

Failed local journals require explicit reconciliation before another untouched-evidence attestation.
The caller must retain these private quarantines. This offline slice does not provide licensed cloud
storage of rejected failure payloads. An ephemeral production runner would need separately reviewed
durable failure-audit handling before real outcome inspections can be enabled; otherwise unpublished
failed inspection history could be lost when that runner is discarded. The template remains inactive
and this is an operational activation gate, not an assertion of unattended recovery readiness.

Conditional safety supplements the required single-writer runtime. It is not a claim of concurrent
ingestion transactions, distributed locks, exactly-once network delivery or automatic recovery
from provider-side deletion of older objects. Restoring an old generation separately detects any
missing/corrupt objects belonging to it; parent manifests alone do not prove all ancestor blobs.

## Explicit export scope and evidence closure

Only validated files under `raw/`, `staging/`, `curated/`, `research/` and `snapshots/` are eligible.
Top-level cache, DuckDB, .env, private config, adjacent files and arbitrary directories never enter
the export. Unknown files inside durable roots reject the generation instead of being quietly
discarded. Names are portable safe relative paths; traversal, absolute/drive paths, backslashes,
dotfiles, reserved Windows names, case collisions and symlink escapes are rejected. Known envelope
filenames/models must agree. Reads are bounded:16MiB/file,256MiB total,4096 files,2MiB manifest,
50000 Parquet rows/file,64MiB declared uncompressed Parquet data/file and256MiB aggregate expansion.
Parent metadata history
is bounded to4096 manifests/32MiB. This is a bootstrap boundary, not a bulk archive transfer tool.
Canonical identifier subjects and outcome benchmark references must resolve; provenance traversal
rejects cycles/depth beyond128 and memoizes completed nodes rather than revisiting shared subgraphs.

Retention/configuration metadata is inspected before full payload traversal. Restricted or unknown
raw/derived dependencies reject the whole mixed generation by default with countable safe reasons.
Deleting a required restricted observation/raw object does not create a valid public derivative:
all canonical/embedded references and raw-manifest closure must still validate. Local Quiver or
research retention attestations are never accepted as cloud permission. No restricted-source cloud
override is implemented in this slice; separately reviewed support would need a deliberate policy
extension. Raw captures without retention manifests are rejected.

### Public SEC scope

The default real-source policy permits public SEC ownership data only, retaining exact raw bytes,
capture metadata, SourceObservation/EventEvidence, canonical records and typed SEC staging. It
requires an explicit policy review reference. It does not claim cryptographic authentication of
operator input. SEC source/manifest metadata must use the reviewed adapter/parser and public-filing
license, an official SEC Archives locator, and primary-source role where applicable. This does not
prove that every permitted record is relevant research coverage.
The offline demo uses the exact already recorded public filing and its source locator; it makes
no SEC request. SEC reuse/access and attribution rules remain those documented in docs15/fixture
README. No contact header or private SEC configuration is exported.

LittleSis is disabled by default. Explicit `allow_littlesis` under a reviewed public policy requires
the typed matching bundles, CC BY-SA4.0 URL, copyright, attribution and change notice; these travel
in source/staging artifacts and generation license notices. Dropping those obligations rejects
the generation. This does not grant rights to unrelated source documents linked by LittleSis,
commercialization, or other providers. All unsupported providers remain disabled.

Invented exports require `invented_engineering` plus an explicit invented attestation. Only synthetic
provider namespaces with public/internal retention are accepted; restricted/unknown classifications
still fail. Vendor-labelled invented fixtures are not automatically authorized by this narrow
policy. Engineering declarations are assertions, not proof of real cloud/data entitlement.

### Research history

Supported frozen layouts live at `snapshots/SNAPSHOT_UUID/`; complete result layouts at
`research/SNAPSHOT_UUID/`; inspection/registration histories at `research/registry/`. Frozen input
files, hashes, protocol/config/identity/price origins and source evidence remain exact. Result
manifests, report metadata and row/status denominators are checked without recomputing returns.
Existing private-root checks apply to current frozen locations, including after relocation.

Sync validates historical content but preserves its original code/runtime fingerprints and does
not execute historical research. A restored old snapshot still fails the normal research build's
current-environment gate when code or dependencies differ. No fingerprint, registration, inspection
or failed attempt is rewritten to claim compatibility or recover an untouched period. Journals
are append-only and unmatched starts retain their conservative interrupted meaning. Canonical
Parquet remains authority; DuckDB is absent after restore and rebuilt locally as needed.

Metadata containing credential keys or credential-bearing URLs is rejected without echoing the
value. Authoritative bytes are never redacted into a different source snapshot. This guard cannot
prove arbitrary free text contains no secret; operators must never supply secrets as source data
or review references. All runtime errors emitted by the CLI are safe categories/counts.

## Exact offline commands

From a Python3.12 repository checkout with the frozen environment, choose a **new** external demo
directory. The demo refuses an existing output directory and preserves its prior generations.

```text
uv sync --frozen
uv run ragged-claws durable-offline-demo --output EXTERNAL_NEW_DEMO_DIRECTORY
uv run ragged-claws durable-local-inspect --objects EXTERNAL_NEW_DEMO_DIRECTORY/objects --generation EXACT_GENERATION_ID_FROM_RECOVERY_JSON
```

The demo publishes an empty generation, restores/ingests the recorded SEC fixture, repeats an
identical no-op, appends a later retrieval manifest, injects a research failure and an upload
interruption, and proves unchanged authority plus recovery of an older generation. `recovery.json`
distinguishes exact original acquisition replay from subsequent local file reads at their actual
current clock. Those later captures are not fresh SEC requests or elapsed source observation.
Independent demo executions therefore create new explicit local-replay capture versions; pinned
generation recovery remains exact and idempotent. The report
records generation/parent IDs, exact hashes,3 canonical events, failure evidence, cache exclusion
and DuckDB rebuild counts. `recovered/` contains only verified durable files from a second clean
restore. Its local object directory and results are explicitly labelled fake storage, not real R2.

The single optional live smoke is skipped unless `RAGGED_CLAWS_DURABLE_LIVE=1`, isolated acknowledgement
`RAGGED_CLAWS_R2_ISOLATED_ACK=NON_PRODUCTION_ONLY`, an R2 HTTPS endpoint, a bucket beginning
`ragged-claws-smoke-`, and a new prefix beginning`isolated-smoke-` are explicitly configured.
AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY must be supplied through the environment, never CLI args,
capture metadata, logs or Git. The prefix must have no authority. The smoke writes only invented
data to an existing isolated bucket and leaves it for separately authorized cleanup; it never
creates a bucket. It was **not run** for this implementation. No configuration values are printed.

## Inactive workflow and activation gates

`ops/durable-runtime.yml.template` is outside `.github/workflows`, has no schedule, binds no secrets
and contains an explicit false job gate. It checks out main, uses least privilege and contains only
an offline rehearsal. Every future manual/scheduled entry point mutating the same durable namespace
must use the literal shared concurrency group`ragged-claws-durable-production` and
`cancel-in-progress:false`; do not key that group by branch, run or workflow name. No private state
is uploaded as Actions artifacts and no pull_request_target execution is used.

Activation is a separate operational review: user-established account/bucket and cost limits,
source/cloud retention rights, narrow credential scope/secret handling, actual isolated R2 restore
and failure tests, supported historical schema recovery, and a concrete reviewed production
operation/transport configuration, including private failure-journal reconciliation/durability.
Only then replace the false gate/rehearsal, install an approved
workflow and schedule, and verify shared serialization across all writers. Copying the template
alone does not supply a production pipeline. No unattended live acquisition is enabled here.

## Official semantics reviewed (2026-10-23)

R2 documents atomic conditional PutObject, including create-once If-None-Match:*; it also warns
that a negative read does not settle an unknown in-flight write. We use only GET and conditional
PUT, with no automatic write retry. [R2 extensions](https://developers.cloudflare.com/r2/api/s3/extensions/),
[S3 compatibility](https://developers.cloudflare.com/r2/api/s3/api/).

S3 PutObject documents409/412 conditional failures. GET supplies body length and ETag; our transport
uses ETags as opaque conditions and independently verifies SHA256/size, rather than interpreting
ETag as a content hash. [PutObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html),
[GetObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html).

Cloudflare's boto3 example uses an R2 endpoint and region`auto`. Our isolated factory follows that
boundary without provisioning anything. [Official boto3 example](https://developers.cloudflare.com/r2/examples/aws/boto3/).
GitHub documents shared concurrency groups and cancel-in-progress control; the inactive template
requires one stable group across future writers. [GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
