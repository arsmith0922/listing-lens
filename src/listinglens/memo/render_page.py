from __future__ import annotations

from html import escape
from typing import Final

from listinglens.core.errors import RenderRefused
from listinglens.memo.render_model import (
    READING_LABEL,
    Provenance,
    RenderedClaim,
    RenderedMemo,
    RenderedSection,
    Segment,
    SourceEntry,
)
from listinglens.memo.render_page_css import PAGE_CSS, style_hash
from listinglens.memo.render_page_head import PageHeader, RecordStamp, dek, footer_lines
from listinglens.memo.render_page_words import DEFINITIONS, KICKER, SOURCES_HEADING, TERMS_HEADING
from listinglens.memo.render_rules import RULES
from listinglens.memo.render_sources import APPROVED_IN, check_link, run_text, runs

# The memo page (D73): one self-contained HTML document made from a rendered memo, its provenance,
# its header and the record's stamp. Every text and every attribute value is escaped with quotes;
# the only links are the memo's own fragments and the links D71 checked, each checked again here
# and never built; there is no script, no style attribute, no form and nothing loaded from
# anywhere, and the Content-Security-Policy refuses all of it and allows the one style by its hash.
# The same inputs always give the same bytes: no clock, no randomness, no locale, LF line endings,
# a final newline, ASCII only.
REL: Final = "noopener noreferrer"
READING: Final = READING_LABEL.removesuffix(": ")
NUMBERS: Final = ("amount", "count")


def _e(text: str) -> str:
    return escape(text, quote=True)


def csp() -> str:
    return f"default-src 'none'; style-src '{style_hash()}'; base-uri 'none'; form-action 'none'"


def _segment(segment: Segment) -> str:
    if segment.kind == "term":
        return f'<span class="term">{_e(segment.text)}</span>'
    if segment.kind == "value" and RULES.get(segment.key) in NUMBERS:
        return f'<span class="num">{_e(segment.text)}</span>'
    return _e(segment.text)


def _marks(claim: RenderedClaim) -> str:
    pieces = [
        f'<a href="#source-{first}">{run_text(first, last)}</a>'
        for first, last in runs(claim.sources)
    ]
    return f'<sup class="mark">{",".join(pieces)}</sup>'


def _claim(claim: RenderedClaim) -> str:
    body = "".join(_segment(segment) for segment in claim.segments) + _marks(claim)
    if claim.kind == "inference":
        return f'<p class="reading"><span class="label">{_e(READING)}</span> {body}</p>'
    return f"<p>{body}</p>"


def _section(section: RenderedSection, memo: RenderedMemo) -> list[str]:
    lines = ["<section>", f"<h2>{_e(section.heading)}</h2>"]
    if section.name == "exchange_status":
        lines.append(f'<p class="note">{_e(memo.exchange_note.text)}</p>')
    lines += [_claim(claim) for claim in section.claims]
    return [*lines, "</section>"]


def _terms(memo: RenderedMemo) -> list[str]:
    """One dt for each word, in order of first appearance, and one dd for each field it is a value
    of in this memo, in order of first appearance."""
    words: dict[str, tuple[str, list[str]]] = {}
    for section in memo.sections:
        for claim in section.claims:
            for segment in claim.segments:
                if segment.kind != "term":
                    continue
                text, keys = words.setdefault(segment.member, (segment.text, []))
                if segment.key not in keys:
                    keys.append(segment.key)
    if not words:
        return []
    lines = ['<section class="terms">', f"<h2>{_e(TERMS_HEADING)}</h2>", "<dl>"]
    for member, (text, keys) in words.items():
        lines.append(f'<dt><span class="term">{_e(text)}</span></dt>')
        for key in keys:
            definition = DEFINITIONS.get((key, member))
            if definition is None:
                raise RenderRefused(key, "a term with no definition")
            lines.append(f"<dd>{_e(definition)}</dd>")
    return [*lines, "</dl>", "</section>"]


def _link(source: SourceEntry, url: str, words: str) -> str:
    return f'<a href="{_e(check_link(source.kind, url))}" rel="{REL}">{_e(words)}</a>'


def _source(source: SourceEntry) -> str:
    wanted = 1 if source.release is None else 2
    if len(source.links) != wanted:
        raise RenderRefused("source", "a source whose links do not fit its label")
    body = _link(source, source.links[0], source.label)
    if source.release is not None:
        body += " " + _link(source, source.links[1], f"{APPROVED_IN} {source.release}") + "."
    return f'<li id="source-{source.number}">{body}</li>'


def page_html(
    memo: RenderedMemo, provenance: Provenance, header: PageHeader, stamp: RecordStamp
) -> str:
    """The page, as one string of ASCII text with LF line endings and a final newline."""
    name = _e(header.company_name)
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta http-equiv="Content-Security-Policy" content="{_e(csp())}">',
        f"<title>{name}: {_e(KICKER)}</title>",
        f"<style>{PAGE_CSS}</style>",
        "</head>",
        "<body>",
        "<header>",
        f'<p class="kicker">{_e(KICKER)}</p>',
        f"<h1>{name}</h1>",
        f'<p class="dek">{_e(dek(header))}</p>',
        '<div class="about">',
        f"<p>{_e(memo.scope_note.text)}</p>",
        f"<p>{_e(memo.ai_disclosure.text)}</p>",
        "</div>",
        "</header>",
    ]
    for section in memo.sections:
        if section.claims:
            lines += _section(section, memo)
    lines += _terms(memo)
    lines += ['<section class="sources">', f"<h2>{_e(SOURCES_HEADING)}</h2>", "<ol>"]
    lines += [_source(source) for source in memo.sources]
    lines += ["</ol>", "</section>", "<footer>"]
    lines += [f"<p>{_e(line)}</p>" for line in footer_lines(provenance, stamp)]
    lines += ["</footer>", "</body>", "</html>"]
    page = "\n".join(lines) + "\n"
    if not page.isascii() or "\r" in page:
        raise RenderRefused("page", "a character that is not ASCII or a carriage return")
    return page
