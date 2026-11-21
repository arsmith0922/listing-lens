from __future__ import annotations

import re
from typing import Final, NamedTuple

# How a value enters the narrative text (D66): a placeholder {fact-id:field}, filled by the
# renderer from the fact. The grammar is one regular expression; a brace left over after the
# placeholders are removed is malformed text. The fields a placeholder may name are an allowlist
# per kind of fact, and each field is one the writer's view shows for that kind (a test pins it),
# so the writer is never told to use a field it cannot see. Kinds with no field (the two caveats)
# cannot be the subject of a placeholder. A figure's period is one field: the renderer words it.
PLACEHOLDER: Final = re.compile(r"\{([a-z0-9][a-z0-9._-]{0,254}):([a-z_]{1,32})\}")
FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "company": ("text",),
    "filing": ("form_type", "filed", "report_date"),
    "fiscal_year": ("end",),
    "data_status": ("status",),
    "figure": ("amount", "unit", "period"),
    "gap": ("concept", "reason"),
    "nasdaq_status": ("symbol", "market_category", "financial_status", "status", "tier"),
    "finding": ("measured", "threshold", "headroom", "state", "rule_section", "unit"),
    "not_measured": ("rule_section", "primary"),
    "condition_status": ("standard_name", "value"),
    "reported_financials": ("signal",),
    "verdict": ("verdict",),
    "count": ("count",),
}


class Placeholder(NamedTuple):
    fact_id: str
    field: str


class ParsedText(NamedTuple):
    prose: str  # the text with every placeholder removed
    placeholders: tuple[Placeholder, ...]
    malformed: bool  # a brace is left in the prose


def parse_text(text: str) -> ParsedText:
    found = tuple(Placeholder(m.group(1), m.group(2)) for m in PLACEHOLDER.finditer(text))
    prose = PLACEHOLDER.sub("", text)
    return ParsedText(prose, found, "{" in prose or "}" in prose)
