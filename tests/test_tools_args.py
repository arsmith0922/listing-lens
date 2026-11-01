from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from listinglens.core.errors import InputValidationError, ToolArgumentError
from listinglens.domain.company import CompanyRef
from listinglens.tools.args import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CheckStandardsArgs,
    ExtractFinancialsArgs,
    ListFilingsArgs,
    ResolveCompanyArgs,
    company_ref_of,
    form_matches,
    wanted_forms,
)

# The argument models (D46, R13). Structural refusals are Pydantic constraints (ValidationError);
# the one domain-level refusal is ToolArgumentError. The bare base InputValidationError is what
# the server masks as an internal failure, so no refusal may ever surface as it.
MODELS: tuple[type[BaseModel], ...] = (
    ResolveCompanyArgs,
    ExtractFinancialsArgs,
    ListFilingsArgs,
    CheckStandardsArgs,
)
CHECK = {"listing_type": "continued", "pathway": "traditional_ipo"}


def _ref(**fields: object) -> CompanyRef:
    return company_ref_of(ResolveCompanyArgs.model_validate(fields))


# Every way an argument can be refused, as a callable that must raise.
REFUSALS: dict[str, Callable[[], object]] = {
    "no selector": lambda: _ref(),
    "two selectors": lambda: _ref(cik="40545", ticker="GE"),
    "three selectors": lambda: _ref(cik="40545", ticker="GE", name="General Electric"),
    "non-digit cik": lambda: _ref(cik="40x45"),
    "negative cik": lambda: _ref(cik="-5"),
    "zero cik": lambda: _ref(cik="0"),
    "blank cik": lambda: _ref(cik="  "),
    "ticker with a space": lambda: _ref(ticker="G E"),
    "ticker with a symbol": lambda: _ref(ticker="GE$"),
    "blank ticker": lambda: _ref(ticker="   "),
    "blank name": lambda: _ref(name="   "),
    "cik too long": lambda: _ref(cik="12345678901"),
    "empty cik": lambda: _ref(cik=""),
    "ticker too long": lambda: _ref(ticker="ABCDEFGHIJK"),
    "name too long": lambda: _ref(name="x" * 201),
    "cik as a number": lambda: _ref(cik=40545),
    "ticker as a number": lambda: _ref(ticker=5),
    "an extra field": lambda: _ref(cik="40545", as_of="2026-01-01"),
    "a price": lambda: _ref(cik="40545", price="12.5"),
    "limit zero": lambda: ListFilingsArgs(cik="40545", limit=0),
    "limit over the cap": lambda: ListFilingsArgs(cik="40545", limit=MAX_LIMIT + 1),
    "limit as text": lambda: ListFilingsArgs.model_validate({"cik": "1", "limit": "5"}),
    "limit as a bool": lambda: ListFilingsArgs.model_validate({"cik": "1", "limit": True}),
    "too many forms": lambda: ListFilingsArgs(cik="1", forms=tuple(f"F{i}" for i in range(21))),
    "an empty form": lambda: ListFilingsArgs(cik="1", forms=("",)),
    "a form with a wildcard": lambda: ListFilingsArgs(cik="1", forms=("10-*",)),
    "a form that starts with a space": lambda: ListFilingsArgs(cik="1", forms=(" 10-K",)),
    "a form too long": lambda: ListFilingsArgs(cik="1", forms=("A" * 21,)),
    "a bad listing type": lambda: CheckStandardsArgs.model_validate(
        {"cik": "1", "listing_type": "ipo", "pathway": "traditional_ipo"}
    ),
    "a bad pathway": lambda: CheckStandardsArgs.model_validate(
        {"cik": "1", "listing_type": "initial", "pathway": "magic"}
    ),
    "a bad tier": lambda: CheckStandardsArgs.model_validate({"cik": "1", **CHECK, "tier": "main"}),
    "a missing listing type": lambda: CheckStandardsArgs.model_validate(
        {"cik": "1", "pathway": "traditional_ipo"}
    ),
    "a tier given in capitals": lambda: CheckStandardsArgs.model_validate(
        {"cik": "1", **CHECK, "tier": "GLOBAL"}
    ),
}


@pytest.mark.parametrize("name", REFUSALS)
def test_every_refusal_is_a_validation_error_or_a_tool_argument_error(name: str) -> None:
    with pytest.raises(Exception) as raised:
        REFUSALS[name]()
    assert type(raised.value) in (ValidationError, ToolArgumentError), name
    assert type(raised.value) is not InputValidationError


def test_a_refusal_the_domain_makes_is_a_tool_argument_error_with_a_hint() -> None:
    with pytest.raises(ToolArgumentError) as raised:
        _ref(cik="40x45")
    assert (raised.value.field, raised.value.value) == ("cik", "40x45")
    assert "digits" in raised.value.hint
    assert isinstance(raised.value, InputValidationError)  # an input error, but not the bare one


def test_exactly_one_selector_is_required_and_the_message_says_which_were_given() -> None:
    with pytest.raises(ToolArgumentError) as none:
        _ref()
    assert none.value.value == "<none>"
    with pytest.raises(ToolArgumentError) as two:
        _ref(ticker="GE", name="General Electric")
    assert two.value.value == "ticker+name"


def test_a_valid_selector_becomes_the_domain_reference() -> None:
    cik = _ref(cik=" 40545 ")
    assert cik.cik is not None and cik.cik.value == 40545
    assert _ref(ticker=" ge ").ticker is not None
    upper = _ref(ticker="ge").ticker
    assert upper is not None and upper.value == "GE"
    assert _ref(name="General Electric").name == "General Electric"


def test_defaults_and_the_cap_are_the_ones_published() -> None:
    assert (DEFAULT_LIMIT, MAX_LIMIT) == (20, 100)
    args = ListFilingsArgs(cik="40545")
    assert (args.limit, args.forms) == (20, ())
    limit = ListFilingsArgs.model_json_schema()["properties"]["limit"]
    assert (limit["default"], limit["minimum"], limit["maximum"]) == (20, 1, 100)


def test_the_check_standards_arguments_are_accepted_in_every_shape() -> None:
    plain = CheckStandardsArgs.model_validate({"cik": "1", **CHECK})
    named = CheckStandardsArgs.model_validate({"ticker": "AIXI", **CHECK, "tier": "global"})
    assert plain.tier is None and named.tier is not None and named.tier.value == "global"


# What no argument can carry: a price, a market value, a holder count, a market-maker count, or
# a date to evaluate on. Those inputs are not supplied by the caller, so the conditions that need
# them stay "not measured" rather than being answered from the caller's word.
ALLOWED = {
    "cik", "ticker", "name", "forms", "limit", "listing_type", "pathway", "tier",
}  # fmt: skip
FORBIDDEN_WORDS = (
    "price", "value", "cap", "holder", "maker", "share", "float", "volume", "date", "as_of",
    "asof", "when", "day", "time",
)  # fmt: skip


def _property_names(schema: object) -> set[str]:
    """Every property name anywhere in a JSON schema, definitions and nesting included."""
    found: set[str] = set()
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                found.update(str(name) for name in value)
            found |= _property_names(value)
    elif isinstance(schema, list):
        for item in schema:
            found |= _property_names(item)
    return found


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_no_argument_can_carry_a_market_input_or_a_date(model: type[BaseModel]) -> None:
    names = _property_names(model.model_json_schema())
    assert names <= ALLOWED, names - ALLOWED
    for name in names:
        assert not any(word in name for word in FORBIDDEN_WORDS), name
    assert model.model_config.get("extra") == "forbid"


def test_the_four_models_together_use_exactly_the_published_arguments() -> None:
    names: set[str] = set()
    for model in MODELS:
        names |= _property_names(model.model_json_schema())
    assert names == ALLOWED


def test_the_schema_walk_would_see_a_forbidden_field() -> None:
    class Bad(BaseModel):
        market_price: str

    assert _property_names(Bad.model_json_schema()) == {"market_price"}


def test_forms_are_compared_whole_and_without_case() -> None:
    wanted = wanted_forms(("10-k", "8-K/A"))
    assert wanted == {"10-k", "8-k/a"}
    assert form_matches("10-K", wanted)
    assert form_matches("8-k/A", wanted)
    assert not form_matches("10-K/A", wanted)
    assert not form_matches("10-KT", wanted)
    assert not form_matches("8-K", wanted)
    assert form_matches("anything", wanted_forms(()))


def test_the_error_names_the_field_the_value_and_a_hint() -> None:
    error = ToolArgumentError("cik", "40x45", "A CIK is 1 to 10 digits.")
    assert (error.field, error.value, error.hint) == ("cik", "40x45", "A CIK is 1 to 10 digits.")
    assert str(error) == "Invalid value for 'cik': '40x45'. A CIK is 1 to 10 digits."


def _raised_names(source: str) -> list[str]:
    """The name of what every `raise X(...)` in the source constructs."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            func = node.exc.func
            names.append(func.id if isinstance(func, ast.Name) else ast.dump(func))
    return names


def test_no_argument_code_raises_the_bare_base_error() -> None:
    """The server masks the base InputValidationError as internal, so argument code may only
    raise ToolArgumentError (or let Pydantic raise ValidationError)."""
    source = (Path(__file__).parents[1] / "src/listinglens/tools/args.py").read_text("utf-8")
    raised = _raised_names(source)
    assert raised and set(raised) == {"ToolArgumentError"}


def test_the_raise_guard_sees_a_bare_raise() -> None:
    assert _raised_names("raise InputValidationError(field='x', value='y')") == [
        "InputValidationError"
    ]
    assert _raised_names("def f():\n    raise ToolArgumentError('a', 'b', 'c')") == [
        "ToolArgumentError"
    ]
