# Accession and index-reference review — offline proposal

The separately committed [v2 card](../research/audits/accession-reference-v2.json) proposes
submission-reference grouping on the already captured September 10 index. It grants no
acquisition permission. The original v1 declaration, parser, receipt, rejection and outputs
remain unchanged. This is source-specific review metadata, not a canonical schema,
investment preregistration, population-coverage claim or funding decision.

## Source basis and its limits

Reviewed October 24, 2026, only the two official policy/reference pages:

- [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data),
  “Using the EDGAR index files,” “Paths and directory structure” / accession description,
  and “Post-acceptance corrections and deletions”: accession identifies an accepted submission;
  index filenames locate complete submission text; the prefix can identify a submitting agent.
- [Webmaster FAQ](https://www.sec.gov/files/about/webmaster-faq.htm), accession numbering,
  header/timestamps and ticker/CIK convenience-file sections: submitting-agent and clock
  distinctions remain important; current convenience mappings do not establish historical listings.

Those statements do not establish equality of every observed different-CIK path's response,
identify a reference's reporting-owner role, or resolve issuer/security/listing identity.
The grouping and address choice below are project proposals, not additional SEC guarantees.
No index, filing body, directory or provider data was requested for this review.

## Distinct identities and deterministic proposal

| Layer | Meaning in this review |
| --- | --- |
| Physical row | One retained source line and original file position, including exact duplicates |
| Literal reference | Exact CIK/name/form/raw date/path tuple; repeated copies retain multiplicity |
| Accession group | Candidate submission-reference identity using the complete dashed accession |
| Capture address | One proposed locator per compatible group, not issuer identity or byte-equality proof |
| Economic Event | Existing body-derived transaction identity; none acquired or created here |

The card was committed before implementation at `688e7e152a292471dec7ea33a62dddf9a1b7abc3`,
SHA256 `d76f8ff1e41aa0b4ecf261b2dd87e13c50f7f431c271f2688cb44f4702410765`.
Group only structurally validated literal references sharing the entire dashed accession.
The existing v1 structural parser still validates index day, raw filing dates and literal
path/accession/index-CIK binding; no arbitrary URL, query, encoded path or traversal is accepted.
Exact form and normalized official filing date must agree within a group. Raw date text remains
preserved even where two representations describe the same date. Names and valid CIK/path variants
are reference metadata; they neither create separate independent signals nor merge entities.

True form/date disagreement retains all rows and rejects that group with reasons. Any such
conflict blocks the entire first-four proposal; no difficult group is skipped to fill slots.
Malformed structural evidence raises explicitly. Compatible groups retain every physical row,
source position, raw line/date/name/CIK/path and exact-reference multiplicity. Groups sort by
accession; one proposed address uses lowest numeric index CIK, then literal filename. No issuer,
name, role, transaction yield, identity resolution or outcome informs that choice.

Only when all groups are compatible are the first four exact Form 4 accession groups proposed
lexically. Forms 4/A and other forms remain visible and unselected. These are future candidate
addresses, not authorized requests or acquired bodies. Any separately authorized later body must
validate header accession/form/official date through the existing parser and derive issuer/owners
independently. Differing captured variants would require explicit version/conflict handling;
there is no last-write-wins rule or invented alias-equivalence test.

## Observed retained-index accounting

| Measure | Count |
| --- | ---: |
| Physical rows | 3,857 |
| Exact duplicate rows | 30 |
| Distinct literal references | 3,827 |
| Accession groups compatible under this proposal | 2,470 |
| Compatible groups with multiple CIK/path references | 1,128 |
| Critical form/date conflicts | 0 |
| Form 4 rows / accession groups | 1,053 / 490 |
| Form 4/A rows / accession groups | 34 / 11 |

An independent standard-library CSV/set/group oracle checks these counts, every grouped physical
row/position and the deterministic proposals against the full retained bytes. Group counts by
every form, complete reference lineage and unresolved limits are in the JSON review. The new
compatibility result does not rewrite the original v1 rejection or prove equivalent body bytes.

Proposed first four addresses below are **not requested**. All have source official filing date
September 10, 2024. The relative path is prefixed by the documented SEC Archives root:

| Accession | Proposed literal filename |
| --- | --- |
| `0000035527-24-000224` | `edgar/data/35527/0000035527-24-000224.txt` |
| `0000060086-24-000179` | `edgar/data/60086/0000060086-24-000179.txt` |
| `0000080420-24-000066` | `edgar/data/80420/0000080420-24-000066.txt` |
| `0000101778-24-000120` | `edgar/data/101778/0000101778-24-000120.txt` |

September 11 remains unattempted and unknown. Bodies, economic events, issuer/owner/security/listing
coverage, first-public/collector/decision availability, prices, outcomes and potential holding
overlap remain unknown, expressed as null populations rather than zero events. No actual decisions
or entries exist. This biased archival scope is not representative or a market census. A 2026
capture is not authenticated as the original 2024 index version or historical collector completeness.

## Pinned offline interface and preservation

```text
uv run --frozen python -m ragged_claws.ingestion.sec_references --rule research/audits/accession-reference-v2.json --scope research/audits/population-timing-v1.json --captures tests/fixtures/sec-population/audit-v1 --output NEW_EXTERNAL_OUTPUT
```

The interface requires the exact rule, original scope, receipt and raw hashes. It reuses the
accepted receipt/evidence validator; unknown rule/receipt formats or changed inputs reject.
It writes only to fresh external output and reads no network, contact configuration or credentials.
The report identifies `offline_reinterpretation_not_acquisition`, embeds the original receipt
verbatim as data, links its hash/raw/declaration and records rule/code/lock/runtime/output hashes.
It creates no v2 acquisition record, new request chronology or successful second index.

V1 remains available separately and still rejects the retained multi-reference frame. All existing
code, models, schemas, hypotheses, journals, raw objects and failed evidence retain their bytes.
No generic policy override, mutable scope unpinning, event/return engine or new dependency is added.
The new module recovers validated rows only from v1's explicit reference-conflict result; every
other structural error still raises. Tests use invented variants, not invented equality as proof
about real aliases, and preserve the original capture-evidence regression probes unchanged.

Single next dependency: independent review of this reference rule and its proposed candidate
addresses before any separately authorized acquisition plan. No unused v1 budget resumes. Actual
historical identity/listing/price/terminal coverage, accepted methods/reconciled untouched evidence,
surviving validation, real elapsed forward observations, durable failure audit and pilot rules
remain unmet. Issues 9/10/15 stay open; no paper start, schedule, cloud, charge, funds or order.
