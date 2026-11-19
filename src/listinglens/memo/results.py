from __future__ import annotations

from typing import Final, Literal, overload

from pydantic import BaseModel, ValidationError, model_validator

from listinglens.core.errors import ToolResultRejected
from listinglens.tools.echo import SCOPE_NOTE, TOOL_CONFIG, ResultBase
from listinglens.tools.models_basic import ListFilingsResult, ResolveCompanyResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult

# The input of the memo (D65): the tool result's text content, the server's own model_dump_json
# (D47), read in JSON mode. The result models are strict, so a decoded dictionary does not
# validate (dates, tuples and enums need JSON mode) and there is no lax route. A refusal names the
# tool, a field of the tool's model, and fixed words; it never carries any of the input.
ToolName = Literal["resolve_company", "list_filings", "extract_financials", "check_standards"]
ToolResult = (
    ResolveCompanyResult | ListFilingsResult | ExtractFinancialsResult | CheckStandardsResult
)
MODELS: Final[dict[str, type[BaseModel]]] = {
    "resolve_company": ResolveCompanyResult,
    "list_filings": ListFilingsResult,
    "extract_financials": ExtractFinancialsResult,
    "check_standards": CheckStandardsResult,
}
MAX_RESULT_BYTES: Final = 1_000_000  # the largest recorded result is under 80 KB
_DETAILS: Final = {
    "json_invalid": "it is not valid JSON",
    "json_type": "it is not a JSON object",
    "recursion_loop": "it is nested too deeply",
    "extra_forbidden": "it has a field the model does not",
    "missing": "a field is missing",
    "model_type": "it is not an object of this model",
}


def _detail(kind: str) -> str:
    if kind in _DETAILS:
        return _DETAILS[kind]
    if kind.endswith("_type") or kind.startswith(("is_instance", "enum", "literal", "date")):
        return "a field has the wrong type or value"
    return "a field does not fit the model"


@overload
def parse_tool_result(tool: Literal["resolve_company"], text: str) -> ResolveCompanyResult: ...
@overload
def parse_tool_result(tool: Literal["list_filings"], text: str) -> ListFilingsResult: ...
@overload
def parse_tool_result(
    tool: Literal["extract_financials"], text: str
) -> ExtractFinancialsResult: ...
@overload
def parse_tool_result(tool: Literal["check_standards"], text: str) -> CheckStandardsResult: ...
@overload
def parse_tool_result(tool: ToolName, text: str) -> ToolResult: ...
def parse_tool_result(tool: ToolName, text: str) -> ToolResult:
    """The tool's result from its text content, or ToolResultRejected."""
    model = MODELS.get(tool)
    if model is None:
        raise ToolResultRejected(str(tool)[:40], "<tool>", "it is not one of the four tools")
    if len(text.encode("utf-8", errors="replace")) > MAX_RESULT_BYTES:
        raise ToolResultRejected(tool, "<payload>", "it is larger than any result can be")
    try:
        parsed = model.model_validate_json(text)
    except ValidationError as exc:
        first = exc.errors()[0]
        head = first["loc"][0] if first["loc"] else None
        field = head if isinstance(head, str) and head in model.model_fields else "<payload>"
        raise ToolResultRejected(tool, field, _detail(first["type"])) from None
    except (RecursionError, ValueError):
        raise ToolResultRejected(tool, "<payload>", _DETAILS["recursion_loop"]) from None
    if not isinstance(
        parsed,
        ResolveCompanyResult | ListFilingsResult | ExtractFinancialsResult | CheckStandardsResult,
    ):
        raise ToolResultRejected(tool, "<payload>", _DETAILS["model_type"])
    return parsed


class ToolResults(BaseModel):
    """The four results of one run about one company. They must describe the same company, carry
    the pinned scope note, agree on whether XBRL facts exist, and the check result must be
    consistent with itself."""

    model_config = TOOL_CONFIG

    resolve: ResolveCompanyResult
    filings: ListFilingsResult
    financials: ExtractFinancialsResult
    check: CheckStandardsResult

    @model_validator(mode="after")
    def _they_describe_one_company_consistently(self) -> ToolResults:
        named: list[tuple[str, ResultBase]] = [
            ("resolve_company", self.resolve),
            ("list_filings", self.filings),
            ("extract_financials", self.financials),
            ("check_standards", self.check),
        ]
        for tool, result in named:
            if result.scope_note != SCOPE_NOTE:
                raise ToolResultRejected(tool, "scope_note", "it is not the pinned scope note")
            if result.company.cik != self.resolve.company.cik:
                raise ToolResultRejected(tool, "company", "it is about another company")
        if self.financials.facts_status != self.check.facts_status:
            raise ToolResultRejected("check_standards", "facts_status", "it differs from the other")
        check = self.check
        tiers = [str(tier.tier) for tier in check.tiers]
        if len(set(tiers)) != len(tiers):
            raise ToolResultRejected("check_standards", "tiers", "a tier appears twice")
        if check.requested_tier is not None and tiers != [str(check.requested_tier)]:
            raise ToolResultRejected("check_standards", "tiers", "they are not the tier asked for")
        matched = sorted(m.ticker for m in check.tier_source.matches)
        if matched != sorted(s.symbol for s in check.nasdaq_status):
            raise ToolResultRejected("check_standards", "nasdaq_status", "it does not fit matches")
        return self
