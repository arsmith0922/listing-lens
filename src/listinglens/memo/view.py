from __future__ import annotations

from pydantic import BaseModel

from listinglens.memo import rules
from listinglens.memo.canonical import dumps
from listinglens.memo.facts import Fact, FactSet
from listinglens.memo.values import ConditionValue, NotMeasuredValue
from listinglens.tools.echo import TOOL_CONFIG

# What the writer sees of a fact set (D66): one JSON object per fact, in reading order, holding
# the fact's id, kind and value and nothing else. No citation, no citation id, no rests_on, no
# order, no lead mark, no type tag (the last three are functions of the kind or of the id, and the
# rest belong to the renderer) and no run context. So a recorded draft replays on any day, and a
# re-stamped directory changes no byte of it. Two bulky kinds are trimmed: an unmeasured rule keeps
# its section, tier, first reason and missing inputs; a branch condition whose value is unknown is
# left out, because its standard and its unmeasured rules already say so. Every primary fact is
# shown whole.
NOT_MEASURED_SHOWN = ("rule_section", "tier", "primary", "missing_inputs")


class WriterView(BaseModel):
    model_config = TOOL_CONFIG

    text: str  # the fact lines, one per fact, joined by newlines
    kinds: dict[str, str]  # fact id -> kind, for every fact shown
    primary: tuple[str, ...]  # ids of the primary facts shown, in reading order
    # fact id -> the keys of its shown value that hold a value (not null), sorted: exactly what
    # a placeholder may name on that fact (D69)
    carried: dict[str, tuple[str, ...]]


def _shown(fact: Fact) -> bool:
    value = fact.value
    return not (
        isinstance(value, ConditionValue) and value.level == "branch" and value.value == "unknown"
    )


def _shown_value(fact: Fact) -> dict[str, object]:
    value = fact.value.model_dump(mode="json")
    value.pop("type", None)
    if isinstance(fact.value, NotMeasuredValue):
        value = {key: value[key] for key in NOT_MEASURED_SHOWN}
    return value


def _row(fact: Fact) -> str:
    return dumps({"id": fact.id, "kind": fact.kind, "value": _shown_value(fact)})


def build_writer_view(fact_set: FactSet) -> WriterView:
    ordered = [fact for fact in sorted(fact_set.facts, key=lambda f: f.order) if _shown(fact)]
    return WriterView(
        text="\n".join(_row(fact) for fact in ordered),
        kinds={fact.id: fact.kind for fact in ordered},
        primary=tuple(
            fact.id for fact in ordered if rules.expected_lead(fact.kind, fact.value) == "primary"
        ),
        carried={
            fact.id: tuple(
                sorted(key for key, held in _shown_value(fact).items() if held is not None)
            )
            for fact in ordered
        },
    )
