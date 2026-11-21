"""The classification of what the checker found in run 1 (D69): one row for each of the 17
findings on the 17 recorded drafts (15 on first attempts, 2 on the retry of AACG), as classified by
reading each flagged claim. `call` says whether the checker was right (a true catch) or wrong (a
false positive); `cause` says what made the writer or the checker do it: the writer, the prompt,
a field the fact set lacked, or a table (the section table). `claim` counts from one, as the
retry lines do; `entries` are the list entries the claim matched."""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

Call = Literal["true_catch", "false_positive"]
Cause = Literal["writer", "prompt", "missing_field", "table"]


class Row(NamedTuple):
    file: str  # a recording of run-1/
    rule: str
    section: str
    claim: int
    call: Call
    cause: Cause
    entries: tuple[str, ...] = ()


W = "memo.writer-"
R = "memo.writer_retry-"
TC: Final = "true_catch"
FP: Final = "false_positive"
MF: Final = "missing_field"
NM: Final = "not_measured"
DIGIT: Final = "digit_in_text"
QUANT: Final = "quantity_word"
REFS: Final = "ref_not_for_section"
TWO_OF_THREE = ("three", "two")  # "two-of-three" matches two quantity words
ROWS: tuple[Row, ...] = (
    Row(W + "31185aec2ef3.json", DIGIT, "filings", 3, TC, MF),
    Row(W + "31185aec2ef3.json", DIGIT, "filings", 4, TC, MF),
    Row(W + "31185aec2ef3.json", REFS, "verdict", 2, TC, "prompt"),
    Row(R + "caa23aced546.json", DIGIT, "filings", 3, TC, MF),
    Row(R + "caa23aced546.json", DIGIT, "filings", 4, TC, MF),
    Row(W + "1d007ecfba9e.json", QUANT, NM, 3, TC, "prompt", TWO_OF_THREE),
    Row(W + "1d007ecfba9e.json", REFS, "verdict", 2, TC, "prompt"),
    Row(W + "b0c0bb2181cf.json", QUANT, NM, 3, TC, "prompt", TWO_OF_THREE),
    Row(W + "b0c0bb2181cf.json", DIGIT, "filings", 4, TC, MF),
    Row(W + "4c70a20d8d07.json", DIGIT, "filings", 2, TC, MF),
    Row(W + "d0c9fd9ce38d.json", QUANT, NM, 3, TC, "prompt", TWO_OF_THREE),
    Row(W + "d0c9fd9ce38d.json", DIGIT, "filings", 3, TC, MF),
    Row(W + "d0c9fd9ce38d.json", REFS, "verdict", 2, TC, "prompt"),
    Row(W + "d65226790194.json", REFS, NM, 4, FP, "table"),
    Row(W + "0398b4106637.json", QUANT, NM, 5, TC, "table", ("two",)),
    Row(W + "0398b4106637.json", QUANT, "verdict", 1, TC, "writer", ("two",)),
    Row(W + "c80047d9fefe.json", REFS, NM, 4, FP, "table"),
)
