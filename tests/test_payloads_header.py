"""The SEC header parser (D78), on the two headers Austin recorded for Lotus Technology and on
pages built from them. Only the tagged block inside the page's one HTML comment is read, and in it
only each party's CIK and SIC inside its COMPANY-DATA; the escaped copy in the body never is. The
expected values are written by hand from the recorded bytes, never from the code."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from listinglens.core.errors import FilingNotFound, MalformedPayload
from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.filing import FilingHeader, HeaderParty
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion.endpoints import filing_document_url, filing_index_url
from listinglens.ingestion.payloads.header import header_document_name, parse_filing_header
from tests.conftest import EDGAR_FIXTURES_DIR, RepositoryFactory, Route, ServiceFactory

LOTUS, LCAA = Cik.parse(1962746), Cik.parse(1841024)
A425 = AccessionNumber.parse("0001104659-23-008580")  # Lotus's first 425
AF4 = AccessionNumber.parse("0001104659-23-109358")  # its F-4
COMPANY = ResolvedCompany(cik=LOTUS, issuer_name="lotus", ref=CompanyRef(cik=LOTUS))
HEADER_425 = (EDGAR_FIXTURES_DIR / "header_lotus_425.html").read_text(encoding="ascii")
URL = filing_document_url(LOTUS, A425, header_document_name(A425))
# The 425's header as its tagged block states it: L Catterton (SIC 6770) the subject, Lotus filer.
EXPECTED_425 = FilingHeader(
    accession_no=A425, filers=(LOTUS,), subjects=(HeaderParty(cik=LCAA, sic="6770"),)
)
BLOCK = HEADER_425[HEADER_425.index("<SEC-HEADER>") : HEADER_425.index("</SEC-HEADER>") + 14]


def _routes() -> dict[str, Route]:
    routes: dict[str, Route] = {}
    for accession, stem in ((A425, "lotus_425"), (AF4, "lotus_f4")):
        index = (EDGAR_FIXTURES_DIR / f"archives_index_{stem}.json").read_bytes()
        routes[filing_index_url(LOTUS, accession)] = index
        page = (EDGAR_FIXTURES_DIR / f"header_{stem}.html").read_bytes()
        routes[filing_document_url(LOTUS, accession, header_document_name(accession))] = page
    return routes


def _parse(text: str) -> FilingHeader:
    return parse_filing_header(text.encode("latin-1"), URL, A425)


def test_the_recorded_425_header_names_lotus_as_filer_and_l_catterton_as_subject(
    repository_factory: RepositoryFactory,
) -> None:
    repository, routed = repository_factory(_routes())
    assert repository.filing_header(COMPANY, A425) == EXPECTED_425
    assert routed.requested == [filing_index_url(LOTUS, A425), URL]


def test_the_service_reads_the_header_as_the_repository_does(
    service_factory: ServiceFactory,
) -> None:
    service, _ = service_factory(_routes())
    assert service.filing_header(COMPANY, A425) == EXPECTED_425


def test_what_the_recorded_f4_header_names(repository_factory: RepositoryFactory) -> None:
    # One FILER (Lotus, whose own SIC 3711 is never read) and no SUBJECT-COMPANY: the F-4 alone
    # names no merger partner, and that is no error.
    repository, _ = repository_factory(_routes())
    assert repository.filing_header(COMPANY, AF4) == FilingHeader(
        accession_no=AF4, filers=(LOTUS,), subjects=()
    )


def _end(text: str) -> int:
    return text.index("-->") + len("-->")


@pytest.mark.parametrize(
    "page",
    [
        HEADER_425.replace(BLOCK, BLOCK + "\n" + BLOCK, 1),
        HEADER_425[: _end(HEADER_425)]
        + "\n<!--\n"
        + BLOCK
        + "\n-->"
        + HEADER_425[_end(HEADER_425) :],
    ],
    ids=["two_in_the_comment", "two_comments"],
)
def test_a_page_with_two_header_blocks_is_refused(page: str) -> None:
    with pytest.raises(MalformedPayload) as caught:
        _parse(page)
    assert caught.value.field == "sec_header"


WITHOUT_COMMENT = HEADER_425[: HEADER_425.index("<!--")] + HEADER_425[_end(HEADER_425) :]


@pytest.mark.parametrize(
    "page",
    [WITHOUT_COMMENT, WITHOUT_COMMENT.replace("<PRE>", "<PRE>" + BLOCK + "\n", 1)],
    ids=["escaped_copy_only", "raw_block_in_the_body"],
)
def test_a_page_with_the_block_only_in_the_body_is_refused(page: str) -> None:
    assert "&lt;SEC-HEADER&gt;" in page  # the escaped copy is there, and is never read
    with pytest.raises(MalformedPayload) as caught:
        _parse(page)
    assert caught.value.detail == "0 comments hold a SEC-HEADER block, not one"


def test_a_cik_outside_company_data_is_never_read() -> None:
    stray = "<CIK>0009999999\n"
    page = HEADER_425.replace("<TYPE>425\n", "<TYPE>425\n" + stray, 1)  # in the block itself
    page = page.replace("<SUBJECT-COMPANY>\n", "<SUBJECT-COMPANY>\n" + stray, 1)
    page = page.replace("<ACT>34\n", "<ACT>34\n" + stray, 1)  # in FILING-VALUES
    page = page.replace(
        "</COMPANY-DATA>\n<FILING-VALUES>\n<FORM-TYPE>425\n</FILING-VALUES>",
        ("</COMPANY-DATA>\n" + stray + "<FILING-VALUES>\n<FORM-TYPE>425\n</FILING-VALUES>"),
    )  # in FILED-BY
    assert page.count(stray) == 4
    header = _parse(page)
    assert header == EXPECTED_425
    assert "9999999" not in header.model_dump_json()


def _swap(old: str, new: str) -> str:
    assert HEADER_425.count(old) >= 1, old
    return HEADER_425.replace(old, new, 1)


def _filer_without_company_data() -> str:
    start = HEADER_425.index("<FILED-BY>")
    tail = HEADER_425[start:].replace("<COMPANY-DATA>\n", "", 1)
    return HEADER_425[:start] + tail.replace("</COMPANY-DATA>\n", "", 1)


@pytest.mark.parametrize(
    "page",
    [
        _swap("</COMPANY-DATA>\n", ""),
        _swap("</SUBJECT-COMPANY>\n", ""),
        _filer_without_company_data(),
        _swap("<CIK>0001841024", "<CIK>00018410AB"),
        _swap("<CIK>0001841024", "<CIK>001841024"),
        _swap("<CIK>0001841024", "<CIK>0000000000"),
        _swap("<CIK>0001841024\n", "<CIK>0001841024\n<CIK>0001841025\n"),
        _swap("<ASSIGNED-SIC>6770", "<ASSIGNED-SIC>677"),
        _swap("<ACCESSION-NUMBER>0001104659-23-008580", "<ACCESSION-NUMBER>0001104659-23-008581"),
        _swap("<FILED-BY>", "<FILED-FOR>").replace("</FILED-BY>", "</FILED-FOR>"),
        _swap("<TYPE>425\n", "<TYPE>425\nnot a tag\n"),
        HEADER_425[: _end(HEADER_425)]
        + "\n<!--\n</SEC-HEADER>\n-->"
        + HEADER_425[_end(HEADER_425) :],
        _swap("<ASSIGNED-SIC>6770\n", "<ASSIGNED-SIC>6770\n<ASSIGNED-SIC>6770\n"),
        _swap("<COMPANY-DATA>\n", "<COMPANY-DATA>x\n"),
        _swap("</COMPANY-DATA>\n", "</COMPANY-DATA>x\n"),
        _swap(
            "<ACCESSION-NUMBER>0001104659-23-008580\n",
            "<ACCESSION-NUMBER>0001104659-23-008580\n<ACCESSION-NUMBER>0001104659-23-008580\n",
        ),
    ],
    ids=[
        "unbalanced",
        "unclosed_subject",
        "filer_without_company_data",
        "cik_not_digits",
        "cik_nine_digits",
        "cik_zero",
        "two_ciks",
        "sic_three_digits",
        "another_accession",
        "no_filer",
        "a_line_not_a_tag",
        "a_second_comment_with_only_a_close",
        "two_sics",
        "an_opener_with_a_value",
        "a_closer_with_a_value",
        "the_accession_twice",
    ],
)
def test_a_malformed_header_is_refused(page: str) -> None:
    with pytest.raises(MalformedPayload) as caught:
        _parse(page)
    assert caught.value.field == "sec_header" and caught.value.url == URL


RAW_425 = (EDGAR_FIXTURES_DIR / "header_lotus_425.html").read_bytes()
SUBJECT_NAME = b"<CONFORMED-NAME>L Catterton Asia Acquisition Corp\n"


# An accented letter in the subject's name: the byte 0xE9 alone, and its two UTF-8 bytes.
@pytest.mark.parametrize("letter", [b"\xe9", b"\xc3\xa9"], ids=["byte_e9", "utf_8_letter"])
def test_a_name_in_another_encoding_never_stops_the_tags_being_read(letter: bytes) -> None:
    page = RAW_425.replace(SUBJECT_NAME, SUBJECT_NAME.replace(b"Corp", b"Corp " + letter), 1)
    assert RAW_425.count(SUBJECT_NAME) == 1 and letter in page and max(page) > 127
    assert parse_filing_header(page, URL, A425) == EXPECTED_425


def test_no_name_is_ever_held(repository_factory: RepositoryFactory) -> None:
    repository, _ = repository_factory(_routes())
    for accession in (A425, AF4):
        held = repository.filing_header(COMPANY, accession).model_dump_json().lower()
        for name in ("lotus", "catterton", "singapore", "shanghai", "marina", "century"):
            assert name not in held
    # The parser holds no tag for a name, an address or a form type, so it cannot read one.
    parser = Path(__file__).resolve().parents[1] / "src/listinglens/ingestion/payloads/header.py"
    source = parser.read_text(encoding="utf-8")
    constants = {n.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Constant)}
    assert not {"CONFORMED-NAME", "TYPE", "FORM-TYPE", "STREET1", "CITY"} & constants


def _index(names: tuple[str, ...]) -> bytes:
    items = ",".join(
        f'{{"last-modified":"2023-01-31 17:21:38","name":"{n}","type":"text.gif","size":""}}'
        for n in names
    )
    folder = f"/Archives/edgar/data/1962746/{A425.bare}"
    tail = '"parent-dir":"/Archives/edgar/data/1962746"'
    return f'{{"directory":{{"item":[{items}],"name":"{folder}",{tail}}}}}'.encode()


@pytest.mark.parametrize(
    ("listed", "refused"),
    [((), FilingNotFound), ((header_document_name(A425),) * 2, MalformedPayload)],
    ids=["none", "two"],
)
def test_an_index_without_exactly_one_header_is_refused_before_any_header_is_asked_for(
    repository_factory: RepositoryFactory, listed: tuple[str, ...], refused: type[Exception]
) -> None:
    repository, routed = repository_factory(
        {**_routes(), filing_index_url(LOTUS, A425): _index(listed)}
    )
    with pytest.raises(refused):
        repository.filing_header(COMPANY, A425)
    assert routed.requested == [filing_index_url(LOTUS, A425)]


def test_a_missing_header_page_is_a_missing_document(repository_factory: RepositoryFactory) -> None:
    routes = {url: body for url, body in _routes().items() if url != URL}
    repository, _ = repository_factory(routes)
    with pytest.raises(FilingNotFound) as caught:
        repository.filing_header(COMPANY, A425)
    assert (caught.value.identifier, caught.value.identifier_kind) == (
        header_document_name(A425),
        "document",
    )
