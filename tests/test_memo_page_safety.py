"""The page's safety (D73): every tag and attribute is held to an allow-list that fails closed,
every link is a fragment of the page or a link D71 checked, the Content-Security-Policy refuses
everything but the page's one style and its hash is recomputed here independently, and markup
planted in the company's name, a ticker, a directory row, a text, a value, a label and the model id
shows only as inert text. A form type with markup never becomes a fact."""

from __future__ import annotations

import base64
import hashlib
import json

import pytest

from listinglens.core.errors import IdentityRefused, LinkRefused, RenderRefused
from listinglens.memo.build import build_fact_set
from listinglens.memo.render_fill import render_memo
from listinglens.memo.render_model import RenderedMemo, Term
from listinglens.memo.render_page import page_html
from listinglens.memo.render_page_head import page_header
from listinglens.memo.render_sources import ALLOWED_HOSTS
from tests.memo_results import assemble, texts
from tests.page_support import (
    CANARY,
    PROVENANCE,
    STAMP,
    Walk,
    canary_built,
    canary_memo,
    header_with,
    no_tier_page,
    pages,
    walk,
)
from tests.record_support import record_of

TAGS = {
    "html", "head", "meta", "title", "style", "body", "header", "p", "h1", "h2", "div",
    "section", "span", "sup", "a", "dl", "dt", "dd", "ol", "li", "footer",
}  # fmt: skip
CLASSES: dict[str, set[str | None]] = {
    "p": {None, "kicker", "dek", "note", "reading"},
    "div": {"about"},
    "section": {None, "terms", "sources"},
    "span": {"term", "num", "label"},
    "sup": {"mark"},
}
META = [{"charset"}, {"name", "content"}, {"http-equiv", "content"}]
REL = "noopener noreferrer"
NO_TIER = (("credit_suisse", "check_dir"), ("trans_american", "check_dir"), ("ge", "check_spac"))


def every_page() -> dict[str, str]:
    found = dict(pages())
    for label, check in NO_TIER:
        found[f"{label}.{check}"] = no_tier_page(label, check)
    return found


def allowed(tag: str, attrs: dict[str, str | None]) -> bool:
    names = set(attrs)
    if tag not in TAGS or any(name.startswith("on") or name == "style" for name in names):
        return False
    if tag == "html":
        return attrs == {"lang": "en"}
    if tag == "meta":
        return names in META
    if tag in CLASSES:
        return names <= {"class"} and attrs.get("class") in CLASSES[tag]
    if tag == "a":
        href = attrs.get("href") or ""
        return names == {"href"} if href.startswith("#") else attrs == {"href": href, "rel": REL}
    if tag == "li":
        return names == {"id"} and (attrs["id"] or "").startswith("source-")
    return not names


def test_the_walk_refuses_what_it_must() -> None:
    assert allowed("p", {"class": "note"}) and allowed("a", {"href": "#source-1"})
    for tag, attrs in (
        ("script", {}), ("iframe", {}), ("form", {}), ("img", {"src": "x"}), ("link", {}),
        ("p", {"style": "x"}), ("p", {"onclick": "x"}), ("p", {"class": "other"}),
        ("a", {"href": "https://www.sec.gov/"}), ("a", {"href": "#x", "rel": REL}),
        ("html", {}), ("meta", {"http-equiv": "refresh"}), ("li", {"id": "x"}), ("h1", {"id": "x"}),
    ):  # fmt: skip
        assert not allowed(tag, dict(attrs)), (tag, attrs)


@pytest.mark.parametrize("name", list(every_page()))
def test_every_tag_and_attribute_is_on_the_allow_list(name: str) -> None:
    parsed = walk(every_page()[name])
    assert parsed.declarations == ["doctype html"]
    refused = [(tag, attrs) for tag, attrs in parsed.starts if not allowed(tag, attrs)]
    assert refused == []


@pytest.mark.parametrize("name", list(pages()))
def test_every_href_is_a_fragment_of_the_page_or_a_link_d71_checked(name: str) -> None:
    record = record_of(name)
    memo = render_memo(record.narrative, record.fact_set)
    checked = {link for source in memo.sources for link in source.links}
    parsed = walk(pages()[name])
    ids = {attrs["id"] for tag, attrs in parsed.starts if tag == "li"}
    assert ids == {f"source-{source.number}" for source in memo.sources}
    hrefs = [attrs["href"] or "" for tag, attrs in parsed.starts if tag == "a"]
    fragments = [h for h in hrefs if h.startswith("#")]
    external = [h for h in hrefs if not h.startswith("#")]
    assert fragments and all(h[1:] in ids for h in fragments)
    assert set(external) == checked
    assert all(h.split("/")[2] in ALLOWED_HOSTS and h.startswith("https://") for h in external)


def csp_of(parsed: Walk) -> str:
    (content,) = [
        attrs["content"] or ""
        for tag, attrs in parsed.starts
        if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy"
    ]
    return content


@pytest.mark.parametrize("name", list(every_page()))
def test_the_policy_refuses_everything_but_the_style_whose_hash_it_names(name: str) -> None:
    parsed = walk(every_page()[name])
    (style,) = [text for tag, text in parsed.texts if tag == "style"]
    digest = base64.b64encode(hashlib.sha256(style.encode("ascii")).digest()).decode("ascii")
    assert csp_of(parsed) == (
        f"default-src 'none'; style-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'"
    )
    assert style.isascii() and "<" not in style


def test_no_page_has_a_script_a_style_attribute_a_form_or_anything_it_would_load() -> None:
    for page in every_page().values():
        lowered = page.lower()
        for banned in ("<script", "<iframe", "<form", "<img", "<link", "<object", "<embed",
                       "<base", " style=", "javascript:", "src=", "@import", "url("):  # fmt: skip
            assert banned not in lowered, banned


def test_markup_in_every_text_slot_of_the_page_shows_only_as_inert_text() -> None:
    record = record_of("agmh.one")
    memo = canary_memo(render_memo(record.narrative, record.fact_set))
    header = header_with(company_name=CANARY, tickers=(CANARY,))
    page = page_html(memo, PROVENANCE.model_copy(update={"model": CANARY}), header, STAMP)
    parsed = walk(page)
    assert [(t, a) for t, a in parsed.starts if not allowed(t, a)] == []
    assert "<script" not in page and "</p> &" not in page
    shown = {tag for tag, text in parsed.texts if CANARY in text}
    assert shown == {"title", "h1", "p", "a", "span"}
    assert (
        "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#x27;q&#x27; &lt;/p&gt;" in page
    )


def test_markup_from_the_recorded_results_is_inert_and_the_security_name_is_never_shown() -> None:
    built = canary_built()
    narrative = record_of("agmh.one").narrative
    memo = render_memo(narrative, built.facts)
    page = page_html(memo, PROVENANCE, page_header(built.context, built.facts), STAMP)
    parsed = walk(page)
    assert [(t, a) for t, a in parsed.starts if not allowed(t, a)] == []
    assert "<script" not in page and "<i>" not in page
    assert any(tag == "h1" and text == CANARY for tag, text in parsed.texts)
    assert any("row <i>AGMH</i>," in text for tag, text in parsed.texts if tag == "a")
    assert "SECNAME" not in page


def test_a_form_type_with_markup_is_refused_by_the_fact_builders() -> None:
    recorded = dict(texts()["agmh"])
    filings = json.loads(recorded["filings20"])
    filings["filings"][0]["form_type"] = "<b>6-K</b>"
    recorded["filings20"] = json.dumps(filings)
    with pytest.raises(IdentityRefused):
        build_fact_set(assemble(recorded, "check_dir"))


def test_the_page_refuses_what_d71_or_the_facts_should_never_hand_it() -> None:
    record = record_of("agmh.one")
    memo = render_memo(record.narrative, record.fact_set)
    header = page_header(record.run_context, record.fact_set)
    first, rest = memo.sources[0], memo.sources[1:]

    def with_source(**changes: object) -> RenderedMemo:
        return memo.model_copy(update={"sources": (first.model_copy(update=changes), *rest)})

    for changes in ({"release": None}, {"links": first.links[:1]}):
        with pytest.raises(RenderRefused):
            page_html(with_source(**changes), PROVENANCE, header, STAMP)
    with pytest.raises(LinkRefused):
        page_html(with_source(links=("https://evil.example/x", first.links[1])), PROVENANCE,
                  header, STAMP)  # fmt: skip
    section = memo.sections[0]
    odd = Term(text="odd", member="odd", key="finding.state")
    claim = section.claims[0].model_copy(update={"segments": (odd,)})
    odd_memo = memo.model_copy(
        update={"sections": (section.model_copy(update={"claims": (claim,)}), *memo.sections[1:])}
    )
    with pytest.raises(RenderRefused):
        page_html(odd_memo, PROVENANCE, header, STAMP)
    with pytest.raises(RenderRefused):
        page_html(
            memo, PROVENANCE, header.model_copy(update={"company_name": "caf" + chr(0xE9)}), STAMP
        )
    facts = record.fact_set.facts
    for kept in ([f for f in facts if f.id != "company.name"], [*facts, *facts]):
        with pytest.raises(RenderRefused):
            page_header(record.run_context, record.fact_set.model_copy(update={"facts": kept}))
