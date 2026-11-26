from __future__ import annotations

import re
from typing import Final

from listinglens.core.errors import InputValidationError, MalformedPayload
from listinglens.domain.filing import FilingHeader, HeaderParty
from listinglens.domain.identifiers import AccessionNumber, Cik

# A filing's SEC header (D78), read from its page {accession}-index-headers.html by literal
# markers, never by an HTML parser. The page carries the header twice: as tagged SGML inside the
# one HTML comment in its head, and as an escaped, readable copy in its body, which is never
# read. In the tagged copy only the accession number is read and, inside each party's
# COMPANY-DATA (a filer's or a subject company's, D79), its CIK and its ASSIGNED-SIC: never a
# name, an address, a former company or a form type, and never a CIK or SIC anywhere else.
_COMMENT: Final = re.compile(r"<!--(.*?)-->", re.DOTALL)
_OPEN: Final = "<SEC-HEADER>"
_CLOSE: Final = "</SEC-HEADER>"
_LINE: Final = re.compile(r"<(/?)([A-Z0-9-]+)>(.*)")
_CIK: Final = re.compile(r"[0-9]{10}")
_SIC: Final = re.compile(r"[0-9]{4}")
SUBJECT: Final = "SUBJECT-COMPANY"
FILERS: Final = frozenset({"FILED-BY", "FILER"})
COMPANY_DATA: Final = "COMPANY-DATA"
_ALWAYS_SECTIONS: Final = FILERS | {SUBJECT, COMPANY_DATA}


def header_document_name(accession: AccessionNumber) -> str:
    return f"{accession.dashed}-index-headers.html"


def _malformed(url: str, detail: str) -> MalformedPayload:
    return MalformedPayload(url=url, field="sec_header", detail=detail)


class _Section:
    """One tagged section: its value lines and the sections inside it, in the header's order."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.values: list[tuple[str, str]] = []
        self.sections: list[_Section] = []

    def only(self, tag: str) -> list[str]:
        return [value for name, value in self.values if name == tag]


def _block(text: str, url: str) -> list[str]:
    """The lines between the SEC-HEADER markers of the one comment that holds them."""
    blocks: list[list[str]] = []
    for comment in _COMMENT.finditer(text):
        lines = comment.group(1).splitlines()
        opens = [i for i, line in enumerate(lines) if line.startswith(_OPEN)]
        closes = [i for i, line in enumerate(lines) if line == _CLOSE]
        if not opens and not closes:
            continue
        if len(opens) != 1 or len(closes) != 1 or closes[0] < opens[0]:
            raise _malformed(url, "a comment must hold exactly one SEC-HEADER block")
        blocks.append(lines[opens[0] + 1 : closes[0]])
    if len(blocks) != 1:
        raise _malformed(url, f"{len(blocks)} comments hold a SEC-HEADER block, not one")
    return blocks[0]


def _tree(lines: list[str], url: str) -> _Section:
    """The block as sections: a party, its COMPANY-DATA and any tag the block closes somewhere.
    A party or COMPANY-DATA left unclosed is refused, never read as a value line."""
    parsed: list[tuple[bool, str, str]] = []
    for line in lines:
        match = _LINE.fullmatch(line)
        if match is None:
            raise _malformed(url, "a header line that is not a tag")
        parsed.append((match.group(1) == "/", match.group(2), match.group(3)))
    sections = {tag for closing, tag, _ in parsed if closing} | _ALWAYS_SECTIONS
    stack = [_Section(_OPEN)]
    for closing, tag, value in parsed:
        if closing:
            if value or len(stack) == 1 or stack[-1].tag != tag:
                raise _malformed(url, f"an unbalanced </{tag}>")
            stack.pop()
        elif tag in sections and not value.strip():
            stack[-1].sections.append(_Section(tag))
            stack.append(stack[-1].sections[-1])
        else:
            stack[-1].values.append((tag, value))
    if len(stack) != 1:
        raise _malformed(url, f"an unclosed <{stack[-1].tag}>")
    return stack[0]


def _party(section: _Section, url: str) -> HeaderParty:
    data = [inner for inner in section.sections if inner.tag == COMPANY_DATA]
    if len(data) != 1:
        raise _malformed(url, f"{section.tag} must hold one {COMPANY_DATA}")
    ciks = data[0].only("CIK")
    sics = data[0].only("ASSIGNED-SIC")
    if len(ciks) != 1 or not _CIK.fullmatch(ciks[0]):
        raise _malformed(url, f"{section.tag} must hold one ten-digit CIK")
    if len(sics) > 1:
        raise _malformed(url, f"{section.tag} holds more than one ASSIGNED-SIC")
    if not all(_SIC.fullmatch(sic) for sic in sics):
        raise _malformed(url, f"{section.tag} has an ASSIGNED-SIC that is not one of four digits")
    try:
        cik = Cik.parse(ciks[0])
    except InputValidationError as exc:
        raise _malformed(url, str(exc)) from exc
    return HeaderParty(cik=cik, sic=sics[0] if sics else None)


def parse_filing_header(body: bytes, url: str, accession: AccessionNumber) -> FilingHeader:
    """The header of the filing, refused (MalformedPayload) unless exactly one comment holds
    exactly one balanced SEC-HEADER block, naming this accession and at least one filer."""
    # latin-1 maps every byte, so a name in another encoding never stops the tags being read.
    root = _tree(_block(body.decode("latin-1"), url), url)
    if root.only("ACCESSION-NUMBER") != [accession.dashed]:
        raise _malformed(url, f"the header does not name {accession.dashed} alone")
    filers = tuple(_party(s, url) for s in root.sections if s.tag in FILERS)
    if not filers:
        raise _malformed(url, "the header names no filer")
    subjects = tuple(_party(s, url) for s in root.sections if s.tag == SUBJECT)
    return FilingHeader(accession_no=accession, filers=filers, subjects=subjects)
