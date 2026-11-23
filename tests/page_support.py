"""Support for the page's tests (D73): the nine pages of run 2's records, pages for the cases no
draft covers (one-claim narratives written here for sets with no tier assessed), a synthetic
provenance and stamp, a canary memo with markup in every text slot, and an html.parser walk that
collects every tag, attribute and text of a page. Nothing here calls a model."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from functools import cache
from html.parser import HTMLParser

from listinglens.memo.build import Built, build_fact_set
from listinglens.memo.context import DirectoryContext, RunContext
from listinglens.memo.narrative import Claim, Narrative, Section
from listinglens.memo.render_fill import render_memo
from listinglens.memo.render_model import Provenance, RenderedMemo, Text, Value
from listinglens.memo.render_page import page_html
from listinglens.memo.render_page_head import PageHeader, RecordStamp, page_header
from listinglens.workflow import memo_page
from tests.memo_results import assemble, results_for, texts
from tests.record_support import NINE, record_of

CANARY = "<script>alert(\"x\")</script> & 'q' </p>"
PROVENANCE = Provenance(
    model="claude-sonnet-5-5", effort="medium", prompt_sha256="ab" * 32, cost="0.04550750",
    attempts=1, tokens=12_141, price_table_version=1,
)  # fmt: skip
STAMP = RecordStamp(
    format="memo-record-v1",
    created_at=datetime(2026, 11, 22, 7, 5, 9, tzinfo=UTC),
    fact_set_digest="cd" * 32,
)


@cache
def page_of(name: str) -> str:
    return memo_page(record_of(name))


def pages() -> dict[str, str]:
    return {name: page_of(name) for name in NINE}


def one_claim(built: Built) -> Narrative:
    """A narrative of one filings claim, for a set whose view has no primary fact."""
    filing = next(f.id for f in built.facts.facts if f.kind == "filing")
    claim = Claim(
        kind="fact", text=f"The company filed a {{{filing}:form_type}}.", refs=(filing,), basis=()
    )
    empty = Section(claims=())
    return Narrative(
        reported_financials=empty, findings=empty, standards=empty, not_measured=empty,
        exchange_status=empty, filings=Section(claims=(claim,)), verdict=empty,
    )  # fmt: skip


@cache
def no_tier_page(label: str, check: str) -> str:
    built = build_fact_set(results_for(label, check))
    memo = render_memo(one_claim(built), built.facts)
    return page_html(memo, PROVENANCE, page_header(built.context, built.facts), STAMP)


def canary_built() -> Built:
    """agmh's results with markup in the company's name and in the directory row's symbol and
    security name, built into facts by the real builders."""
    recorded = {
        key: text.replace('"AGM GROUP HOLDINGS, INC."', json.dumps(CANARY))
        for key, text in texts()["agmh"].items()
    }
    check = json.loads(recorded["check_dir"])
    citation = check["nasdaq_status"][0]["citation"]
    citation["symbol"], citation["security_name"] = "<i>AGMH</i>", "SECNAME " + CANARY
    recorded["check_dir"] = json.dumps(check)
    return build_fact_set(assemble(recorded, "check_dir"))


def canary_memo(memo: RenderedMemo) -> RenderedMemo:
    """A rendered memo with the canary in a text segment, a value, an amount and a label."""
    section = memo.sections[0]
    claim = section.claims[0]
    planted = claim.model_copy(
        update={
            "segments": (
                Text(text=CANARY),
                Value(text=CANARY, key="company.text"),
                Value(text=CANARY, key="figure.amount"),
            )
        }
    )
    first = section.model_copy(update={"claims": (planted, *section.claims[1:])})
    source = memo.sources[0].model_copy(update={"label": CANARY})
    return memo.model_copy(
        update={"sections": (first, *memo.sections[1:]), "sources": (source, *memo.sources[1:])}
    )


def header_with(**changes: object) -> PageHeader:
    base = PageHeader(
        company_name="X CORP", tickers=("XA",), listing_type="continued",
        pathway="traditional_ipo", tier_how="named", requested_tier="capital",
        tiers=("capital",), tiers_without_rules=(), evaluated_on=date(2026, 10, 31),
        directory_available=True,
    )  # fmt: skip
    return base.model_copy(update=changes)


def context_with(base: RunContext, **changes: object) -> RunContext:
    return base.model_copy(update=changes)


def unread_directory() -> DirectoryContext:
    return DirectoryContext(available=False, stamp=None, sha256=None)


class Walk(HTMLParser):
    """Every start tag with its attributes, every end tag, and every piece of text, in order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.starts: list[tuple[str, dict[str, str | None]]] = []
        self.ends: list[str] = []
        self.texts: list[tuple[str, str]] = []
        self.declarations: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.starts.append((tag, dict(attrs)))
        if tag not in ("meta",):
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.starts.append((tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        self.ends.append(tag)
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        self.texts.append((self.stack[-1] if self.stack else "", data))

    def handle_decl(self, decl: str) -> None:
        self.declarations.append(decl)


def walk(page: str) -> Walk:
    parser = Walk()
    parser.feed(page)
    parser.close()
    return parser
