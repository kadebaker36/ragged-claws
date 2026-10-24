"""Invented reference variants and pinned recorded index; no acquisition or alias-byte proof."""

import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from ragged_claws.ingestion.sec_audit import HEADER, AuditError, IndexConflict, parse_index
from ragged_claws.ingestion.sec_parser import parse_filing
from ragged_claws.ingestion.sec_references import regenerate, review_index

ROOT = Path(__file__).resolve().parents[2]
RULE = ROOT / "research/audits/accession-reference-v2.json"
SCOPE = ROOT / "research/audits/population-timing-v1.json"
CAPTURES = ROOT / "tests/fixtures/sec-population/audit-v1"
A = "0000000001-24-000001"


def row(
    cik: str = "10",
    accession: str = A,
    form: str = "4",
    day: str = "20240910",
    name: str = "INVENTED filer",
) -> str:
    return f"{cik}|{name}|{form}|{day}|edgar/data/{cik}/{accession}.txt"


def index(*rows: str) -> bytes:
    return (
        "Invented reference index\nLast Data Received: Sep 10, 2024\n"
        + HEADER
        + "\n-----\n"
        + "\n".join(rows)
        + "\n"
    ).encode()


def test_variants_group_once_and_duplicates_keep_multiplicity() -> None:
    source = index(row("20"), row("2", name="OTHER INVENTED filer"), row("20"))
    result = review_index(source, "2024-09-10")
    assert result["counts"]["accession_groups"] == 1
    assert result["counts"]["physical_rows"] == 3
    assert result["counts"]["exact_duplicate_rows"] == 1
    group = result["groups"][0]
    assert len(group["references"]) == 3 and len(group["paths"]) == 2
    assert sum(group["exact_reference_multiplicity"].values()) == 3
    assert group["proposed_locator"] == f"https://www.sec.gov/Archives/edgar/data/2/{A}.txt"
    assert group["alias_byte_equivalence"] == "not_established"
    assert group["issuer_or_owner_role"] == "not_inferred_from_index"
    assert [r["source_file_line"] for r in group["references"]] == [5, 6, 7]
    assert result["economic_event_count"] is None
    with pytest.raises(IndexConflict):
        parse_index(source, "2024-09-10")


def test_order_and_names_do_not_select_locators_and_amendments_stay_separate() -> None:
    rows = [
        row("20"),
        row("2"),
        *[row("30", f"0000000001-24-{n:06}") for n in range(2, 7)],
        row("1", "0000000000-24-000001", "4/A"),
        row("1", "0000000000-24-000002", "8-K"),
    ]
    a = review_index(index(*rows), "2024-09-10")
    b = review_index(
        index(*[r.replace("INVENTED filer", "RENAMED source") for r in reversed(rows)]),
        "2024-09-10",
    )
    assert a["proposed_first_four"] == b["proposed_first_four"]
    assert [g["accession"] for g in a["groups"]] == [g["accession"] for g in b["groups"]]
    assert [r["accession"] for r in a["proposed_first_four"]] == [
        f"0000000001-24-{n:06}" for n in range(1, 5)
    ]
    assert a["counts"]["compatible_groups_by_form"] == {"4": 6, "4/A": 1, "8-K": 1}


@pytest.mark.parametrize(
    "variant,reason",
    [("form", "conflicting_form_type"), ("date", "conflicting_official_filing_date")],
)
def test_critical_conflict_retains_rows_and_blocks_all_selection(variant: str, reason: str) -> None:
    other = row("20", form="4/A") if variant == "form" else row("20", day="20240909")
    result = review_index(index(row(), other, row("30", "0000000001-24-000002")), "2024-09-10")
    assert result["groups"][0]["reasons"] == [reason]
    assert len(result["groups"][0]["references"]) == 2
    assert result["groups"][0]["proposed_locator"] is None
    assert result["candidate_status"] == "blocked_by_reference_conflicts"
    assert result["proposed_first_four"] == []  # Do not substitute the later compatible group.


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.test/a.txt",
        "edgar/data/10/../a.txt",
        "edgar/data/10/%2e%2e/a.txt",
        "edgar/data/20/" + A + ".txt",
        "edgar/data/10/" + A + ".txt?x=1",
        "edgar/data/10/000000000124000001.txt",
    ],
)
def test_unsafe_or_inconsistent_locators_reject(path: str) -> None:
    bad = row().rsplit("|", 1)[0] + "|" + path
    with pytest.raises(AuditError):
        review_index(index(bad), "2024-09-10")


def test_full_accession_is_key_and_equivalent_raw_dates_are_preserved() -> None:
    result = review_index(
        index(row(), row("20", day="2024-09-10"), row("10", "0000000001-24-000002")), "2024-09-10"
    )
    assert result["counts"]["accession_groups"] == 2
    assert result["counts"]["rejected_groups"] == 0
    assert {r["filed_raw"] for r in result["groups"][0]["references"]} == {"20240910", "2024-09-10"}


def test_index_filer_is_not_body_issuer() -> None:
    fixture = ROOT / "tests/fixtures/sec/0000950170-24-105263.txt"
    filing = parse_filing(
        fixture.read_bytes(),
        accession="0000950170-24-105263",
        source_version_id=UUID(int=1),
        acceptance_timezone="America/New_York",
    )
    group = review_index(index(row("315090", filing.accession)), "2024-09-10")["groups"][0]
    assert group["index_ciks"] == ["315090"] and filing.issuer_cik == "0000070858"
    assert group["issuer_or_owner_role"] == "not_inferred_from_index"


def test_pinned_offline_regeneration_preserves_v1_and_unknown_populations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline review attempted network")

    monkeypatch.setattr(httpx.Client, "request", deny_network)
    receipt_before = (CAPTURES / "manifest.json").read_bytes()
    a = regenerate(RULE, SCOPE, CAPTURES, tmp_path / "a")
    b = regenerate(RULE, SCOPE, CAPTURES, tmp_path / "b")
    assert a == b
    assert (tmp_path / "a/output-hashes.json").read_bytes() == (
        tmp_path / "b/output-hashes.json"
    ).read_bytes()
    assert (CAPTURES / "manifest.json").read_bytes() == receipt_before
    assert a["original_receipt"] == json.loads(receipt_before)
    assert a["original_receipt"]["stop_reason"] == "invalid_index"
    assert a["second_index"]["state"] == "unattempted" and a["second_index"]["population"] is None
    assert all(
        a[k] is None
        for k in (
            "body_population",
            "economic_event_population",
            "issuer_owner_security_listing_population",
            "holding_overlap_population",
        )
    )
    assert not a["new_acquisition"] and not a["funding_ready"]
    assert sum(len(g["references"]) for g in a["review"]["groups"]) == 3857
    with pytest.raises(AuditError, match="fresh"):
        regenerate(RULE, SCOPE, CAPTURES, tmp_path / "a")


@pytest.mark.parametrize("target", ["rule", "receipt", "raw", "scope"])
def test_unknown_formats_or_changed_pinned_inputs_reject(tmp_path: Path, target: str) -> None:
    import shutil

    captures = tmp_path / "captures"
    shutil.copytree(CAPTURES, captures)
    rule = tmp_path / "rule.json"
    rule.write_bytes(RULE.read_bytes())
    scope = tmp_path / "scope.json"
    scope.write_bytes(SCOPE.read_bytes())
    if target == "rule":
        rule.write_bytes(rule.read_bytes().replace(b"2.0.0", b"9.0.0"))
    elif target == "receipt":
        p = captures / "manifest.json"
        p.write_bytes(p.read_bytes().replace(b"1.0.0", b"9.0.0"))
    elif target == "raw":
        next((captures / "objects").iterdir()).write_bytes(b"invented tampering")
    else:
        scope.write_bytes(scope.read_bytes() + b" ")
    with pytest.raises(AuditError):
        regenerate(rule, scope, captures, tmp_path / "output")
