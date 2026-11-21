from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Protocol

from listinglens.memo import rules_text
from listinglens.memo.narrative import Narrative
from listinglens.memo.placeholders import parse_text

# What the drafting run reports about a draft (D68), so the lists of D67 can be measured without
# reading any draft aloud: how many times each rule fired, and which list entries matched. Both
# are names from fixed lists and counts, never any of the draft.
LIST_RULES = ("quantity_word", "recommendation_phrase", "prediction_phrase")


class HasRule(Protocol):
    @property
    def rule(self) -> str: ...


def rule_counts(findings: Iterable[HasRule]) -> dict[str, int]:
    """How many findings each rule has, sorted by rule name."""
    counts = Counter(finding.rule for finding in findings)
    return dict(sorted(counts.items()))


def entry_counts(narrative: Narrative) -> dict[str, dict[str, int]]:
    """For each list rule, how many times each entry of its list matched in the prose of the
    claims of the draft, placeholders removed as the checker does."""
    found: dict[str, Counter[str]] = {rule: Counter() for rule in LIST_RULES}
    for _, _, claim in narrative.claims():
        prose = parse_text(claim.text).prose
        found["quantity_word"].update(rules_text.quantity_words_in(prose))
        found["recommendation_phrase"].update(rules_text.recommendation_in(prose))
        found["prediction_phrase"].update(rules_text.prediction_in(prose))
    return {rule: dict(sorted(counter.items())) for rule, counter in found.items()}
