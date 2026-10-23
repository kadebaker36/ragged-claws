# Analysis archive and inspection-history recovery

Bounded offline archival engineering for #15/#10. No real evaluation, source or price
acquisition, cloud configuration, scheduled runtime or investment approval is added.
All demonstrations use invented or empty inputs and local fake object storage.

## Format and compatibility

`Generation`, `Pointer` and `CloudPolicy` retain their exact 1.0.0 models, serialized
defaults and hash rules. Canonical models, 19 generated schemas, Protocol, BuildConfig,
Snapshot, Registration, AnalysisPlan, Approval and Evaluation are unchanged. No
persisted artifact is rewritten or migrated. The new reader accepts old generations
without the extension; old readers reject new extension paths. Unknown versions and
files fail closed. No fallback interprets future formats as current ones.

The explicit additive format is `analysis-archive/1.0.0`:

| Path under durable root | Content |
| --- | --- |
| `research/analyses/EVALUATION_UUID/evaluation.json` | Original analysis-result/1.0.0 |
| `research/analyses/EVALUATION_UUID/evaluation.md` | Exact original renderer output |
| `research/registry/plans/MODEL_SHA256.json` | Referenced analysis-plan/1.0.0 |
| `research/registry/approvals/MODEL_SHA256.json` | Referenced analysis-approval/1.0.0 |
| `research/registry/attempts/ATTEMPT_UUID.started.json` | Original full start or declared reduced header denial |
| `research/registry/attempts/ATTEMPT_UUID.analysis.json` | Optional original plan/result hash scope |
| `research/registry/attempts/ATTEMPT_UUID.finished.json` | Optional original finish and inspection interval |
| `research/registry/archives/MODEL_SHA256.json` | Content-addressed archive inventory and review |

Frozen inputs remain `snapshots/SNAPSHOT_UUID/`, sealed builder results remain
`research/SNAPSHOT_UUID/` and registrations remain in their existing registry directory.
Top-level `analyses` and arbitrary analysis files remain unsupported.

An archive seal records exact path/SHA256 pairs for all retained analysis, plan,
approval and attempt files, plus `destination=private_operator_archive`, an explicit
true absolute-path review attestation and the exact CloudPolicy review reference.
An optional attempt-to-approval hash map retains approvals used by denied/interrupted
attempts that produced no Evaluation. This map records use, not approval validity or
permission to execute a denied scope. Referenced approvals/plans must be present;
unreferenced copies are rejected. Approvals with preserved-history attestations must
retain every attested journal file with its exact hash.

`seal_archive` appends an inventory; it does not validate, publish, approve research or
select favorable results. Subsequent histories append seals; earlier seals remain
immutable, and their declared files must still match. The union must cover the exact
current archival inventory. Generation parent checks retain every existing path and
immutable byte, including old seals. Restore also checks immutable parent manifests.
Only existing root curated/staging append semantics remain mutable. An initially
omitted external inspection cannot be discovered by hashing a supplied directory;
operator reconciliation and an independently retained parent remain necessary.

## Historical checks and limits

Publication and restoration retain bounded path, symlink, case-collision, duplicate
JSON, metadata-secret, size/Parquet-expansion, typed model and source-rights checks.
Full journals retain the legacy validator plus stronger scope checks. Header denial
is exactly `{"mode":"diagnostic","phase":"analysis_header_rejected"}` and can have
only an unsuccessful, uninspected finish without an inspection interval. Missing
finish is preserved, never invented. Full starts must match their retained frozen
snapshot, mode, protocol, period and potential coverage. Real successful attempts
must be inspected, and every successful full attempt must retain its builder result.
Post-read failures retain the conservative selection start through
max(period end, coverage); true pre-read denials remain false. Interrupted real starts
remain potentially inspected under the existing registration guard.

A real start published without a finish establishes a conservative potential interval.
A descendant may leave it unfinished or append an inspected finish covering that entire
interval. It cannot append an uninspected denial or a narrower inspected interval to
recover an untouched claim. This comparison runs before publication writes and against
every pinned ancestor during restore, using immutable retained start bytes. Initial
pre-read denials already containing both start and finish remain supported. No finish
is synthesized and no exceptional reconciliation mechanism is introduced. A genuine
completion that cannot retain the published interval fails closed pending separate review.

Evaluations require matching frozen inputs/results, copied original rows, exact
plan and optional approval, protocol/code/lock/runtime/origin hashes, the original
UUIDv5 identity formula and a matching successful analysis scope/finish. Real modes
also require their original matching registration/approval. Plans must match declared
protocol/features/period/mode, feed/adjustment and frozen price-provider namespaces.
An unrelated root or other snapshot cannot supply a missing dependency: the existing
per-loader closure validators still run for root, each frozen input, and each result
with only its explicitly matching frozen input.

Closure is bidirectional: every successful analysis sidecar with a non-null result hash
must resolve to exactly one retained, validated Evaluation JSON/Markdown in the same
snapshot/plan/result context. Optional approval identity is part of the Evaluation ID.
If otherwise identical scopes have different approvals, explicit existing attempt-to-approval
bindings must resolve that ambiguity in both directions; unresolvable scopes reject.
The builder's original sidecar has a null result hash and does not require an Evaluation.
Denials and unfinished attempts do not acquire invented outputs. A successful empty
builder result may omit its row envelope only when the matching frozen Event population
is empty; nonempty inputs still require the row file.

The parser checks the complete declared event/horizon inventory, deterministic row
IDs, snapshot/event/outcome/status relationships, exact row copies, existing pure cost arithmetic, report distribution
and status counts, arm counts/coverage/concentrations, primary contrast, bootstrap
summary shape/counts, conditional decision consistency and exact Markdown. It does
**not** regenerate returns, reassemble outcomes, resample the bootstrap, reconstruct
its draw digest/interval, or run a calendar-based historical execution. Those original
calculations and scientific assumptions are not certified by archival integrity.
Hash relationships detect corruption relative to the supplied sealed artifacts;
operator-created hashes are not signatures or independent source authentication.
Supported historical format/render/math semantics are explicit v1; incompatible
future changes need a separate parser, not reinterpretation of old bytes.

Restore does not start/finish an inspection, evaluate an experiment or rewrite a code
fingerprint. Existing current-environment execution guards remain intact. An old-code
snapshot can be recovered exactly while normal execution rejects it. An approval's
absolute `registry_path` remains verbatim, even after recovery to a different location;
both absolute POSIX and Windows paths are recognized on either host. It cannot
authorize that location. A different workspace or scope requires renewed
supervisor review/approval. Investment validation remains `not_evaluated`; inference
design and actual untouched evidence remain unaccepted/unestablished.

## Rights and failure boundary

Analysis inherits all frozen input/source restrictions. The source allowlist is
unchanged: reviewed SEC ownership, optional attributed LittleSis, explicit invented
namespaces; restricted/commercial/unknown data still rejects. The SEC identity family
and parent-excerpt support remain outside this durable slice. A declaration does not
launder restricted inputs. No actual cloud or vendor request is made by this work.

Absolute operator paths and approval attestations are private archival metadata.
The extension requires a review reference explicitly covering private retention and
path disclosure. It grants no public registry publication permission. The boundary
cannot verify bucket ACLs or actual entitlement: the caller must configure and review
a private destination separately. The invented review reference authorizes only the
local fake demonstration, not a real bucket, service or cloud upload.

All candidate validation and parent comparison precede PUT. Existing immutable upload,
complete remote readback, pointer CAS, indeterminate-write and private quarantine rules
remain. Failure before commit retains previous authority; a lost commit response can
still be indeterminate. Failed workspace payloads are never uploaded as a shortcut.

**A successful archive cannot preserve an unpublished read if an ephemeral runner
disappears before publication.** Remote write-ahead inspection audit, failure-history
durability/reconciliation, actual R2 recovery and reviewed serialized runtime activation
remain unmet. This extension does not establish #15 operational readiness. #9/#10/#15
remain open; no meaningful unattended acquisition or funding readiness follows.

## Offline demonstration

Use Python 3.12, the frozen environment and a fresh external directory:

```text
uv run --frozen ragged-claws analysis-archive-offline-demo --output NEW_EXTERNAL_DIRECTORY
uv run --frozen ragged-claws durable-local-inspect --objects NEW_EXTERNAL_DIRECTORY/objects --generation EXACT_ID_FROM_ARCHIVE_DEMO_JSON
```

The helper uses the existing builder/evaluator for six invented events, two fixed
engineering plans yielding positive and insufficient outputs, actual pre-read and
reduced-header denials, an empty post-read failure and an unfinished attempt. It then
publishes/restores through LocalObjects, checks exact bytes, preserves the original
operator path and rejects renamed overlapping registration after recovery. No actual
events or real-price experiment is registered or approved. DuckDB is excluded and
need not be built for the archive to be authoritative.

Focused integration tests inject plan/scope/result/finish loss and mutation, malformed
summaries/rows/Markdown/versions, parent deletion, interrupted upload, corrupt readback
and CAS conflict; previous authority and complete older recovery remain available.
Preserved original 1.0.0 object generations are also restored externally with their
original hashes; historical artifacts are never regenerated to fit current code.
