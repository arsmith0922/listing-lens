"""Run 2 of the drafting script, committed unchanged in live_writer/run-2/ (D70): 9 recordings and a
manifest, nine first attempts and no retries, made with the prompt of D69 (pinned by the hash of the
text `git show d28930a` gives, not by the code, which will move on). They load, match the manifest
byte for byte, replay with the figures the run reported, and show what D69's changes did: the forms
named through form_type, the count of the gaps in not_measured, no disclaimer, and nothing for
today's checker to find. The checks every run shares are in live_run_support."""

from __future__ import annotations

import re
from decimal import Decimal

from listinglens.llm import Recording, load_price_table
from listinglens.llm.cost import price_usage
from listinglens.memo.checker import check_narrative
from listinglens.memo.narrative import Narrative
from listinglens.memo.placeholders import parse_text
from tests.live_run_support import (
    RunSpec,
    check_folder,
    check_manifest,
    check_prompt,
    check_requests,
    replay,
)
from tests.test_memo_classification import draft_of

# the sha256 of the system prompt of D69, from the _PARAGRAPHS literal of
# `git show d28930a:src/listinglens/memo/prompt.py` joined by blank lines (6,063 characters)
D69_PROMPT_SHA = "e31e758a1af3476ea457d9a6b4dfbb3a0ba93504fe4d7eabacc3da3f1625eb07"
MANIFEST_SHA = "76763fac1dcf2d98c8748d1141085d29db945f19c25da3840a33610dfafe9e66"
RUN2 = RunSpec(
    name="run-2",
    recordings=9,
    manifest_sha=MANIFEST_SHA,
    prompt_sha=D69_PROMPT_SHA,
    prompt_chars=6_063,
    purposes={"memo.writer": 9},
    attempts=9,
    tokens=137_995,
    dollars=Decimal("0.51706350"),
)
# the nine recordings in the order they were made: file, the draft it answers, and what it holds:
# claims, inferences, placeholders, form_type placeholders, output tokens, thinking tokens, cost
DRAFTS = (
    ("memo.writer-cf2d99b6242d.json", "aacg.one", 21, 2, 64, 3, 3_211, 0, "0.05097750"),
    ("memo.writer-02a0428b3088.json", "agmh.one", 21, 2, 65, 5, 3_317, 0, "0.04550750"),
    ("memo.writer-45553bc78e4b.json", "aixi.one", 25, 2, 79, 8, 4_102, 0, "0.05508350"),
    ("memo.writer-b9fcfb27f451.json", "credit_suisse.one", 20, 1, 49, 6, 2_671, 0, "0.03844350"),
    ("memo.writer-a93cf9a56484.json", "ge.one", 18, 2, 48, 5, 2_526, 0, "0.03697350"),
    ("memo.writer-44554c250779.json", "luckin.one", 22, 2, 65, 5, 3_686, 0, "0.05159750"),
    ("memo.writer-9d8916cd1e2d.json", "trans_american.one", 20, 2, 67, 7, 3_475, 0, "0.04877750"),
    ("memo.writer-e45a06bc95d1.json", "aixi.three", 30, 1, 139, 7, 8_010, 1_313, "0.11320550"),
    ("memo.writer-76c11f9cbb10.json", "trans_american.three", 24, 2, 76, 8, 4_272, 0, "0.07649750"),
)  # fmt: skip
CACHED_PREFIX = 2_795


def recordings_in_order() -> list[Recording]:
    return sorted(check_prompt(RUN2), key=lambda r: r.recorded_at)


def narrative_of(recording: Recording) -> Narrative:
    return Narrative.model_validate_json(recording.response.text)


def test_run_2_is_nine_recordings_and_a_manifest_and_nothing_else() -> None:
    check_folder(RUN2)


def test_every_recording_loads_and_the_manifest_matches_each_file_byte_for_byte() -> None:
    check_manifest(RUN2)


def test_every_recording_carries_the_prompt_of_d69_and_nothing_else_as_its_system_text() -> None:
    recordings = check_prompt(RUN2)
    for recording in recordings:
        user = recording.request.messages[0].text
        assert user.startswith("FACTS\n") and user.endswith("\nEND OF FACTS\nWrite the narrative.")


def test_run_2_is_nine_first_attempts_no_retry_each_one_a_completed_answer() -> None:
    recordings = check_requests(RUN2)
    assert [r.request.purpose for r in recordings] == ["memo.writer"] * 9
    assert all(len(r.request.messages) == 1 for r in recordings)  # no draft was sent back


def test_the_nine_files_are_the_nine_drafts_in_the_order_they_were_made() -> None:
    made = recordings_in_order()
    assert [f"memo.writer-{r.fingerprint[:12]}.json" for r in made] == [d[0] for d in DRAFTS]
    assert [draft_of(r)[0] for r in made] == [d[1] for d in DRAFTS]
    assert made[0].recorded_at == "2026-11-22T00:56:42+00:00"
    assert made[-1].recorded_at == "2026-11-22T00:59:26+00:00"


def test_the_run_replays_through_the_fake_client_and_the_meter_with_the_figures_it_reported() -> (
    None
):
    totals, recordings = replay(RUN2)
    assert (totals.attempts, totals.tokens, totals.dollars) == (9, 137_995, Decimal("0.5170635"))
    prices = load_price_table()
    costs = [
        str(price_usage(r.response.usage, prices.prices_for(r.request.model)).total)
        for r in sorted(recordings, key=lambda r: r.recorded_at)
    ]
    assert costs == [d[8] for d in DRAFTS]
    usage = [r.response.usage for r in recordings]
    assert sum(u.prompt_tokens for u in usage) == 102_725
    assert sum(u.output_tokens for u in usage) == 35_270


def test_the_claims_inferences_placeholders_and_forms_of_each_draft_and_in_all() -> None:
    for recording, draft in zip(recordings_in_order(), DRAFTS, strict=True):
        claims = [claim for _, _, claim in narrative_of(recording).claims()]
        placeholders = [p for claim in claims for p in parse_text(claim.text).placeholders]
        got = (
            len(claims),
            sum(c.kind == "inference" for c in claims),
            len(placeholders),
            sum(p.field == "form_type" for p in placeholders),
        )
        assert got == draft[2:6], draft[1]
    totals = [sum(int(d[i]) for d in DRAFTS) for i in (2, 3, 4, 5)]
    assert totals == [201, 16, 652, 54]
    assert [d[5] for d in DRAFTS] == [3, 5, 8, 6, 5, 5, 7, 7, 8]


def test_the_gaps_count_is_in_a_not_measured_claim_of_every_draft() -> None:
    for recording in recordings_in_order():
        claims = narrative_of(recording).claims()
        assert any("count.gaps" in c.refs for section, _, c in claims if section == "not_measured")


def test_no_claim_restates_what_the_program_states_in_the_memo() -> None:
    for recording in recordings_in_order():
        for _, _, claim in narrative_of(recording).claims():
            prose = parse_text(claim.text).prose
            assert not re.search(r"investment advice|risk signal|\bAI\b", prose, re.IGNORECASE)


def test_the_largest_output_the_thinking_and_the_cached_prefix() -> None:
    made = recordings_in_order()
    outputs = [r.response.usage.output_tokens for r in made]
    assert outputs == [d[6] for d in DRAFTS] and max(outputs) == 8_010 < 12_000
    thinking = [r.response.usage.thinking_tokens for r in made]
    assert thinking == [d[7] for d in DRAFTS] and thinking.count(0) == 8
    assert [r.response.usage.cache_write_5m_tokens for r in made] == [CACHED_PREFIX] + [0] * 8
    assert [r.response.usage.cache_read_tokens for r in made] == [0] + [CACHED_PREFIX] * 8


def test_today_the_checker_finds_nothing_on_any_of_the_nine_drafts() -> None:
    for recording in recordings_in_order():
        name, view = draft_of(recording)
        narrative = narrative_of(recording)
        assert check_narrative(narrative, view) == (), name
        for _, _, claim in narrative.claims():  # and every placeholder is on a field the fact holds
            for placeholder in parse_text(claim.text).placeholders:
                assert placeholder.field in view.carried[placeholder.fact_id], name
