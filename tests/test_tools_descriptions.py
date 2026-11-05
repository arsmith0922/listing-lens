from __future__ import annotations

import pytest

from listinglens.margin.windows import STALE_AFTER_DAYS
from listinglens.tools import field_text
from listinglens.tools.models_rule import FindingView, NotMeasuredView
from listinglens.tools.models_source import TierSourceReport
from listinglens.tools.models_tier import (
    BranchView,
    RequirementView,
    StandardView,
    TierView,
    VerdictView,
)
from tests.test_tools_field_mapping import VIEWS

# The fields that carry no description because their meaning is self-evident: an identifier, a
# name, a plain figure, a threshold, or a nested model that describes itself (D45). The set is
# exact: a new field without a description fails, and so does a described field left here.
SELF_EVIDENT = frozenset(
    {
        "BranchView.name",
        "CheckStandardsResult.company",
        "CheckStandardsResult.tier_source",
        "CompanyEcho.resolved_from",
        "CrossTagView.concept",
        "CrossTagView.kind",
        "CrossTagView.other_tag",
        "CrossTagView.other_value",
        "CrossTagView.period",
        "CrossTagView.selected_tag",
        "CrossTagView.selected_value",
        "DirectoryCitationView.kind",
        "DirectoryCitationView.symbol",
        "ExtractFinancialsResult.company",
        "ExtractFinancialsResult.figures",
        "ExtractFinancialsResult.gaps",
        "FigureView.citation",
        "FigureView.concept",
        "FigureView.period",
        "FigureView.unit",
        "FigureView.value",
        "FilingView.filed_date",
        "FiscalYearView.accession_no",
        "FiscalYearView.end",
        "FiscalYearView.form_type",
        "FindingView.comparison",
        "FindingView.measured",
        "FindingView.rule_citation",
        "FindingView.rule_id",
        "FindingView.rule_section",
        "FindingView.threshold",
        "FindingView.unit",
        "GapView.concept",
        "IdentityEvidenceView.pretax_tag",
        "IdentityEvidenceView.pretax_value",
        "IdentityEvidenceView.tax_tag",
        "IdentityEvidenceView.tax_value",
        "ListFilingsResult.company",
        "NasdaqStatusView.symbol",
        "NotMeasuredView.comparison",
        "NotMeasuredView.rule_citation",
        "NotMeasuredView.rule_id",
        "NotMeasuredView.rule_section",
        "NotMeasuredView.threshold",
        "NotMeasuredView.unit",
        "ObservationView.accession_no",
        "ObservationView.filed",
        "ObservationView.form_type",
        "ObservationView.value",
        "PeriodView.kind",
        "RequirementView.branches",
        "RequirementView.key",
        "ResolveCompanyResult.company",
        "RestatementView.concept",
        "RestatementView.kind",
        "RestatementView.period",
        "RestatementView.tag",
        "RestatementView.unit",
        "ResultBase.company",
        "StandardView.name",
        "StandardView.requirements",
        "StandardView.standard_id",
        "TierView.verdict",
        "TranslatedFigureView.figure_citation",
        "TranslatedFigureView.translations",
        "TranslationView.value",
        "TwinView.period",
        "TwinView.value",
        "XbrlCitationView.period",
        "XbrlCitationView.source",
        "XbrlCitationView.taxonomy",
        "XbrlCitationView.unit",
    }
)

# The approved texts for the meanings shared across the views, typed here from the ruling.
VALUE = (
    "true: holds on what was measured. false: fails, decided by at least one measured breach. "
    "unknown: cannot be decided from what is on hand."
)
THIN = (
    "true when it holds only by way of conditions that are at risk (inside the cushion band); "
    "always false when value is not true."
)
HEADROOM = (
    "How far the measured value sits on the passing side of the threshold, in the "
    "threshold's unit. Below zero fails; zero passes a gte or lte comparison and "
    "fails a strict gt or lt one."
)
HEADROOM_RATIO = (
    "Headroom divided by the absolute threshold, for display only and never used to decide a "
    "state. Null when the threshold is zero."
)
CUSHION_RATIO = (
    "The at-risk band: a passing result whose headroom is at most this fraction of the absolute "
    "threshold is at_risk rather than clear."
)
LATEST_FISCAL_YEAR = (
    "The end of the company's latest fiscal year, from its own filings: the newest full-year USD "
    "income or revenue period it has reported, cited to the filing that reported it. Compare "
    "each figure's period end with this date: a figure ending more than 183 days before it is "
    "from an earlier fiscal year, and check_standards never measures it as current (the rule "
    "reads stale_figure). Public float is dated at the end of the second fiscal quarter by rule, "
    "so it normally ends about six months earlier and is exempt, as is the share count. Null "
    "when the filings hold no full-year USD income or revenue figure, and then no figure is "
    "checked for staleness."
)
REPORTED_FINANCIALS = (
    "How the conditions testable from SEC XBRL figures look, with every condition that needs a "
    "market price, holder count, or market-maker count assumed met. undetermined means a figure "
    "is absent or a rule needs a multi-year series; individual breaches are still listed in "
    "findings. Figures are as reported, not verified."
)
STANDARDS = (
    "Each standard holds if every one of its requirements holds. The tier is met if every common "
    "requirement holds and, when the tier has standards, at least one of them holds; a tier with "
    "no standards rests on its common requirements alone."
)
VERDICT = (
    "meets: holds, not thinly. at_risk: holds, but thinly. does_not_meet: fails on a measured "
    "breach. cannot_determine: neither passed nor failed, because it depends on something that "
    "was not measured (named in the caveat) or because no rule is in force."
)
CAVEAT = (
    "What the undecided conditions are missing. Empty unless the verdict is cannot_determine "
    "with rules in force."
)
EVALUATED_ON = (
    "The date the result was evaluated for (today, UTC). For check_standards, the rules applied "
    "are the ones in force on this date."
)
WINDOW = (
    "The period the rule reads: one balance (instant), the latest fiscal year, at least n of the "
    "last m fiscal years each tested on its own, or the sum over the last given number of "
    "fiscal years."
)
RULES_IN_FORCE = (
    "false means no Nasdaq rule applies to this selection (for example an initial listing on a "
    "pathway other than traditional_ipo), which is not a pass."
)


def _described(model_name: str, field: str) -> str | None:
    return VIEWS[model_name].model_fields[field].description


def test_exactly_the_self_evident_fields_have_no_description() -> None:
    undescribed = {
        f"{name}.{field}"
        for name, model in VIEWS.items()
        for field, info in model.model_fields.items()
        if not info.description
    }
    assert undescribed - SELF_EVIDENT == set(), "a field has no description"
    assert SELF_EVIDENT - undescribed == set(), "a self-evident field is described now"


def test_every_description_reaches_the_published_json_schema() -> None:
    checked = 0
    for name, model in VIEWS.items():
        properties = model.model_json_schema()["properties"]
        for field, info in model.model_fields.items():
            if info.description:
                assert properties[field].get("description") == info.description, (name, field)
                checked += 1
    total = sum(len(model.model_fields) for model in VIEWS.values())
    assert checked == total - len(SELF_EVIDENT)


@pytest.mark.parametrize(
    ("model", "field", "text"),
    [
        *[(m, "value", VALUE) for m in ("BranchView", "RequirementView", "StandardView")],
        ("VerdictView", "value", VALUE),
        *[(m, "thin", THIN) for m in ("BranchView", "RequirementView", "StandardView")],
        ("VerdictView", "thin", THIN),
        ("FindingView", "headroom", HEADROOM),
        ("FindingView", "headroom_ratio", HEADROOM_RATIO),
        ("FindingView", "cushion_ratio", CUSHION_RATIO),
        ("TierView", "reported_financials", REPORTED_FINANCIALS),
        ("StandardView", "reported_financials", REPORTED_FINANCIALS),
        ("TierView", "rules_in_force", RULES_IN_FORCE),
        ("TierView", "standards", STANDARDS),
        ("VerdictView", "verdict", VERDICT),
        ("VerdictView", "caveat", CAVEAT),
        ("FindingView", "window", WINDOW),
        ("ExtractFinancialsResult", "latest_fiscal_year", LATEST_FISCAL_YEAR),
        ("NotMeasuredView", "window", WINDOW),
        *[(m, "evaluated_on", EVALUATED_ON) for m in ("ResultBase", "CheckStandardsResult")],
    ],
)
def test_the_shared_meanings_are_the_approved_texts_word_for_word(
    model: str, field: str, text: str
) -> None:
    assert _described(model, field) == text


def test_the_text_constants_are_the_approved_texts() -> None:
    assert field_text.VALUE == VALUE
    assert field_text.THIN == THIN
    assert field_text.HEADROOM == HEADROOM
    assert field_text.HEADROOM_RATIO == HEADROOM_RATIO
    assert field_text.CUSHION_RATIO == CUSHION_RATIO
    assert field_text.REPORTED_FINANCIALS == REPORTED_FINANCIALS
    assert field_text.RULES_IN_FORCE == RULES_IN_FORCE
    assert field_text.STANDARDS == STANDARDS
    assert field_text.VERDICT == VERDICT
    assert field_text.CAVEAT == CAVEAT
    assert field_text.EVALUATED_ON == EVALUATED_ON
    assert field_text.WINDOW == WINDOW
    assert field_text.LATEST_FISCAL_YEAR == LATEST_FISCAL_YEAR


def test_the_stale_figure_descriptions_say_what_the_engine_does() -> None:
    kind = _described("ReasonView", "kind") or ""
    assert kind.endswith(
        "stale_figure: the only figure on hand ends more than 183 days before the end of the "
        "company's latest fiscal year, so it is not measured as current."
    )
    assert _described("CaveatView", "stale_concepts") == (
        "Figures whose only value on hand is from an earlier fiscal year than the company's "
        "latest, so the undecided conditions could not measure them as current. "
        "extract_financials shows each beside latest_fiscal_year."
    )
    assert f"more than {STALE_AFTER_DAYS} days" in kind
    assert f"more than {STALE_AFTER_DAYS} days" in field_text.LATEST_FISCAL_YEAR


def test_no_published_description_carries_a_typographic_character() -> None:
    """The approved wording uses a plain ASCII apostrophe everywhere."""
    for name, model in VIEWS.items():
        for field, info in model.model_fields.items():
            text = info.description or ""
            assert text.isascii(), (name, field)


def test_the_meaning_fields_exist_where_the_texts_are_expected() -> None:
    for model in (BranchView, RequirementView, StandardView, VerdictView):
        assert {"value", "thin"} <= set(model.model_fields)
    assert {"headroom", "headroom_ratio", "cushion_ratio"} <= set(FindingView.model_fields)
    assert "primary" in NotMeasuredView.model_fields
    assert "how" in TierSourceReport.model_fields
    assert list(TierView.model_fields)[-1] == "verdict"  # the verdict comes last
    assert list(TierView.model_fields)[:5] == [
        "tier",
        "selected_by_tickers",
        "rules_in_force",
        "note",
        "reported_financials",
    ]
