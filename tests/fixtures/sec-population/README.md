# Recorded SEC audit evidence and invented counterparts

`audit-v1/manifest.json` is the exact acquisition receipt, including the initial parser
rejection. Its sole object is the complete, unmodified 337,624-byte HTTP200 response
from the declared September10,2024 daily master index, captured October24,2026 UTC.
SHA256 is its filename: `ce75cb8eaa6d7f7fe5976aa4c8aa9e59c199b62c9025fa6cc769cc54cd1a7f5b`.
The second index was unattempted; zero submission GETs occurred. No restart is authorized.

Attribution: U.S. Securities and Exchange Commission, EDGAR public archives.
The exact requested URL/retrieval timestamps/status/hash are in the receipt.
Official [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
and [Webmaster FAQ](https://www.sec.gov/files/about/webmaster-faq.htm) were reviewed
October24,2026 UTC: government-created index and public filing content are reusable,
scripted access needs a declared contact and fair-access limits. No request header,
private contact or other credential is retained here. Source-policy pages were read
via the web tool; the one data GET used the existing private SEC UA only inside the
request process. No source pages were retrieved through a workaround.

An archived index observed in2026 is not authenticated as the original2024 version.
Do not promote index date or filer CIK to acceptance time or body issuer identity.
The offline parser correction supports `File Name` and compact dates and preserves
older filed dates separately from index day. It then rejects multiple paths/metadata
for one accession under the unchanged declared conflict rule. These source references
can reflect multiple filing participants; rejection does not accuse SEC of bad data.

`test_sec_population_audit.py` constructs explicitly **invented** indexes and altered
submission/accession/date/no-P/S/unknown-clock/security cases from the separately
attributed original Form4 fixture. They are engineering examples, not acquired
filings, observed forward events, prices, capacity estimates or investment evidence.
