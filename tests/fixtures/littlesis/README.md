# Recorded LittleSis API-v2 fixture subset

Attribution: **LittleSis / Public Accountability Initiative**, source response copyright
`LittleSis CC BY-SA 4.0`. Database content is licensed under
[Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).
Preserve this attribution, source links, license and change notices when redistributing this
subset or adaptations. No endorsement is implied. This data license does not change the
repository's software license.

Captured 2026-10-22 with one unauthenticated GET per explicit documented URL, no redirects,
retries or challenge handling. All three returned HTTP 200 JSON with the above license metadata.
Raw JSON files are **unmodified exact response bytes**; `.gitattributes` prevents newline conversion.
Adjacent provenance files record URL, acquisition timestamp, byte size and SHA-256. They are
locally authored acquisition metadata; this README is a locally authored attribution notice.

| Raw response | Source | Acquisition UTC | SHA-256 |
|---|---|---|---|
| `recorded-297069.json` | [Relationship 297069](https://littlesis.org/api/relationships/297069) | 2026-10-22T21:55:38.514847Z | `6e3db8165b8fcacb08a5f53e2f85370f32897def2ca420aa7420b4eed80460a4` |
| `recorded-position-page.json` | [Entity 72489, category 1, one page of one result](https://littlesis.org/api/entities/72489/relationships?category_id=1&per_page=1) | 2026-10-22T21:55:58.863635Z | `7cb5e5627484e2bfb3c7a4d2ecc9d18aa1a72141e457e466b5a02b45b51747c0` |
| `recorded-1565630.json` | [Relationship 1565630](https://littlesis.org/api/relationships/1565630) | 2026-10-22T21:56:18.664182Z | `cfeca2dbe39876a467ca7c3722709fb573ca7d18fded632b6d7ce4fde5fdec38` |

Relationship 1565630 provides the documented Robert Mercer (72489) → Renaissance Technologies
LLC (102097) position example. The response reports `2010-01-00`, unknown end/current status,
and curation in 2019. Those values do not prove historical publication or a current role.
The list page contains no included entities and advertises another page; it is intentionally
incomplete and no further pages were collected. Relationship 297069 supplies a year-precision
start and day-precision end, as well as included person/organization records.

Tests create invented mutations in memory for invalid IDs/dates, conflicts and scope checks;
they are not represented as additional recorded source captures. Canonical/staged derivatives
change ID representation, category names and date structure, retain unknown knowledge time,
and include their own transformation change notice. Source database statements are not
independently verified primary evidence or investment/misconduct conclusions.

The official source/version, access/terms review and mapping rules are recorded in
[`docs/16-littlesis-snapshots.md`](../../../docs/16-littlesis-snapshots.md).
