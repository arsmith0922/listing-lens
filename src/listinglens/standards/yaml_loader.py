from __future__ import annotations

import re
from collections.abc import Hashable
from decimal import Decimal

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, ScalarNode

from listinglens.core.errors import StandardsConfigError

# The only module that imports PyYAML. Ruleset files are repo-controlled, but they feed
# citations and thresholds, so the loader refuses every YAML feature that could change a value
# silently: PyYAML keeps the last of two duplicate keys, reads `no` as false and `2024-01-01` as
# a date, reads `0755` as octal and `1:30` as sexagesimal, turns 0.1 into a float, and follows
# anchors and aliases. Dates stay strings so the ISO gate decides them (D28), and a decimal token
# becomes an exact Decimal (D27).
MAX_FILE_BYTES = 1024 * 1024
_MAX_DETAIL_CHARS = 500
_FLOAT_TAG = "tag:yaml.org,2002:float"

_BOOL = re.compile(r"^(?:true|false)$")
_NULL = re.compile(r"^(?:~|null)$")
_INT = re.compile(r"^[-+]?(?:0|[1-9][0-9]*)$")
_DECIMAL = re.compile(r"^[-+]?(?:0|[1-9][0-9]*)\.[0-9]+$")
_NUMBER_STARTS = list("-+0123456789")


class _StrictLoader(yaml.SafeLoader):
    # Replace YAML 1.1's implicit typing with a deliberately small set: true/false, null, plain
    # decimal integers, and plain decimals. Everything else, including dates, stays a string.
    # A key with no value is the empty string, not null: a half-edited `effective_to:` must not
    # silently become an open-ended rule. Write ~ or null to mean none.
    yaml_implicit_resolvers: dict[str, list[tuple[str, re.Pattern[str]]]] = {}  # noqa: RUF012

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, object]:
        seen: set[str] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                raise ConstructorError(
                    None, None, "mapping keys must be strings", key_node.start_mark
                )
            if key in seen:
                raise ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _construct_decimal(loader: yaml.SafeLoader, node: ScalarNode) -> Decimal:
    return Decimal(loader.construct_scalar(node))


_StrictLoader.add_implicit_resolver("tag:yaml.org,2002:bool", _BOOL, list("tf"))
_StrictLoader.add_implicit_resolver("tag:yaml.org,2002:null", _NULL, ["~", "n"])
_StrictLoader.add_implicit_resolver("tag:yaml.org,2002:int", _INT, _NUMBER_STARTS)
_StrictLoader.add_implicit_resolver(_FLOAT_TAG, _DECIMAL, _NUMBER_STARTS)
_StrictLoader.add_constructor(_FLOAT_TAG, _construct_decimal)


def _reject_anchors_aliases_and_tags(text: str, name: str) -> None:
    """Scan the parse events, before any value is built, for the features a ruleset never needs.
    An alias always names an anchor, so refusing anchors refuses aliases too."""
    for event in yaml.parse(text, Loader=_StrictLoader):
        if isinstance(event, yaml.NodeEvent) and event.anchor is not None:
            detail = f"anchors and aliases are not allowed (found {event.anchor!r})"
            raise StandardsConfigError(name, "<file>", "<yaml>", detail)
        if isinstance(event, yaml.ScalarEvent | yaml.CollectionStartEvent) and event.tag:
            detail = f"explicit tags are not allowed (found {event.tag!r})"
            raise StandardsConfigError(name, "<file>", "<yaml>", detail)


def parse_yaml(raw: bytes, *, name: str) -> object:
    """Parse one YAML document into plain Python values.

    Returns str, int, bool, None, Decimal, list, and dict[str, ...] only. Raises
    StandardsConfigError for anything else: oversize or non-UTF-8 input, a duplicate key, an
    anchor, alias, or tag, a non-string key, or any YAML syntax error. A single document only.
    """
    if len(raw) > MAX_FILE_BYTES:
        raise StandardsConfigError(name, "<file>", "<size>", f"larger than {MAX_FILE_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StandardsConfigError(name, "<file>", "<encoding>", "not valid UTF-8") from exc
    try:
        _reject_anchors_aliases_and_tags(text, name)
        data: object = yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise StandardsConfigError(name, "<file>", "<yaml>", str(exc)[:_MAX_DETAIL_CHARS]) from exc
    return data
