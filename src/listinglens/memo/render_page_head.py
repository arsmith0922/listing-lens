from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from pydantic import BaseModel

from listinglens.core.errors import RenderRefused
from listinglens.memo import vocab
from listinglens.memo.checker import RULE_ORDER
from listinglens.memo.context import ListingType, Pathway, RunContext, TierHow
from listinglens.memo.facts import FactSet
from listinglens.memo.render_fmt import format_date, group_count
from listinglens.memo.render_model import Provenance
from listinglens.memo.render_page_words import (
    ATTEMPTS,
    CHECKED,
    CONTINUED_QUESTIONS,
    DIRECTORY_UNREAD,
    EVALUATED,
    HASH_PREFIX,
    INITIAL_QUESTIONS,
    NOT_IN_FORCE_NOTE,
    NOT_IN_FORCE_SOME,
    PATHWAY_WORDS,
    RECORDED,
    TIER_NAMES,
    WRITTEN,
    WRITTEN_NO_EFFORT,
)
from listinglens.memo.values import CompanyValue, VerdictValue
from listinglens.tools.echo import TOOL_CONFIG

# What the page's header and footer say (D73), built from the run's context, the fact set, the
# provenance and the record's stamp. The words are the approved ones of render_page_words; this
# module only chooses among them and fills them in. The tiers are in the tools' order, most to
# least stringent.
TIER_ORDER: tuple[vocab.Tier, ...] = ("global_select", "global", "capital")


class PageHeader(BaseModel):
    model_config = TOOL_CONFIG

    company_name: str
    tickers: tuple[str, ...]
    listing_type: ListingType
    pathway: Pathway
    tier_how: TierHow
    requested_tier: vocab.Tier | None
    tiers: tuple[vocab.Tier, ...]  # every tier assessed, with or without a rule in force
    tiers_without_rules: tuple[vocab.Tier, ...]
    evaluated_on: date
    directory_available: bool


class RecordStamp(BaseModel):
    model_config = TOOL_CONFIG

    format: str
    created_at: datetime
    fact_set_digest: str


def page_header(context: RunContext, fact_set: FactSet) -> PageHeader:
    in_order = sorted(fact_set.facts, key=lambda fact: fact.order)
    company = [f.value for f in in_order if isinstance(f.value, CompanyValue)]
    names = [value.text for value in company if value.field == "name"]
    tickers = tuple(value.text for value in company if value.field == "ticker")
    if len(names) != 1:
        raise RenderRefused("company.name", "the fact set does not name the company once")
    verdicts = {f.value.tier for f in fact_set.facts if isinstance(f.value, VerdictValue)}
    assessed = verdicts | set(context.tiers_without_rules)
    return PageHeader(
        company_name=names[0],
        tickers=tickers,
        listing_type=context.listing_type,
        pathway=context.pathway,
        tier_how=context.tier_how,
        requested_tier=context.requested_tier,
        tiers=tuple(tier for tier in TIER_ORDER if tier in assessed),
        tiers_without_rules=tuple(t for t in TIER_ORDER if t in context.tiers_without_rules),
        evaluated_on=context.evaluated_on,
        directory_available=context.directory.available,
    )


def joined(items: Sequence[str]) -> str:
    """Items joined by a comma and a space, the last by " and "."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def tier_names(tiers: Sequence[vocab.Tier]) -> str:
    """The tiers' names joined, each after the "the" of the one before (the first takes the
    "the" of its sentence)."""
    names = [TIER_NAMES[tier] for tier in tiers]
    return joined([names[0], *("the " + name for name in names[1:])]) if names else ""


def _question(header: PageHeader) -> str:
    table = CONTINUED_QUESTIONS if header.listing_type == "continued" else INITIAL_QUESTIONS
    template = table.get(header.tier_how)
    if template is None:
        raise RenderRefused("dek", "a listing type with a tier choice it cannot have")
    tier = header.requested_tier if header.tier_how == "named" else None
    if tier is None and len(header.tiers) == 1:
        tier = header.tiers[0]
    if "{tier}" in template and tier is None:
        raise RenderRefused("dek", "a tier choice with no tier")
    return template.format(
        tier=TIER_NAMES[tier] if tier is not None else "",
        tiers=tier_names(header.tiers),
        pathway=PATHWAY_WORDS[header.pathway],
    )


def dek(header: PageHeader) -> str:
    question = _question(header)
    first = (
        f"{joined(header.tickers)}, {question}."
        if header.tickers
        else question[:1].upper() + question[1:] + "."
    )
    sentences = [first, EVALUATED.format(date=format_date(header.evaluated_on))]
    if header.tiers_without_rules:
        everyone = set(header.tiers_without_rules) == set(header.tiers)
        sentences.append(
            NOT_IN_FORCE_NOTE
            if everyone
            else NOT_IN_FORCE_SOME.format(tiers=tier_names(header.tiers_without_rules))
        )
    if not header.directory_available:
        sentences.append(DIRECTORY_UNREAD)
    return " ".join(sentences)


def footer_lines(provenance: Provenance, stamp: RecordStamp) -> tuple[str, str, str]:
    attempts = ATTEMPTS.get(provenance.attempts)
    if attempts is None:
        raise RenderRefused("footer", "a number of attempts with no words")
    prompt = provenance.prompt_sha256[:HASH_PREFIX]
    written = (
        WRITTEN_NO_EFFORT.format(model=provenance.model, attempts=attempts, prompt=prompt)
        if provenance.effort is None
        else WRITTEN.format(
            model=provenance.model, effort=provenance.effort, attempts=attempts, prompt=prompt
        )
    )
    checked = CHECKED.format(
        rules=len(RULE_ORDER),
        cost=provenance.cost,
        tokens=group_count("footer", provenance.tokens),
        version=provenance.price_table_version,
    )
    made = stamp.created_at
    recorded = RECORDED.format(
        format=stamp.format,
        date=format_date(made.date()),
        time=f"{made.hour:02d}:{made.minute:02d}:{made.second:02d}",
        digest=stamp.fact_set_digest[:HASH_PREFIX],
    )
    return written, checked, recorded
