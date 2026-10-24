# Bounded outcome-blind SEC population/timing audit

**Result: incomplete acquisition and rejected index frame.** No filing bodies, prices,
outcomes, inference, registration, portfolio NAV or paper observation were acquired/run.
This does not reject the investment hypothesis or establish readiness. #9/#10/#15 remain open.

## Fixed scope and actual acquisition

[population-timing-v1.json](../research/audits/population-timing-v1.json) was committed
as `744a6f22ed52dfa8f971e0e4cfb302d3a5cd45f4` before any index or selected-body GET.
Its SHA256 is `eb21d709277f968f1dbe8932d6ea0f0325f8b2a8251765c84bda9c51dc741634`.
The declared dates are September10/11,2024; for each valid index select the first four
unique exact Form4 accessions lexically, independently of issuer, body contents or yield.
No substitution is permitted. This is a biased two-date diagnostic, not a random sample,
representative sampling frame, market-wide census or proof of historical completeness.

Budget: two index GETs, eight complete-submission GETs, one attempt/resource, serially,
at most one request/second; 2MiB/index and5MiB/submission, no redirect/retry/replacement.
The helper also stops globally on transport, oversized content or invalid index.
No directory pages, searches, other dates, providers or access workarounds are allowed.
The narrow callable acquisition helper has no default live command/config discovery.
Only an external one-shot operator script loaded the existing ignored SEC UA inside its
process; it serialized no contact/header/exception text. The private contact was not
reflected in the retained response. No other credential/account access occurred.

Actual: **one index GET**, HTTP200, 337,624 complete bytes, captured at
`2026-10-24T03:52:52.354817+00:00` (October23 in America/Chicago).
The raw SHA256 is `ce75cb8eaa6d7f7fe5976aa4c8aa9e59c199b62c9025fa6cc769cc54cd1a7f5b`.
The initial parser rejected the valid SEC `File Name` column spelling/compact dates.
The receipt retains `invalid_index` and that original error. The global stop prevented
the second index and **all submission requests**. Acquisition was not restarted after
the offline correction; unused budget is not permission to retry or replace.

The corrected offline parser handles the observed header/dates, preserves older official
filing dates separately from index day, and then finds accession/path conflicts under the
unchanged declaration. One accession appears under multiple CIK-specific paths/names.
These references can describe multiple participants in a filing; this is a mismatch with
our strict declared frame rule, not an allegation of SEC corruption or invalid filings.
No arbitrary path is selected to resolve it and no filing subset is authorized.

## Denominator waterfall and limitations

| Layer | Observed result | Meaning |
| --- | ---: | --- |
| Declared indexes | 2 | Fixed scope, not two successful captures |
| Attempted / captured / HTTP-denied / oversize | 1 / 1 / 0 / 0 | Successful bytes, then parser stop |
| Unattempted indexes | 1 | September11 unknown, never zero filings |
| September10 physical data rows | 3,857 | Rejected-index context only |
| Exact Form4 row references | 1,053 | Source rows, not economic events |
| Other-form rows, including Form4/A | 2,804, including34 Form4/A | Retained by exact form in JSON |
| Distinct Form4 accession labels | 490 | All490 have multiple metadata/path references |
| All-form conflicting accession groups | 1,128 | Strict frame rejection, no path arbitration |
| Authorized selection / submission GETs | 0 / 0 | No valid frame, not zero P/S activity |
| Observed body-derived events / intervals | 0 / 0 | No bodies; population event/overlap counts unknown |

Every rejected index row, exact locator, raw filed date, normalized filed date, index day,
form and conflict group remains visible in `rejected_index_context`. No rejected reference
is an observed zero-event filing. Valid-frame totals/selection remain unavailable; the
September11 frame and all body/event/issuer/owner/security/listing/timing populations are
unknown. The report's empty event/interval collections count only inspected body evidence,
which is absent; `population_overlap=null` expressly prevents a zero-capacity inference.
No source-derived event/public/actionable timestamps or real interval counts are fabricated.

An index captured in2026 is an observed archival version, not proof of original2024 bytes
or first-public/collector availability. Source corrections/removals and historical collection
gaps remain unquantified. Index CIK/name is filer context; body issuer is separately parsed.
Neither index date nor transaction date supplies acceptance precision. No ticker, title or
CIK is promoted to a Security/Listing. Filing prices never establish affordable positions.

## Offline implementation and clocks

`python -m ragged_claws.ingestion.sec_audit` requires the exact pinned declaration and
capture manifest, rejects extra resources/hash/size/status/budget contradictions, and writes
to a fresh output outside inputs. It performs no network/config/credential access. Index
bytes enter existing immutable raw storage as `sec.daily_master_index`, not a canonical P/S
observation. If a future separately authorized bundle contains valid selected bodies, they
pass through the existing SecForm4Adapter/parser/staging/canonical Parquet, preserving all
excluded rows, owner records, evidence and existing idempotency/conflict rules. There is
no new resolver, event engine, outcome engine or canonical/schema/dependency change.
The adapter's only extension permits the documented exact index complete-submission path;
the original index locator is retained, without guessing an issuer or changing it to another URL.

Body accounting preserves transaction date, official filing date, raw acceptance,
America/New_York interpretation, UTC public evidence, acceptance+five-minute **assumption**,
source-derived actionable open and this retrieval independently. First-ever publication,
first-ever collector receipt and historical decision availability stay unknown. There are
no actual decisions/fills/entries. A2026 retrieval never becomes a2024 policy entry.

Hypothetical supports use local XNYS sessions: closed interval from source-label actionable
open through close of the60th regular session **after** entry; entry is index zero. Sweep
starts precede ends at identical instants. Report event supports, distinct issuers and
repeat-issuer excess separately, retaining unknown timing. They are calendar overlap,
not holdings, independent periods, dollar capacity or returns. The fixture oracle is
September11,2024 13:30UTC open → December5,2024 21:00UTC close. Two same-issuer supports
plus another beginning exactly at their close have peak3 supports/2issuers, with1repeat
excess. This is invented endpoint verification, not acquired market exposure.

## Source policy and regeneration

Official [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
sections Fair access, Business hours, Corrections, Index files and Paths were reread;
the [Webmaster FAQ](https://www.sec.gov/files/about/webmaster-faq.htm) reuse, scripted-access,
dissemination/header/timestamp sections were reread October24UTC. They support narrow
scripted public access/reuse and distinguish acceptance, nightly index and variable
publication lag. The five-minute assumption is not a guaranteed dissemination bound.
No cloud retention allowlist is expanded.

The [fixture attribution](../tests/fixtures/sec-population/README.md) identifies the exact
public response/receipt and labels all generated test counterparts invented. Raw object
bytes are binary in Git to prevent line-ending changes. Use a **new external output**:

```text
uv run --frozen python -m ragged_claws.ingestion.sec_audit --scope research/audits/population-timing-v1.json --captures tests/fixtures/sec-population/audit-v1 --output NEW_EXTERNAL_OUTPUT
```

JSON/Markdown and output hashes include acquisition failure, scope/input/code/lock/runtime
fingerprints and unavailable population states. Repeated offline regeneration is deterministic
in the same locked runtime and never writes inputs. Original models, schemas, methods,
hypotheses, results and inspection journals remain unchanged. Regression tests cover
duplicates/conflicts, unsafe locators, date/type contradictions, selection/no substitution,
uncollected versus empty, body issuer versus filer, unknown/late clocks, interval endpoints,
repeat issuers, raw/hash lineage, replay/conflict and access/transport/size stop behavior.

Receipt validation requires the original declaration commit and exact declared budget for
acquisition receipts, including failed and interrupted acquisitions. The existing minimal
missing-configuration receipt may omit the budget only with zero attempts, zero retained
bytes and exclusively unattempted resources; a supplied budget must still match. Completed
responses require an exact hash/object, bounded integer size, aware request/retrieval clocks,
status and boolean completeness. Every such object is verified before output creation,
including denied/partial response bytes. Missing or unusable evidence raises `AuditError`;
it cannot become an empty or complete population. Interrupted checkpoints contain no
invented response, and genuine complete empty indexes remain valid. Receipt consistency
is an integrity check, not source authentication or proof of actual request chronology.
The original parser-stop receipt and all earlier rejected outputs remain unchanged;
corrections regenerate only into fresh external directories and do not restart acquisition.

**Single next dependency:** supervisor review of the observed multi-CIK accession/path
ambiguity and a separately versioned reference rule, before authorizing any more acquisition.
The existing declaration is not silently relaxed or replaced. Population coverage, identity/
listing/terminal/price access, accepted inference/untouched evidence, actual elapsed forward
observations, durable failure audit and pilot sizing/exit gates remain unmet. No schedule,
forward clock, subscription, cloud activation, funds or order starts with this diagnostic.
