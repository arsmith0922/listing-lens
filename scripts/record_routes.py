"""The four route examples (D77) that scripts/record_fixtures.py records with its routes selector:
each company's submissions record and every overflow page the record lists, as the exact bytes
the SEC sent and never trimmed, because the hand oracles read every row. Each CIK is confirmed
from the SEC's own records before anything is written: the record's name, or one of its former
names, holds the expected words (case ignored), and where the company still trades, the SEC's
ticker file maps its ticker to that same CIK. A company that is not confirmed is reported with what
the SEC has, and nothing at all is written. It lives here, like record_pairs.py, so the recorder
stays under the line cap; record_fixtures.py imports it by bare name and hands it its writer."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import (
    company_tickers_url,
    submissions_overflow_url,
    submissions_url,
)
from listinglens.ingestion.transport import EdgarTransport


class RouteExample(NamedTuple):
    stem: str
    cik: str
    words: str  # held, case ignored, by the SEC's name for the company or one of its former names
    ticker: str | None  # a ticker the SEC's ticker file must map to the same CIK, or None


# The CIKs are the architect's starting point; the run confirms each from the SEC's own records.
ROUTE_EXAMPLES = (
    RouteExample("lcaa", "0001841024", "L CATTERTON ASIA ACQUISITION", None),  # a SPAC
    RouteExample("lotus", "0001962746", "LOTUS TECH", "LOT"),  # the de-SPAC with it
    RouteExample("puda", "0001162747", "PUDA COAL", None),  # a 2005 China reverse merger
    RouteExample("coinbase", "0001679788", "COINBASE GLOBAL", "COIN"),  # a direct listing
)

WriteRaw = Callable[[str, bytes, str], None]  # filename, exact bytes, url


class _Named(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str


class _Files(BaseModel):
    model_config = ConfigDict(extra="ignore")

    files: list[_Named]


class _Record(BaseModel):
    """The few parts of a submissions record the confirmation reads; the bytes are kept as sent."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    cik: str
    name: str
    former_names: list[_Named] = Field(alias="formerNames")
    filings: _Files


class _Ticker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cik_str: int
    ticker: str


_TICKERS = TypeAdapter(dict[str, _Ticker])


def _problem(example: RouteExample, record: _Record, tickers: dict[str, int]) -> str | None:
    """Why the SEC's records do not confirm this company's CIK, or None when they do."""
    held = Cik.parse(record.cik).padded
    names = [record.name, *(former.name for former in record.former_names)]
    if held != example.cik or not any(example.words.casefold() in n.casefold() for n in names):
        return f"the SEC has CIK {held} as {record.name!a}"
    found = None if example.ticker is None else tickers.get(example.ticker)
    if example.ticker is not None and found != Cik.parse(example.cik).value:
        mapped = "is not in company_tickers.json" if found is None else f"maps to CIK {found:010d}"
        return f"{example.ticker} {mapped}"
    return None


def _confirmed(example: RouteExample, record: _Record) -> str:
    line = f"confirmed {example.stem}: CIK {example.cik} is {record.name!a}"
    if example.ticker is not None:
        line += f", and {example.ticker} maps to it in company_tickers.json"
    return line


def record_route_examples(transport: EdgarTransport, write_raw: WriteRaw) -> tuple[int, int]:
    """Fetch the ticker file, then each record and every page it lists; confirm each company; and
    only when every fetch and every check has passed, write each file as the exact bytes the SEC
    sent. Returns how many files were written and their bytes in all (the manifest aside)."""
    url = company_tickers_url()
    listed = _TICKERS.validate_json(transport.get(url).raise_for_status().content)
    tickers = {entry.ticker: entry.cik_str for entry in listed.values()}
    fetched: list[tuple[str, str, bytes]] = []  # filename, url, exact bytes
    problems: list[str] = []
    lines: list[str] = []
    for example in ROUTE_EXAMPLES:
        cik = Cik.parse(example.cik)
        url = submissions_url(cik)
        body = transport.get(url).raise_for_status().content
        record = _Record.model_validate_json(body)
        problem = _problem(example, record, tickers)
        if problem is not None:
            problems.append(f"not confirmed: {example.stem}: {problem}")
            continue
        lines.append(_confirmed(example, record))
        fetched.append((f"submissions_{example.stem}.json", url, body))
        for page in record.filings.files:
            page_url = submissions_overflow_url(cik, page.name)
            fetched.append(
                (page.name, page_url, transport.get(page_url).raise_for_status().content)
            )
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        raise SystemExit(1)
    for line in lines:
        print(line)
    for filename, file_url, content in fetched:
        write_raw(filename, content, file_url)
    return len(fetched), sum(len(content) for _, _, content in fetched)
