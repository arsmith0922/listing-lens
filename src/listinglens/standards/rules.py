from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, TypeAdapter, model_validator

from listinglens.core.dates import IsoDate
from listinglens.domain.financials import TargetConcept
from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import (
    Comparison,
    Exchange,
    ListingType,
    ProxyPolicy,
    ThresholdUnit,
    Tier,
    TranslationPolicy,
)
from listinglens.standards.metrics import CONFIG, Metric, Window
from listinglens.standards.quantities import CONCEPT_UNITS, InputKind

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_HTTPS_URL = re.compile(r"https://[A-Za-z0-9.-]+(:[0-9]+)?(/\S*)?")
_ISO_DATE = TypeAdapter(IsoDate)


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError("must be 1-128 letters, digits, dots, underscores, or hyphens")
    return value


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def _https_url(value: str) -> str:
    if not _HTTPS_URL.fullmatch(value):
        raise ValueError("must be an https URL with no whitespace")
    return value


def _date_input(value: object) -> object:
    """A YAML-loaded date is an ISO string, gated by the shared core gate (D28); a typed caller
    may pass a date object. A datetime, a number, or a numeric string is never accepted."""
    if type(value) is date:
        return value
    return _ISO_DATE.validate_python(value)


def _threshold_input(value: object) -> object:
    """Thresholds are exact: an integer or a decimal token, never a float, a string, or a bool.
    NaN and infinity are refused by pydantic's own Decimal validation (pinned by a test)."""
    if isinstance(value, bool) or not isinstance(value, int | Decimal):
        raise ValueError("threshold must be an exact number: an integer or decimal, not text")
    return Decimal(value)


Identifier = Annotated[str, AfterValidator(_identifier)]
NonBlank = Annotated[str, AfterValidator(_non_blank)]
HttpsUrl = Annotated[str, AfterValidator(_https_url)]
RuleDate = Annotated[date, BeforeValidator(_date_input)]
Threshold = Annotated[Decimal, BeforeValidator(_threshold_input)]
StrictBool = Annotated[bool, Field(strict=True)]


class RuleCitation(BaseModel):
    """Where a rule's text and approval can be checked. quoted_text is verbatim."""

    model_config = CONFIG

    rule_section: NonBlank
    rule_url: HttpsUrl
    quoted_text: NonBlank
    retrieved_on: RuleDate
    sec_release: NonBlank | None = None
    sec_release_url: HttpsUrl | None = None

    @model_validator(mode="after")
    def _release_pair(self) -> RuleCitation:
        if (self.sec_release is None) != (self.sec_release_url is None):
            raise ValueError("sec_release and sec_release_url are both set or both omitted")
        return self


class Verification(BaseModel):
    """Checked against the primary source, by whom and when. Unverified rules may still be
    evaluated, but their results are marked (D32); the release gate refuses to certify them."""

    model_config = CONFIG

    verified: StrictBool
    verified_on: RuleDate | None = None
    verified_by: NonBlank | None = None

    @model_validator(mode="after")
    def _both_or_neither(self) -> Verification:
        recorded = self.verified_on is not None and self.verified_by is not None
        absent = self.verified_on is None and self.verified_by is None
        if self.verified and not recorded:
            raise ValueError("a verified rule records verified_on and verified_by")
        if not self.verified and not absent:
            raise ValueError("an unverified rule records neither verified_on nor verified_by")
        return self


class ProxySpec(BaseModel):
    """An explicit stand-in for a rule's real input, used only if the ruleset policy turns
    proxies on, and always reported as 'via proxy'."""

    model_config = CONFIG

    concept: TargetConcept
    caveat: NonBlank


class StandardRule(BaseModel):
    """One requirement. standard_id groups rules that must all hold (a standard); rules with no
    standard_id apply to every standard in their tier. Within a standard, rules sharing a
    requirement are alternatives by branch: a requirement holds if any one branch holds, and a
    branch holds if every rule in it holds. A rule with no requirement is its own requirement."""

    model_config = CONFIG

    rule_id: Identifier
    exchange: Exchange
    tier: Tier
    listing_type: ListingType
    pathways: tuple[Pathway, ...]
    standard_id: Identifier | None = None
    standard_name: NonBlank | None = None
    requirement: Identifier | None = None
    branch: Identifier = "main"
    metric: Metric
    window: Window
    comparison: Comparison
    threshold: Threshold
    threshold_unit: ThresholdUnit
    effective_from: RuleDate | None  # None: never in force (a stayed or pending rule); write ~
    effective_to: RuleDate | None = None
    citation: RuleCitation
    verification: Verification
    proxy: ProxySpec | None = None
    translation_policy: TranslationPolicy | None = None

    @property
    def requirement_key(self) -> str:
        return self.requirement if self.requirement is not None else self.rule_id

    @property
    def requires(self) -> frozenset[InputKind]:
        """The non-EDGAR inputs this rule needs, computed from its metric so there is one source
        of truth. Empty means chunk 12's figures are enough."""
        return self.metric.requires

    @model_validator(mode="after")
    def _consistent(self) -> StandardRule:
        if (self.standard_id is None) != (self.standard_name is None):
            raise ValueError("standard_id and standard_name are both set or both omitted")
        if not self.pathways or len(set(self.pathways)) != len(self.pathways):
            raise ValueError("pathways must be a non-empty list without duplicates")
        if self.threshold_unit is not self.metric.unit:
            raise ValueError(f"threshold_unit must be {self.metric.unit.value} for this metric")
        if self.effective_from is None:
            # Both directions of one rule: a dateless rule is never in force, so it cannot be
            # verified, and a verified rule is live, so it cannot be dateless.
            if self.verification.verified:
                raise ValueError("a verified rule is in force, so it records an effective_from")
            if self.effective_to is not None:
                raise ValueError("effective_to needs an effective_from")
        elif self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        if self.proxy is not None:
            if not self.requires:
                raise ValueError("a proxy only makes sense for a rule that needs a non-EDGAR input")
            if CONCEPT_UNITS[self.proxy.concept] is not self.threshold_unit:
                raise ValueError("the proxy concept must be measured in the rule's threshold unit")
        verified_on = self.verification.verified_on
        if verified_on is not None and verified_on < self.citation.retrieved_on:
            raise ValueError("verified_on must not be before the citation's retrieved_on")
        return self


class TranslationSetting(BaseModel):
    model_config = CONFIG

    value: TranslationPolicy
    basis: NonBlank


class ProxySetting(BaseModel):
    model_config = CONFIG

    value: ProxyPolicy
    basis: NonBlank


class RulesetPolicy(BaseModel):
    """Ruleset-wide choices that are ours, not Nasdaq's. Each records the basis for the choice."""

    model_config = CONFIG

    translation: TranslationSetting
    proxy: ProxySetting
