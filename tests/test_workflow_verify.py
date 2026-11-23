"""The validator of a memo record (D72): every check is reached by the misuse it is for, refuses
with a fixed check and fixed words, and never carries a value, an id of the draft or a word of the
narrative. The purposes are an allow-list that fails closed, the prompt hash is checked for its
form only (a record made under an older prompt still loads), and a record is validated when it is
built and when it is loaded."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from listinglens.core.errors import RecordInvalid
from listinglens.llm.ledger import CallRecord
from listinglens.workflow import MemoRecord, check_record
from listinglens.workflow.verify import CURRENT_FORMAT, PURPOSES
from tests.record_support import (
    NINE,
    ONE,
    TWO,
    call_with,
    context_with,
    directory_with,
    narrative_spoiled,
    record_of,
    retried_record_of,
    writer_with,
)

TODAYS_FORMAT = "memo-record-v1"


def refusal(record: MemoRecord) -> RecordInvalid:
    with pytest.raises(RecordInvalid) as excinfo:
        check_record(record)
    return excinfo.value


@pytest.mark.parametrize("name", NINE)
def test_a_good_record_of_every_draft_passes_and_the_validator_can_be_called_alone(
    name: str,
) -> None:
    check_record(record_of(name))


def test_a_good_record_of_two_attempts_passes() -> None:
    check_record(retried_record_of("agmh.one"))


@pytest.mark.parametrize("scenario", sorted(ONE))
def test_each_misuse_of_a_one_attempt_record_is_refused_by_its_check(scenario: str) -> None:
    check, change = ONE[scenario]
    assert refusal(change(record_of("agmh.one"))).check == check


@pytest.mark.parametrize("scenario", sorted(TWO))
def test_each_misuse_of_a_two_attempt_record_is_refused_by_its_check(scenario: str) -> None:
    check, change = TWO[scenario]
    assert refusal(change(retried_record_of("agmh.one"))).check == check


def test_the_requested_tier_of_a_record_that_has_it_passes_and_another_one_does_not() -> None:
    record = record_of("credit_suisse.one")
    assert record.run_context.requested_tier == "global_select"
    assert refusal(context_with(record, requested_tier="capital")).check == "context"
    check_record(context_with(record, requested_tier=None))


def test_a_record_without_the_exchange_flag_does_not_need_the_directory() -> None:
    record = record_of("trans_american.one")
    assert all(f.kind != "nasdaq_status" for f in record.fact_set.facts)
    check_record(directory_with(record, available=False))


def test_the_directory_is_compared_with_every_directory_citation() -> None:
    record = record_of("aixi.three")
    cites = [c for c in record.fact_set.citations.values() if c.kind == "directory"]
    assert cites
    first = cites[0]
    check_record(directory_with(record, sha256=first.file_sha256, stamp=first.file_created))
    assert refusal(directory_with(record, sha256=None)).check == "context"
    assert refusal(directory_with(record, stamp=None)).check == "context"


@pytest.mark.parametrize("purpose", ["memo.reading", "memo.writer_retry2", "memo.reader", "", "x"])
def test_the_purposes_are_an_allow_list_and_an_unknown_one_fails_closed(purpose: str) -> None:
    assert PURPOSES == ("memo.writer", "memo.writer_retry")
    assert refusal(call_with(record_of("agmh.one"), 0, purpose=purpose)).check == "purposes"
    assert refusal(call_with(retried_record_of("agmh.one"), 1, purpose=purpose)).check == "purposes"


def test_the_prompt_hash_is_checked_for_its_form_and_never_against_todays_prompt() -> None:
    old, new = retried_record_of("agmh.one"), record_of("agmh.one")
    assert old.writer.prompt_sha256 != new.writer.prompt_sha256
    check_record(old)
    check_record(new)
    check_record(writer_with(new, prompt_sha256="0" * 64))
    check_record(writer_with(new, prompt_sha256="0123456789abcdef" * 4))


def test_a_time_in_whole_seconds_in_utc_passes_in_every_spelling_of_utc() -> None:
    record = record_of("agmh.one")
    zero = timezone(timedelta(0))
    for stamp in (
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, 23, 59, 59, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=zero),
    ):
        check_record(record.model_copy(update={"created_at": stamp}))


def test_the_current_format_is_the_one_the_record_builds() -> None:
    assert CURRENT_FORMAT == TODAYS_FORMAT == record_of("agmh.one").format


FIXED_DETAILS = frozenset(
    {
        "the format is not the current one",
        "the time is not timezone-aware UTC",
        "the time is not in whole seconds",
        "the prompt hash is not 64 lowercase hexadecimal characters",
        "the statements are not the current ones in order",
        "the digest is not the fact set's",
        "the directory file is not the one the facts cite",
        "the requested tier is not a tier of the facts",
        "a tier without rules has a verdict",
        "the facts hold the exchange's flag but the directory was not available",
        "the calls are not the writer's call and then its retry",
        "the attempts are not the number of calls",
        "the first attempt's findings do not fit the attempts",
        "a call did not complete",
        "a call's model is not the writer's",
        "the attempts, tokens or failed calls are not the calls'",
        "the dollars are not the calls'",
    }
)


def test_a_refusal_holds_a_fixed_check_and_fixed_words_and_never_a_value_of_the_record() -> None:
    """Every detail is one of the fixed sentences above (the narrative's names rules and nothing
    else), so no value, id or word of the record can be in a message."""
    both = (record_of("agmh.one"), retried_record_of("agmh.one"))
    seen, details = 0, set()
    for scenarios, record in ((ONE, both[0]), (TWO, both[1])):
        for check, change in scenarios.values():
            error = refusal(change(record))
            assert error.check == check and len(error.check) <= 40
            if check == "narrative":
                assert error.detail.startswith("it fails the checker: ")
                assert not [w for w in error.detail.split() if w.endswith(".") or "SECRET" in w]
            else:
                assert error.detail in FIXED_DETAILS, error.detail
                details.add(error.detail)
            assert str(error) == f"The memo record is not valid ({error.check}): {error.detail}"
            seen += 1
    assert seen == len(ONE) + len(TWO)
    assert details == FIXED_DETAILS


def test_the_narrative_refusal_names_the_rules_and_not_a_word_of_the_text() -> None:
    error = refusal(narrative_spoiled(record_of("agmh.one")))
    assert error.detail.startswith("it fails the checker: ")
    names = error.detail.removeprefix("it fails the checker: ").split(", ")
    assert names == sorted(set(names)) and all(n.replace("_", "").isalpha() for n in names)
    assert "SECRETWORD" not in str(error) and "buy" not in str(error)


def test_the_record_is_validated_when_it_is_built_and_when_it_is_loaded() -> None:
    record = record_of("agmh.one")
    text = record.model_dump_json()
    bad = text.replace('"format":"memo-record-v1"', '"format":"memo-record-v0"', 1)
    assert bad != text
    with pytest.raises(RecordInvalid) as excinfo:
        MemoRecord.model_validate_json(bad)
    assert excinfo.value.check == "format"
    fields = {name: getattr(record, name) for name in MemoRecord.model_fields}
    with pytest.raises(RecordInvalid):
        MemoRecord(**{**fields, "attempts": 2})
    assert MemoRecord(**fields) == record


def test_a_record_error_keeps_its_check_short_and_says_where_it_came_from() -> None:
    error = RecordInvalid("x" * 100, "detail")
    assert len(error.check) == 40 and error.detail == "detail"
    assert str(error) == f"The memo record is not valid ({'x' * 40}): detail"
    assert isinstance(call_with(record_of("agmh.one"), 0).calls[0], CallRecord)
