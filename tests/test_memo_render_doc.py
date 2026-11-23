"""The rendered document and its plain-text projection (D71): the structure the architect approved
(the scope note, the disclosure, the sections that have claims with the exchange note under Exchange
status, the reading label, the marks, the numbered sources with indented links), checked on a small
hand-made document, and the nine drafts of run 2 pinned by digest."""

from __future__ import annotations

import hashlib

from listinglens.memo.render_fill import render_memo
from listinglens.memo.render_model import (
    HEADINGS,
    READING_LABEL,
    RenderedClaim,
    RenderedMemo,
    RenderedSection,
    SourceEntry,
    Statement,
    Term,
    Text,
    Value,
)
from listinglens.memo.render_text import to_text
from tests.memo_render_goldens import GOLDENS
from tests.render_support import run2

SCOPE = "Scope note."
AI = "AI disclosure."
EXCHANGE = "Exchange note."


def claim(kind: str, marks: str, *segments: Text | Value | Term) -> RenderedClaim:
    numbers = tuple(int(n) for n in marks.replace("-", ",").split(",") if n.isdigit())
    return RenderedClaim.model_validate(
        {"kind": kind, "segments": segments, "sources": numbers, "marks": marks}
    )


def small_memo() -> RenderedMemo:
    names = list(HEADINGS)
    by_name = {
        "findings": (
            claim("fact", "1-2", Text(text="State: "), Term(text="clear", member="clear", key="k")),
            claim("inference", "3,7-9", Text(text="It is "), Value(text="2,500,000", key="k")),
        ),
        "exchange_status": (claim("fact", "4", Text(text="The flag is deficient.")),),
    }
    return RenderedMemo(
        scope_note=Statement(id="scope_note_v1", text=SCOPE),
        ai_disclosure=Statement(id="ai_disclosure_v1", text=AI),
        exchange_note=Statement(id="exchange_note_v1", text=EXCHANGE),
        sections=tuple(
            RenderedSection(name=n, heading=HEADINGS[n], claims=by_name.get(n, ())) for n in names
        ),
        sources=(
            SourceEntry(
                number=1,
                kind="rule",
                label="A rule.",
                links=("https://a.example/1", "https://a.example/2"),
                release="SR-X-1",
            ),
            SourceEntry(
                number=2,
                kind="directory",
                label="A row.",
                links=("https://b.example/x",),
                release=None,
            ),
        ),
    )


def test_the_projection_has_the_approved_structure_to_the_character() -> None:
    assert to_text(small_memo()) == (
        "Scope note.\n\n"
        "AI disclosure.\n\n"
        "Findings\n"
        "State: clear [1-2]\n"
        "Reading: It is 2,500,000 [3,7-9]\n\n"
        "Exchange status\n"
        "Exchange note.\n\n"
        "The flag is deficient. [4]\n\n"
        "Sources\n"
        "1. A rule. Approved in SR-X-1.\n"
        "    https://a.example/1\n"
        "    https://a.example/2\n"
        "2. A row.\n"
        "    https://b.example/x\n"
    )


def test_the_headings_and_the_reading_label_are_pinned_against_an_independent_copy() -> None:
    assert HEADINGS == {
        "reported_financials": "Reported financials",
        "findings": "Findings",
        "standards": "Standards",
        "not_measured": "Not measured",
        "exchange_status": "Exchange status",
        "filings": "Filings",
        "verdict": "Verdict",
    }
    assert list(HEADINGS) == [
        "reported_financials", "findings", "standards", "not_measured", "exchange_status",
        "filings", "verdict",
    ]  # fmt: skip
    assert READING_LABEL == "Reading: "


def test_a_section_without_claims_leaves_no_heading_and_no_note() -> None:
    text = to_text(small_memo())
    for heading in ("Reported financials", "Standards", "Not measured", "Filings", "Verdict"):
        assert f"\n{heading}\n" not in text
    memo = small_memo().model_copy(update={"sections": small_memo().sections[:4]})
    assert "Exchange note." not in to_text(memo)


def test_the_projection_of_a_real_memo_opens_with_the_two_statements_and_ends_with_sources() -> (
    None
):
    narrative, fact_set = run2()["agmh.one"]
    memo = render_memo(narrative, fact_set)
    text = to_text(memo)
    assert text.startswith(f"{memo.scope_note.text}\n\n{memo.ai_disclosure.text}\n\n")
    assert text.endswith("\n") and not text.endswith("\n\n") and "\r" not in text
    lines = text.split("\n")
    assert lines.count("Sources") == 1 and lines[lines.index("Sources") - 1] == ""
    tail = lines[lines.index("Sources") + 1 : -1]
    numbered = [line for line in tail if not line.startswith("    ")]
    assert [line.partition(". ")[0] for line in numbered] == [str(n) for n in range(1, 40)]
    assert all(line.startswith("    https://") for line in tail if line.startswith("    "))
    assert text.count("\nExchange status\n" + memo.exchange_note.text + "\n\n") == 1


def test_terms_are_plain_words_and_an_inference_begins_with_the_reading_label() -> None:
    narrative, fact_set = run2()["agmh.one"]
    text = to_text(render_memo(narrative, fact_set))
    assert "cannot determine" in text and "cannot_determine" not in text
    readings = [line for line in text.split("\n") if line.startswith("Reading: ")]
    assert len(readings) == sum(c.kind == "inference" for _, _, c in narrative.claims())
    assert all(line.endswith("]") for line in readings)


def test_the_nine_projections_are_pinned_by_digest_and_are_ascii_with_lf_endings() -> None:
    assert [g[0] for g in GOLDENS] == list(run2())
    for name, digest, lines, characters in GOLDENS:
        narrative, fact_set = run2()[name]
        text = to_text(render_memo(narrative, fact_set))
        assert hashlib.sha256(text.encode("ascii")).hexdigest() == digest, name
        assert (len(text.splitlines()), len(text)) == (lines, characters), name
        assert text.isascii() and "\r" not in text
