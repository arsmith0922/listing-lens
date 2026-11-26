"""classify_pathway's whole result for Coinbase on the tool day, 2026-10-31 (D80), written by hand
from the fixture JSON (page CIK0001679788-submissions-001.json, the rows named beside each filing),
never from the code: a direct listing, so candidates traditional_ipo or direct_listing, at stage
listed, needing neither lookup. Its recent rows (2022-05-10 to 2026-11-24) hold no filing the
route reads."""

from __future__ import annotations

CIK = "0001679788"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/1679788/"


def filing(accession: str, form: str, filed: str) -> dict[str, object]:
    return {
        "kind": "sec_record", "cik": CIK, "record": "submissions", "field": "filing",
        "accession_no": accession, "form_type": form, "filed_date": filed,
        "index_url": ARCHIVES + accession.replace("-", "") + "/",
    }  # fmt: skip


S1 = filing("0001628280-21-003168", "S-1", "2021-02-25")  # row 191, 333-253482
A2 = filing("0001628280-21-005373", "S-1/A", "2021-03-23")  # row 186, the later of two
L8A = filing("0001628280-21-005378", "8-A12B", "2021-03-23")  # row 184, 001-40289
CERT = filing("0001354457-21-000402", "CERT", "2021-03-24")  # row 182, 001-40289
EFFECT = filing("9999999995-21-001252", "EFFECT", "2021-04-01")  # row 163
B4 = filing("0001628280-21-006850", "424B4", "2021-04-14")  # row 148
OFFERING = ["registration_statement", "final_prospectus"]
NOT_NEEDED = {"status": "not_needed", "filing": None, "error": None}
COINBASE = {
    "company": {
        "cik": CIK,
        "issuer_name": "Coinbase Global, Inc.",
        "resolved_from": {"kind": "cik", "value": CIK},
    },
    "evaluated_on": "2026-10-31",
    "scope_note": "Routes and stages are read from the SEC's submissions records (form types, "
    "dates, file numbers and 8-K items, and the company's SIC and former names) and, where "
    "needed, one SEC filing header (CIKs and SIC codes only), and are not verified by "
    "ListingLens. This output is a risk signal, not investment advice and not a recommendation "
    "to buy or sell any security.",
    "cutoff": "2026-10-31",
    "outcome": "candidates",
    "route": None,
    "candidates": {
        "routes": ["traditional_ipo", "direct_listing"],
        "why": "offering_forms_alike",
        "because": "A traditional IPO and a direct listing file the same forms (a registration "
        "statement and its amendments, the exchange registration and its certification, the "
        "notice of effectiveness and a final prospectus), so form types cannot tell them apart.",
        "evidence": [S1, L8A, CERT, EFFECT, B4],
        "settle_by": [
            {
                "route": "direct_listing",
                "phrase": "direct listing",
                "roles": OFFERING,
                "status": "provisional",
            },
            {
                "route": "traditional_ipo",
                "phrase": "underwriting discounts and commissions",
                "roles": OFFERING,
                "status": "provisional",
            },
        ],
        "documents": [
            {
                "role": "registration_statement",
                "filing": A2,
                "primary_document": "coinbaseglobalincs-1a2.htm",
            },
            {
                "role": "final_prospectus",
                "filing": B4,
                "primary_document": "coinbaseglobalinc424b.htm",
            },
        ],
    },
    "looked_for": [],
    "stage": "listed",
    "stages": [
        {"stage": "in_registration", "on": "2021-02-25", "filings": [S1]},
        {"stage": "effective", "on": "2021-04-01", "filings": [EFFECT]},
        {"stage": "final_prospectus", "on": "2021-04-14", "filings": [B4]},
        {"stage": "listed", "on": "2021-04-01", "filings": [L8A, CERT, EFFECT]},
    ],
    "registration": {
        "file_number": "333-253482",
        "began": S1,
        "drafts": 3,  # DRS row 199 and DRS/A rows 196 and 193, on 377-03643
        "first_draft": "2020-10-09",
        "amendments": 2,  # S-1/A rows 189 and 186
        "post_effective_amendments": 1,  # POS AM row 95, 2021-07-01
    },
    "listing": {"registered": L8A, "certified": CERT, "effective_on": "2021-04-01"},
    "events": [
        {"kind": "registration_filed", "filing": S1},
        {"kind": "listing_registered", "filing": L8A},
        {"kind": "exchange_certified", "filing": CERT},
        {"kind": "effective", "filing": EFFECT},
        {"kind": "final_prospectus", "filing": B4},
    ],
    "counterparty": None,
    "spac_evidence": None,
    "shell": None,
    "ipo_header_lookup": NOT_NEEDED,
    "counterparty_lookup": {
        "status": "not_needed",
        "filing": None,
        "named_cik": None,
        "error": None,
    },
}
