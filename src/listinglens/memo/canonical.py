from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from listinglens.memo.facts import FactSet

# The one text form of a fact set (D64): sorted keys, no spaces, ASCII only. The facts are stored
# sorted by id, so equal fact sets give equal bytes.


def dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_json(fact_set: FactSet) -> str:
    return dumps(fact_set.model_dump(mode="json"))


def fact_set_digest(fact_set: FactSet) -> str:
    """The SHA-256 of the canonical JSON. Stable only over fixed inputs: citation ids hash the
    directory's stamp and file hash, which change hourly in a live run."""
    return hashlib.sha256(canonical_json(fact_set).encode("ascii")).hexdigest()


def stable_part_json(fact_set: FactSet) -> str:
    """Every fact without its citation ids: its id, kind, lead, order, value and rests_on. None of
    it depends on a citation, so it does not change when the directory is re-stamped. The writer's
    view (a later commit) is built from this part and never shows a citation id."""
    rows = [
        {key: value for key, value in fact.model_dump(mode="json").items() if key != "citations"}
        for fact in fact_set.facts
    ]
    return dumps(rows)
