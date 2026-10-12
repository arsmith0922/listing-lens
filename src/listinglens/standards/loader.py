from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable

from pydantic import BaseModel, ValidationError

from listinglens.core.errors import StandardsConfigError
from listinglens.core.validation import summarize_validation_error
from listinglens.standards.checks import check_rules
from listinglens.standards.rules import RulesetPolicy, StandardRule
from listinglens.standards.ruleset import Ruleset
from listinglens.standards.yaml_loader import parse_yaml

POLICY_FILE = "policy.yaml"
_MAX_RECORD_LABEL = 128


def default_source() -> Traversable:
    """The rulesets shipped inside the package, so the loader works from a source tree and
    from an installed wheel alike."""
    return resources.files("listinglens.standards").joinpath("rulesets").joinpath("nasdaq")


def _read(entry: Traversable, label: str) -> bytes:
    try:
        return entry.read_bytes()
    except OSError as exc:
        raise StandardsConfigError(label, "<file>", "<read>", type(exc).__name__) from exc


def _validate[M: BaseModel](model: type[M], record: object, label: str, record_id: str) -> M:
    try:
        return model.model_validate(record)
    except ValidationError as exc:
        field, detail = summarize_validation_error(model.__name__, exc)
        raise StandardsConfigError(label, record_id[:_MAX_RECORD_LABEL], field, detail) from exc


def _record_id(record: object, index: int) -> str:
    if isinstance(record, dict) and isinstance(record.get("rule_id"), str):
        return str(record["rule_id"])
    return f"#{index}"


def _load_rules(entry: Traversable, label: str) -> list[StandardRule]:
    data = parse_yaml(_read(entry, label), name=label)
    if not isinstance(data, list):
        raise StandardsConfigError(label, "<file>", "<root>", "a rule file is a list of records")
    return [
        _validate(StandardRule, record, label, _record_id(record, index))
        for index, record in enumerate(data)
    ]


def _load_policy(entry: Traversable, label: str) -> RulesetPolicy:
    data = parse_yaml(_read(entry, label), name=label)
    return _validate(RulesetPolicy, data, label, "<policy>")


def load_ruleset(source: Traversable | None = None) -> Ruleset:
    """Load every *.yaml rule file and the policy file from a directory.

    The directory is the packaged one by default; tests pass a path. Any malformed file or
    record raises StandardsConfigError naming the file, the record, and the field. An empty
    directory of rules is valid (a ruleset with no rules yet) but the policy file is required.
    """
    root = source if source is not None else default_source()
    try:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name)
    except OSError as exc:
        raise StandardsConfigError(
            root.name, "<ruleset>", "<directory>", type(exc).__name__
        ) from exc
    rules: list[StandardRule] = []
    policy: RulesetPolicy | None = None
    for entry in entries:
        if not entry.is_file() or not entry.name.endswith(".yaml"):
            continue
        label = f"{root.name}/{entry.name}"
        if entry.name == POLICY_FILE:
            policy = _load_policy(entry, label)
        else:
            rules.extend(_load_rules(entry, label))
    if policy is None:
        raise StandardsConfigError(
            root.name, "<ruleset>", POLICY_FILE, "the policy file is missing"
        )
    check_rules(rules, root.name)
    return Ruleset(rules=tuple(rules), policy=policy)
