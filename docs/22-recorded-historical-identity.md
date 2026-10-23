# Historical identity dossier: September 2024 SEC diagnostic

**Bounded result: share-class candidate recorded; event/listing mapping remains unresolved.**
No market prices or returns were acquired. This does not establish population mapping coverage,
an accepted statistical method, untouched validation or funding readiness. The methods card in
doc21 remains an unapproved proposal; its twelve-episode floor is not a universal funding wait.

## Source/access scope and retained bytes

Reviewed October23,2026: SEC [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
and [Developer Resources](https://www.sec.gov/about/developer-resources) specify a declared contact
User-Agent, efficient explicit requests and a total ten-request/second ceiling. The
[webmaster FAQ](https://www.sec.gov/files/about/webmaster-faq.htm) permits reuse of public EDGAR
filing content and distinguishes acceptance from dissemination. Acceptance is not measured first
public availability. Existing SEC acceptance+five-minutes remains an explicit research assumption.

Exactly **three bounded GET captures**, covering **two additional filing accessions**: Schedule13G/A
complete submission; annual-report filing index; annual-report primary document. No crawling,
provider/account/key requests, redirects, retries, current ticker lookup or symbol universe.
The existing ignored SEC UA was used solely for these SEC requests and was not logged/copied.
Existing SecThrottle was set to one second; status403/429/challenge/non200 would stop the sequence.
Response byte limits were512KiB,128KiB and14MiB, checked before/while streaming; all returned200.
The acquisition used a small external bounded-httpx script, not a new production live client.

The fixed offline fixture manifest is
`tests/fixtures/identity/sec-2024/evidence.json`. It records exact requested/canonical URLs,
retrieval instants, statuses, limits, sizes, full hashes, field-byte spans and retention basis.
Raw full responses and acquisition receipts are content-addressed outside Git in
`historical-identity-acquisition`; exact response representations below have not been reserialized.

| Evidence | Public/source timing | Representation in Git | SHA256 |
|---|---|---|---|
| [0001104659-24-020016](https://www.sec.gov/Archives/edgar/data/70858/000110465924020016/0001104659-24-020016.txt), SC13G/A, Vanguard filing concerning BAC | Header accepted `20240213165550`; filed2024-02-13; ownership event date2023-12-29, signature2024-02-13 | Full13,356-byte submission | `252953852009256b2506304a8c213db7791243b5f6b524b4d271dda4897d6f71` |
| [0000070858-24-000122 index](https://www.sec.gov/Archives/edgar/data/70858/000007085824000122/0000070858-24-000122-index.htm) | Filed2024-02-20; accepted `2024-02-20 17:01:30`; report period2023-12-31 | Full15,942-byte index | `b60ee0e1f1c2d8a5946f4e93466b8a8022af0650e60de56ac9fff6a865a84e14` |
| [Annual report cover](https://www.sec.gov/Archives/edgar/data/70858/000007085824000122/bac-20231231.htm), same accession | Filing date from index; cover/report dates do not define continuous listing validity | Exact1,199-byte contiguous table-row excerpt, not full response | Excerpt `e678e8624730ecfa12611b8a03fedd58027f45c79e0df7cecdfe75688fcbac1b` |

Annual-report full response was12,861,776bytes, SHA256
`ae256da438e3a3311c38f5a80641e59e43f21cfe58b46d3f54a1a5794eeaa8da`.
It remains outside Git; the excerpt is precisely `parent[1445367:1446566]`, zero-based byte offsets,
end-exclusive. The index advertised12,861,659bytes; the captured response size is independently
reported, not silently equated. No claim of identical historical bytes is made from a2026capture.
The observed hash is the exact2026response. No multi-megabyte report is added to Git or frozen
research state. The excerpt observation/manifest explicitly records parent hash/size/offsets.
It is evidence derived from a captured response, never represented as the full annual report.

## Claim-by-claim decision and lineage

`recorded-sec-identity/1.0.0` is a **fixed reviewed-fixture importer**, not a general13G/10K parser.
`reviewed-byte-spans/1.0.0` identifies the explicit extraction/review contract. Pinned content and
metadata hashes reject substitutes. SourceObservation and raw manifests carry retrieval/status/
representation metadata; separate Provenance records identify retrospective enrichment/review.
Claim byte offsets are retained in each raw manifest through freeze. Exact evidence fields are
listed in the fixture manifest, so the claims can be checked without network access.

| Claim | Source field | Canonical treatment | Temporal limitation |
|---|---|---|---|
| Issuer CIK0000070858 |13G/A SUBJECT COMPANY header and annual index filer CIK; original Form4 issuer | Existing normalized-CIK Entity only, same Entity UUID; separate sourced CIK claim, no Entity mutation | CIK identifies issuer, not security or venue |
| Common-stock CUSIP060505104 |13G/A cover “Title of Class of Securities”, CUSIP; repeated Item2(d)/(e) | Deterministic Security UUID from strong CUSIP, COMMON_STOCK candidate; separate ExternalIdentifier | Identifier assertion was public by filing date; source does not prove uninterrupted validity through September2024 |
| Common Stock, par value$0.01 | Annual cover `dei:Security12bTitle` | Dossier evidence consistent with common class; no amount/currency/price fields added to event | Cover is discrete dated evidence; not a spanning validity interval |
| BAC | Annual common cover `dei:TradingSymbol`; original Form4 `issuerTradingSymbol` | Candidate symbol metadata only; no ticker-derived permanent ID | Ticker equality cannot identify a class or establish continuity |
| New York Stock Exchange | Annual common cover `dei:SecurityExchangeName` | Raw exchange text retained; **no MIC assigned**, no Listing created | No separately reviewed MIC mapping or permanent listing identifier; no supported effective interval |
| Common Stock on September Form4 | All3TableI security titles | Original Event payloads/evidence untouched; no Controls identity bindings | Same title/name/ticker across dates is insufficient to bridge missing listing/class continuity |

The13G/A issuer association is checked through typed CIK/Entity identity, not a top search result.
Security creation uses the existing CUSIP helper and provenance; no CIK/ticker/name Security ID.
No instrument FIGI or reviewed alternative listing creation basis is present. The annual report
also lists other securities: its common row is isolated explicitly and does not make preferred
shares interchangeable with the reported common stock. No ownership attribution, price currency,
venue of transaction or open-market trade classification is inferred from a P/S code or class title.

Canonical identifier `known_from` is conservatively **date-only2024-02-13**, derived from the13G
public filing date, not2023-12-29or2026retrieval. A same-day query before that entire date has elapsed
is ineligible. Raw acceptance precision remains in the pinned header/dossier; no exact first-public
timestamp is invented. The2026capture/review is retained separately (`observed_at`/`derived_at`).
This supports a retrospective query that the CUSIP assertion was knowable by September2024; it
does **not** make the missing valid interval or event binding historically defensible, and it
does not claim our collector possessed it then. No feature uses it as an investment signal.

Both `valid_from` and `valid_to` of the identifier assertion remain unknown. No broad historical
interval is manufactured from a cover date. Do not construct a bare Listing with absent bounds:
the generic catalog treats absent Listing endpoints as unbounded, which would express a stronger
claim than this evidence permits. Here no Listing is imported at all. Tests use explicit UNKNOWN
TemporalValue boundaries to exercise unavailable/ambiguous historical queries. This slice does not
change or reinterpret that established catalog API or its canonical serialization.

## Separate diagnostic and remaining gap

Offline preparation appends the recorded observations/provenance/claims and one unbound Security
candidate. It uses the existing IdentityCatalog, storage and SEC adapter; no second resolver,
new pricing path or current-symbol filter. It does not mutate the original3Event records. Controls
remain empty, all original public/actionable timing and source families remain intact, and prices/
benchmark identity are absent. Independent evidence is not attached as another purchase/sale event
or a vendor convergence vote. A snapshot contains all raw objects/manifests and canonical claims.

Candidate/input/qualifying events remain3, distinct event issuers1; canonical Security candidates1,
Listings0; event-bound Securities/Listings0. Each20/60/90horizon has3unresolved_security outcomes
(9rows total), zero complete outcomes and null returns/distributions. The reason remains
`no_source_backed_security_listing_binding`; no inference evaluation is run and investment validation is
not evaluated. This lack of status transition is the honest result of insufficient interval
evidence, not a failure to preserve the acquired candidate. Old3-unresolved reports stay immutable.

Next bounded acquisition need: independent source-backed class/listing identity and validity
covering the September11,2024actionable open, including a reviewed venue/MIC/permanent listing
creation basis and evidence against intervening class/listing changes. Do not quietly bridge
February to September or use a current provider answer as historical proof. Population-wide
identity/terminal coverage, price access/terms, accepted dependence methods/untouched evidence,
durable failure audit and actual elapsed forward behavior remain separate gates. #9/#10/#15open.

## Offline regeneration

Use fresh external paths. The new command never requests network or credentials:

```text
uv run --frozen ragged-claws research-prepare-identity-diagnostic --evidence tests/fixtures/identity/sec-2024 --sec-fixtures tests/fixtures/sec --protocol research/hypotheses/sec-p-s-v2.json --output PREPARED
uv run --frozen ragged-claws research-freeze PREPARED --output FROZEN
uv run --frozen ragged-claws research-build FROZEN --output OUTPUT --registry REGISTRY
```

Repeated `import_identity_evidence` is idempotent; same-ID/different-payload storage fails. Use
a fresh preparation directory for a full new diagnostic. Changed protocol/model/code hashes
produce separately scoped snapshots/results rather than rewriting old artifacts. All default
tests are offline; no automatic live test, accounts, subscriptions, runtime or trading is added.
