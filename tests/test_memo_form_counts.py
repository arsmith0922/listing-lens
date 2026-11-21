"""A count of one form of filing carries the form's exact name (D69): set exactly on such counts,
equal to the form of every filing it counts, left out of every serialized form when absent, and the
same over all 42 recorded sets and Xiao-I's hand-counted forms."""

from __future__ import annotations

import json

import pytest

from listinglens.core.errors import FactInvalid, IdentityRefused
from listinglens.memo.build import build_fact_set
from listinglens.memo.canonical import canonical_json, dumps
from listinglens.memo.facts import FactSet
from listinglens.memo.ids import slug
from listinglens.memo.values import CountValue, FilingValue
from tests.memo_results import CHECKS, results_for
from tests.memo_sets import build
from tests.memo_specs import specs
from tests.memo_support import Spec
from tests.test_memo_populations import FILING, count_spec
from tests.tools_stack import CIKS

PREFIX = "filings.form."
# Xiao-I's twenty filings counted by hand from the recorded list (D65's oracle), with the form
# exactly as the SEC writes it
AIXI_FORMS = {
    "6-k": ("6-K", 10),
    "424b5": ("424B5", 3),
    "schedule-13g_a": ("SCHEDULE 13G/A", 2),
    "f-6-pos": ("F-6 POS", 2),
    "schedule-13g": ("SCHEDULE 13G", 1),
    "20-f_a": ("20-F/A", 1),
    "20-f": ("20-F", 1),
}


def refused(items: list[Spec], rule: str) -> None:
    with pytest.raises(FactInvalid) as excinfo:
        build(items)
    assert rule in str(excinfo.value)


@pytest.mark.parametrize(
    ("name", "form_type", "ok"),
    [
        ("filings.form.6-k", "6-K", True),
        ("filings.form.6-k", None, False),  # a form count with no form
        ("filings.returned", "6-K", False),  # a count of something else that has one
        ("gaps", "6-K", False),
        ("tier.global.findings_breached", "6-K", False),
        ("gaps", None, True),
        ("filings.omitted", None, True),
    ],
)
def test_form_type_is_set_on_a_count_of_one_form_and_on_no_other_count(
    name: str, form_type: str | None, ok: bool
) -> None:
    if ok:
        assert CountValue(name=name, count=1, form_type=form_type).form_type == form_type
    else:
        with pytest.raises(FactInvalid):
            CountValue(name=name, count=1, form_type=form_type)


def test_a_form_type_must_be_a_clean_identity() -> None:
    for bad in ("", " 6-K", "6-K ", "6\n-K", "6-K" + chr(0x2014)):
        with pytest.raises(IdentityRefused):
            CountValue(name="filings.form.6-k", count=1, form_type=bad)


def test_a_form_count_whose_form_does_not_match_its_name_is_refused() -> None:
    wrong = count_spec("filings.form.6-k", 1, None, FILING)._replace(
        value={"type": "count", "name": "filings.form.6-k", "count": 1, "form_type": "6_K"}
    )
    refused([*specs(), wrong], "does not match its name")


def test_a_form_count_that_names_another_spelling_of_the_form_is_refused() -> None:
    """The slug of 6-k and 6-K is one, so the population check passes; the exact name does not."""
    other = count_spec("filings.form.6-k", 1, None, FILING)._replace(
        value={"type": "count", "name": "filings.form.6-k", "count": 1, "form_type": "6-k"}
    )
    refused([*specs(), other], "differs from a filing it counts")


def test_a_form_count_must_count_only_filings_of_its_form() -> None:
    good = count_spec("filings.form.6-k", 1, None, FILING)
    assert any(f.id == "count.filings.form.6-k" for f in build([*specs(), good]).facts)
    other = count_spec("filings.form.20-f", 1, None, FILING)  # a 6-K counted as a 20-F
    refused([*specs(), other], "outside its population")


def test_a_zero_form_count_is_checked_for_its_form_and_its_name_only() -> None:
    zero = count_spec("filings.form.8-k", 0, specs()[3].cites)
    assert zero.value["form_type"] == "8-K"
    assert any(f.id == "count.filings.form.8-k" for f in build([*specs(), zero]).facts)
    for form in (None, "9-K"):
        value = {k: v for k, v in zero.value.items() if k != "form_type"}
        bad = zero._replace(value=value if form is None else {**value, "form_type": form})
        with pytest.raises(FactInvalid):
            build([*specs(), bad])


# --- every serialization path leaves out an absent form_type ---------------------------------
def a_set_with_form_counts() -> FactSet:
    return build_fact_set(results_for("aixi", "check_dir")).facts


def test_a_count_without_a_form_serializes_the_same_on_every_path() -> None:
    value = CountValue(name="gaps", count=2)
    assert value.model_dump() == {"type": "count", "name": "gaps", "count": 2}
    assert value.model_dump(mode="json") == {"type": "count", "name": "gaps", "count": 2}
    assert json.loads(value.model_dump_json()) == {"type": "count", "name": "gaps", "count": 2}
    assert "form_type" not in value.model_dump_json()
    assert dumps(value.model_dump(mode="json")) == '{"count":2,"name":"gaps","type":"count"}'


def test_a_count_with_a_form_serializes_it_on_every_path() -> None:
    value = CountValue(name="filings.form.6-k", count=10, form_type="6-K")
    for dumped in (
        value.model_dump(),
        value.model_dump(mode="json"),
        json.loads(value.model_dump_json()),
    ):
        assert dumped["form_type"] == "6-K"


def test_no_count_but_a_form_count_has_the_key_in_the_canonical_json_of_a_set() -> None:
    fact_set = a_set_with_form_counts()
    document = json.loads(canonical_json(fact_set))
    for fact in document["facts"]:
        if fact["kind"] != "count":
            continue
        assert ("form_type" in fact["value"]) == fact["value"]["name"].startswith(PREFIX)
    holders = [f["kind"] for f in document["facts"] if "form_type" in f["value"]]
    assert sorted(set(holders)) == ["count", "filing"]
    assert holders.count("count") == 7 and holders.count("filing") == 20


def test_a_set_with_form_counts_round_trips_through_dump_and_validate_unchanged() -> None:
    fact_set = a_set_with_form_counts()
    assert FactSet.model_validate(fact_set.model_dump()) == fact_set
    assert FactSet.model_validate_json(json.dumps(fact_set.model_dump(mode="json"))) == fact_set
    assert FactSet.model_validate_json(fact_set.model_dump_json()) == fact_set
    again = FactSet.model_validate_json(canonical_json(fact_set))
    assert again == fact_set and canonical_json(again) == canonical_json(fact_set)


# --- the builders, over every recorded set ---------------------------------------------------
def test_over_all_42_sets_each_form_count_names_the_exact_form_of_the_filings_it_counts() -> None:
    sets = 0
    for label in CIKS:
        for check in (*CHECKS, "check_init_one", "check_spac"):
            fact_set = build_fact_set(results_for(label, check)).facts
            by_id = {f.id: f for f in fact_set.facts}
            form_counts = 0
            for fact in fact_set.facts:
                value = fact.value
                if not isinstance(value, CountValue):
                    continue
                if not value.name.startswith(PREFIX):
                    assert value.form_type is None, (label, check, fact.id)
                    continue
                form_counts += 1
                assert value.form_type is not None
                assert slug(value.form_type) == value.name.removeprefix(PREFIX)
                assert fact.id == f"count.{PREFIX}{slug(value.form_type)}"
                assert len(fact.rests_on) == value.count > 0
                for other in fact.rests_on:
                    filing = by_id[other].value
                    assert isinstance(filing, FilingValue) and filing.form_type == value.form_type
            assert 6 <= form_counts <= 10, (label, check)
            sets += 1
    assert sets == 42


def test_the_exact_forms_and_numbers_of_xiao_i_are_the_hand_counted_ones() -> None:
    fact_set = a_set_with_form_counts()
    found = {
        f.value.name.removeprefix(PREFIX): (f.value.form_type, f.value.count)
        for f in fact_set.facts
        if isinstance(f.value, CountValue) and f.value.name.startswith(PREFIX)
    }
    assert found == AIXI_FORMS
    assert sum(count for _, count in AIXI_FORMS.values()) == 20
    assert sum(15 + len(form) for form, _ in AIXI_FORMS.values()) == 156  # bytes added to the view
