# LittleSis context snapshots (M1 / issue #8)

## Source contract and access review

Reviewed 2026-10-22 against the official
[LittleSis Rails repository](https://github.com/public-accountability/littlesis-rails/tree/57bf9f77771b62d0984e070c5561554d56f58f4e),
commit `57bf9f77771b62d0984e070c5561554d56f58f4e` (2026-10-05).
The deployed service may change independently; unsupported shapes fail explicitly.
The relevant source files at that commit are:

- `app/views/api/index.html.erb`: documented API-v2 entities, relationships and pagination.
- `app/controllers/api/entities_controller.rb`: entity relationship membership, category filter,
  explicit page and per_page parameters.
- `app/utility/api.rb` and `app/utility/api/serializable.rb`: database license metadata,
  resource IDs, included entities and pagination.
- `app/utility/api/serializer.rb`, `config/api.yml`, `app/models/relationship.rb`:
  fields, category direction, updated_at serialization and nullable current flags.
- `app/utility/ls_date.rb`: zero month/day represent missing precision.
- [Terms of use](https://github.com/public-accountability/littlesis-rails/blob/57bf9f77771b62d0984e070c5561554d56f58f4e/config/pages/terms_of_use.en.md):
  documented API automation and CC BY-SA 4.0 database licensing. The software GPL license
  is separate. No LittleSis implementation code is copied into this adapter.

The API documentation landing page had a reported access denial. It was not retried or
bypassed. Three explicit documented API resource requests succeeded with HTTP 200 JSON,
without authentication, challenge handling or retries. Exact recorded bytes and acquisition
metadata are in `tests/fixtures/littlesis/`; no claim of complete graph coverage follows.
There is no available LittleSis connector. The optional HTTP helper makes one explicit
request and stops on non-200 responses, redirects, HTML/challenges or invalid JSON.
It uses its own constant User-Agent; it never reads SEC contact configuration.
The caller supplies the HTTP client/transport and timeout policy; no live requests occur in
default tests or the CLI. The helper does not traverse, auto-page or bulk collect.

Supported locators are HTTPS `littlesis.org/api/entities/<positive integer>`,
`/api/relationships/<positive integer>` and `/api/entities/<id>/relationships` with an explicit
`per_page` between 1 and 20. Optional positive `page` and category_id 1–12 are accepted.
Other endpoints/parameters are rejected. A list must return Relationship primary resources,
matching either endpoint of the requested entity, the category filter, page metadata and
requested count bound. Included Entity context remains permitted. Empty pages are retained.
A single resource must match its requested type and ID. Contradictions retain captured raw
bytes but publish no staging or canonical state.

## Time, identity and evidence

`LittleSisResource` stages the full source resource JSON, raw partial dates, curation string
and parsed aware timestamp, source URLs, and a deterministic per-resource semantic hash.
The exact full response is immutable content-addressed raw evidence with a retrieval manifest.
Unknown fields, amounts and nullable source flags remain in raw/staging; numbers are parsed
with Decimal rather than converted through binary floats.

Effective start/end map to canonical `Relationship.valid_from/valid_to`. `YYYY`, `YYYY-MM`,
`YYYY-MM-DD`, `YYYY-00-00`, and `YYYY-MM-00` retain source text and year/month/day precision.
Null/blank dates map to unknown; their distinct original values remain in staged JSON/raw.
Invalid dates and provably inverted effective intervals fail. Computed date bounds are used
only to detect contradictions, never persisted as invented dates. Equal start/end is retained
without inventing an interval duration or a source end-date inclusivity convention.

`updated_at` means database curation, not original publication. Collection time becomes
observation/snapshot time. Canonical observation public_time and relationship known_from/to
stay unknown. No observed-time forward-use policy is introduced. Existing PIT eligibility
and feature-snapshot validation exclude these relationships even when effective dates are
years older than collection. A nullable is_current flag does not supply an end or public date;
false with missing end also stays missing. This adapter creates no predictive features.

Entity identity is UUIDv5 over the LittleSis immutable numeric entity ID and namespace;
relationship identity uses the immutable numeric relationship ID, not endpoint names or pairs.
Source Person maps to canonical person, source Org to organization. Business subtypes do not
establish issuer, share class, listing, ticker or CIK identity. Unknown types/endpoints remain
countable unresolved, with no orphan canonical relationship. Source entity1→entity2 direction
is preserved. Categories map to neutral canonical slugs: position, education, membership,
family, donation, transaction, lobbying, social, professional, ownership, hierarchy, generic.
Unknown categories are staged and excluded with a reason. Source role/descriptions, aliases,
category attributes, current flags and URLs remain staged rather than becoming interpretation.

Existing explicit `ExternalIdentifier(OTHER, namespace="littlesis.entity")` bindings can reuse
canonical subjects. They require a persisted subject, observation, matching provenance pointer
and verified raw hash. Ambiguous bindings and contradictory person/organization types fail.
No display-name matching or household collapse occurs. Primary entity names/provenance and
existing aliases are preserved exactly; new source profile values remain in separate snapshots.
New identifier claims are evidence-specific and have unknown historical knowledge time.

Every accepted snapshot has an ENRICHMENT SourceObservation, provenance, attribution and
change notice. Frozen mappings link source resource IDs to canonical IDs and report imported,
reused, unresolved or excluded status/reason. A snapshot mapping is additional evidence of an
existing fact, not an independent relationship signal. Underlying primary references are not
exposed in the reviewed API response. URLs present in a response are retained; this adapter
does not invent citations or claim to verify the original documents.

## Revisions, persistence and compatibility

Exact response versions use the existing namespace/request-identity/raw-hash observation ID
rule. Same-byte replay preserves first observation time and frozen mapping decisions despite
later identity-catalog enrichment. A bundle can republish its own missing datasets after an
interrupted write. It does not reconstruct missing external identity evidence or arbitrary
dependencies removed from other accepted bundles; recover those from their original captures.

Across snapshots, relationship semantic hashes exclude only that resource's updated_at.
Resource ordering and unrelated included profile edits cannot rewrite the first canonical
relationship, its first provenance, or its source-observation tuple. New snapshot mappings
record additional evidence against the same canonical ID. Distinct source relationship IDs
sharing endpoints coexist. A material change to an accepted relationship raises
CanonicalConflictError, leaves analytical files unchanged and retains new raw bytes. Such a
revision needs an explicit reconciliation workflow; it is never last-write-wins or silently
discarded. Source profile edits do not overwrite canonical entities.

`LittleSisSnapshot` / `LittleSisBundle` are versioned adapter staging envelopes, persisted in
`staging/littlesis_snapshot_mapping.parquet`; canonical data remain in curated Parquet.
Relationship is added to the existing generic canonical store and DuckDB rebuild discovers
its Parquet view automatically. No canonical model or generated schema changes, schema bump,
data migration or mandatory catalog mutation are needed. Existing datasets remain readable.
Rebuild DuckDB when a new curated relationship dataset needs a query view.

Publication preflights ID conflicts across all target files before analytical writes. Individual
file replacement is atomic; cross-file publication is not transactional and ingestion assumes
a single writer. Preserve accepted staging bundles and raw manifests for recovery.

## Reproducible local use

```text
uv run ragged-claws ingest-littlesis tests/fixtures/littlesis/recorded-1565630.json --source-url https://littlesis.org/api/relationships/1565630 --data-dir data
```

The CLI captures the local file at current ingestion time, reports frozen mapping-status counts
(including zeros), reasons, relationship and PIT-ineligible counts, snapshot ID/time and attribution.
It does not substitute the fixture's original retrieval time; exact fixture replay with acquisition
time is demonstrated by the offline Python tests. Rejected snapshots report a reason/count and
exit 2. Replaying an accepted snapshot reports its original mapping status, not a new-write count.

Default verification uses the three tiny recorded open-data responses plus explicitly invented
mutations generated inside tests. No subscriptions, graph scoring, primary-evidence verification,
historical backfill, scheduler, cloud storage or investment validation is supplied by this change.
