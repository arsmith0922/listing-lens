"""The classification of run 1's 17 findings (D69), recomputed. Today's checker over the 17 recorded
drafts and the nine views built today gives exactly the 15 true catches of the table and none of the
2 false positives; the views' fact ids and kinds are those the writer was shown; each quantity
row's entries are what its claim matches."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from listinglens.llm import Recording, load_recordings
from listinglens.memo import narrative as n
from listinglens.memo.checker import check_narrative
from listinglens.memo.narrative import Narrative
from listinglens.memo.placeholders import parse_text
from listinglens.memo.rules_text import quantity_words_in
from listinglens.memo.view import WriterView
from tests.draft_memos_support import load_script
from tests.memo_classification import ROWS, Row

RUN1 = Path(__file__).parent / "fixtures" / "llm" / "live_writer" / "run-1"
VIEWS = {d.name: d.view for d in load_script().scenario()}
ROWS_DIGEST = "e451a555a30af9151c689aee4282b2904f1a8c62c03a487bf7248da2cc45ed4b"


def recorded_pairs(recording: Recording) -> list[tuple[str, str]]:
    """The (id, kind) of every fact the writer was shown in this recording's first user turn."""
    text = recording.request.messages[0].text
    rows = text.split("\nEND OF FACTS\n")[0].removeprefix("FACTS\n").split("\n")
    return [(json.loads(line)["id"], json.loads(line)["kind"]) for line in rows]


def pairs(view: WriterView) -> list[tuple[str, str]]:
    return [(json.loads(line)["id"], json.loads(line)["kind"]) for line in view.text.split("\n")]


def recordings() -> dict[str, Recording]:
    """The recordings of run 1 by file name."""
    return {f"{r.request.purpose}-{r.fingerprint[:12]}.json": r for r in load_recordings(RUN1)}


def draft_of(recording: Recording) -> tuple[str, WriterView]:
    """The scenario draft whose facts (ids and kinds, in order) the recording was shown."""
    wanted = recorded_pairs(recording)
    (name,) = [name for name, view in VIEWS.items() if pairs(view) == wanted]
    return name, VIEWS[name]


def claim_of(row: Row) -> str:
    narrative = Narrative.model_validate_json(recordings()[row.file].response.text)
    (found,) = [c for s, i, c in narrative.claims() if (s, i + 1) == (row.section, row.claim)]
    return found.text


def findings_today() -> set[tuple[str, str, str, int]]:
    found: set[tuple[str, str, str, int]] = set()
    for file, recording in recordings().items():
        narrative = Narrative.model_validate_json(recording.response.text)
        for finding in check_narrative(narrative, draft_of(recording)[1]):
            assert finding.section is not None and finding.claim_index is not None
            found.add((file, finding.rule, finding.section, finding.claim_index + 1))
    return found


def key(row: Row) -> tuple[str, str, str, int]:
    return (row.file, row.rule, row.section, row.claim)


def test_the_views_built_today_hold_the_facts_the_writer_was_shown_in_the_same_order() -> None:
    assert len(recordings()) == 17
    names = Counter(draft_of(r)[0] for r in recordings().values())  # one view for each recording
    assert names == {
        "aacg.one": 2, "agmh.one": 2, "aixi.one": 2, "credit_suisse.one": 2, "ge.one": 1,
        "luckin.one": 2, "trans_american.one": 2, "aixi.three": 2, "trans_american.three": 2,
    }  # fmt: skip
    for recording in recordings().values():
        view = draft_of(recording)[1]
        assert [fact_id for fact_id, _ in recorded_pairs(recording)] == list(view.kinds)


def test_today_the_checker_finds_the_fifteen_true_catches_and_not_the_two_false_positives() -> None:
    today = findings_today()
    true = {key(r) for r in ROWS if r.call == "true_catch"}
    false = {key(r) for r in ROWS if r.call == "false_positive"}
    assert today == true and len(true) == 15
    assert not today & false and len(false) == 2


def test_the_false_positives_are_gone_because_the_gaps_now_belong_to_not_measured() -> None:
    assert n.sections_of_count("gaps") == ("reported_financials", "not_measured")
    for row in (r for r in ROWS if r.call == "false_positive"):
        narrative = Narrative.model_validate_json(recordings()[row.file].response.text)
        (claim,) = [c for s, i, c in narrative.claims() if (s, i + 1) == (row.section, row.claim)]
        assert "count.gaps" in claim.refs  # the claim is the one the old table refused


def test_the_entries_of_each_row_are_what_its_claim_matches() -> None:
    for row in ROWS:
        found = quantity_words_in(parse_text(claim_of(row)).prose)
        assert (found if row.rule == "quantity_word" else ()) == row.entries, row


def test_the_table_is_pinned_by_its_counts_and_its_digest() -> None:
    assert len(ROWS) == 17 and len({key(r) for r in ROWS}) == 17
    assert Counter(r.call for r in ROWS) == {"true_catch": 15, "false_positive": 2}
    assert Counter(r.cause for r in ROWS) == {
        "missing_field": 7,
        "prompt": 6,
        "writer": 1,
        "table": 3,
    }
    assert Counter(r.rule for r in ROWS) == {
        "digit_in_text": 7,
        "quantity_word": 5,
        "ref_not_for_section": 5,
    }
    assert sum(r.file.startswith("memo.writer_retry-") for r in ROWS) == 2
    shown = json.dumps([list(r) for r in ROWS], sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(shown.encode()).hexdigest() == ROWS_DIGEST


def test_every_recorded_draft_is_either_in_the_table_or_clean() -> None:
    in_table = {r.file for r in ROWS}
    clean = set(recordings()) - in_table
    assert len(in_table) == 9 and len(clean) == 8
    assert {f for f in clean if f.startswith("memo.writer-")} == {"memo.writer-3db3450b48c4.json"}
