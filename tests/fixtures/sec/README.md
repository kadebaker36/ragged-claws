# Recorded public SEC ownership fixture

`0000950170-24-105263.txt` is the **exact 14,338 response bytes** of the public SEC complete
submission, acquired on October 22, 2026. `provenance.json` records the precise retrieval time,
source URL/accession, byte count and SHA256. Git treats this file as binary to prevent newline
conversion, whitespace repair or platform-dependent fixture hashes.

Source:
https://www.sec.gov/Archives/edgar/data/70858/000095017024105263/0000950170-24-105263.txt

Filing index:
https://www.sec.gov/Archives/edgar/data/70858/000095017024105263/0000950170-24-105263-index.htm

SHA256: `5eb55738b2b6e3a2e76cb6ffcbfb6e415dbc5c7af763c9c6ced9e30e7171e732`.

The real filing reports issuer CIK 0000070858, reporting owners 0000315090 and 0001067983,
three Table I S rows dated September 6/9/10, 2024, and seven footnotes. Reported shares are
1,081,102 / 1,721,366 / 2,994,625; reported prices are 39.6682 / 39.5742 / 39.2978. These are
reported prices with footnote qualifications, not reconstructed executions. All ownership is
reported as indirect. Header acceptance is `20240910191316`; official filing date is 20240910.

The default test suite reads only this local file. Edge cases are **invented in-memory mutations**
of the recorded bytes, explicitly labeled in tests; they are not represented as real SEC filings.
Tests that preload typed owner entities use an explicitly invented identity catalog. They prove
exact CIK binding without claiming the ownership XML itself established owner entity types.

Reproduction requires a locally configured real SEC declared User-Agent/contact and one explicit
resource request through `SecFilingClient`. Do not use fixture contacts for live requests. The
contact used for acquisition is kept in ignored local configuration, absent from this fixture,
metadata, tests and Git. Stop on access denials; no broad crawling is needed.

The SEC [reuse FAQ](https://www.sec.gov/files/about/webmaster-faq.htm) permits access/reuse of
EDGAR public filing content. Retention classification is `public`; attribution and original source
URL are retained. This is public filing evidence, not a claim of investment performance or misconduct.
