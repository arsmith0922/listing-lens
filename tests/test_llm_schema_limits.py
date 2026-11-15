"""The documented complexity limits and the definition rules (D57), counted by hand.

At most 24 optional properties (a property its object's required list does not name) and at most
16 nodes that use anyOf or a list-valued type, counted from the root with every $ref followed
into its definition at each use. Every definition must be used."""

from __future__ import annotations

from listinglens.llm.schema_graph import MAX_OPTIONAL_PROPERTIES, MAX_UNION_NODES
from tests.llm_schema_support import accepted, closed, optional_object, refused, string, union


def names(count: int, prefix: str = "p") -> list[str]:
    return [f"{prefix}{n}" for n in range(count)]


def uses(definition: str, count: int) -> dict[str, object]:
    """count properties, all required, each a $ref to the definition."""
    return {f"u{n}": {"$ref": f"#/$defs/{definition}"} for n in range(count)}


def test_the_limits_are_the_documented_numbers() -> None:
    assert (MAX_OPTIONAL_PROPERTIES, MAX_UNION_NODES) == (24, 16)


def test_twenty_four_optional_properties_are_accepted_and_twenty_five_are_refused() -> None:
    accepted(optional_object(names(24)))
    refused(optional_object(names(25)), "25 optional properties")


def test_a_required_property_is_not_optional() -> None:
    thirty = {name: string() for name in names(30)}
    accepted({**closed(thirty), "required": names(6)})  # 30 - 6 = 24 optional
    thirty_one = {name: string() for name in names(31)}
    refused({**closed(thirty_one), "required": names(6)}, "25 optional properties")


def test_optional_properties_are_counted_in_nested_objects() -> None:
    def root(inner_count: int) -> dict[str, object]:
        properties = {name: string() for name in names(12, "a")}
        properties["inner"] = optional_object(names(inner_count, "b"))
        return {**closed(properties), "required": ["inner"]}  # 12 + inner_count optional

    accepted(root(12))  # 24
    refused(root(13), "25 optional properties")


def test_optional_properties_are_counted_inside_items_and_alternatives() -> None:
    twelve = optional_object(names(12))
    accepted(
        closed({"a": {"type": "array", "items": twelve}, "b": {"anyOf": [twelve]}})
    )  # 24, 1 union
    thirteen = optional_object(names(13))
    refused(
        closed({"a": {"type": "array", "items": twelve}, "b": {"anyOf": [thirteen]}}), "optional"
    )


def test_sixteen_union_nodes_are_accepted_and_seventeen_are_refused() -> None:
    accepted(closed({name: union() for name in names(16)}))
    refused(closed({name: union() for name in names(17)}), "17 union nodes")


def test_a_list_valued_type_is_a_union_node() -> None:
    accepted(closed({name: {"type": ["string", "null"]} for name in names(16)}))
    refused(closed({name: {"type": ["string", "null"]} for name in names(17)}), "17 union nodes")


def test_anyof_nodes_and_list_valued_types_are_counted_together() -> None:
    mixed = {
        **{name: union() for name in names(8, "a")},
        **{n: {"type": ["string", "null"]} for n in names(8, "t")},
    }
    accepted(closed(mixed))  # 8 + 8 = 16
    refused(closed({**mixed, "extra": union()}), "17 union nodes")


def test_a_node_using_both_anyof_and_a_list_type_counts_once() -> None:
    both: dict[str, object] = {"type": ["string", "null"], "anyOf": [{"type": "string"}]}
    accepted(closed({name: both for name in names(16)}))  # 16, not 32
    refused(closed({name: both for name in names(17)}), "17 union nodes")


def test_union_nodes_are_counted_inside_items_and_nested_objects() -> None:
    inner = closed({name: union() for name in names(8, "i")})
    items = {"type": "array", "items": closed({name: union() for name in names(8, "j")})}
    accepted(closed({"inner": inner, "list": items}))  # 8 + 8 = 16
    refused(closed({"inner": inner, "list": items, "one_more": union()}), "17 union nodes")


def test_a_reference_is_followed_at_every_use_for_optional_properties() -> None:
    definition = optional_object(names(5, "d"))  # 5 optional properties each time it is used
    four = closed(uses("D", 4), **{"$defs": {"D": definition}})
    accepted(four)  # 4 x 5 = 20
    five = closed(uses("D", 5), **{"$defs": {"D": definition}})
    refused(five, "25 optional properties")  # 5 x 5 = 25


def test_a_reference_is_followed_at_every_use_for_union_nodes() -> None:
    definitions = {"$defs": {"U": union()}}
    accepted(closed(uses("U", 16), **definitions))
    refused(closed(uses("U", 17), **definitions), "17 union nodes")


def test_a_reference_through_another_definition_multiplies_at_each_level() -> None:
    leaf = optional_object(names(5, "d"))  # 5 optional each use
    middle = closed(uses("Leaf", 2))  # uses the leaf twice: 10 optional each use
    defs = {"$defs": {"Leaf": leaf, "Middle": middle}}
    accepted(closed(uses("Middle", 2), **defs))  # 2 x 10 = 20
    refused(closed(uses("Middle", 3), **defs), "30 optional properties")  # 3 x 10 = 30


def test_a_use_of_a_definition_inside_an_item_or_alternative_is_counted_too() -> None:
    definitions = {"$defs": {"U": union()}}
    properties: dict[str, object] = {
        **{f"s{n}": {"$ref": "#/$defs/U"} for n in range(8)},
        "list": {"type": "array", "items": {"$ref": "#/$defs/U"}},
        "either": {"anyOf": [{"$ref": "#/$defs/U"}, {"type": "null"}]},
    }
    # 8 direct uses + 1 in items + 1 for the anyOf node itself and 1 for the use inside it = 11
    accepted(closed(properties, **definitions))
    more = {**properties, **{f"t{n}": {"$ref": "#/$defs/U"} for n in range(6)}}
    refused(closed(more, **definitions), "17 union nodes")  # 11 + 6


def test_a_definition_that_no_reference_reaches_is_refused() -> None:
    refused(closed({"v": string()}, **{"$defs": {"Unused": closed({})}}), "never referenced")
    refused(closed({"v": string()}, **{"definitions": {"Unused": closed({})}}), "never referenced")


def test_a_definition_reached_only_by_an_unused_definition_is_refused() -> None:
    defs = {
        "Used": closed({"x": string()}),
        "Orphan": closed({"u": {"$ref": "#/$defs/Hidden"}}),
        "Hidden": closed({"y": string()}),
    }
    refused(closed({"v": {"$ref": "#/$defs/Used"}}, **{"$defs": defs}), "never referenced")


def test_a_definition_reached_through_another_definition_is_used() -> None:
    defs = {
        "Outer": closed({"i": {"$ref": "#/$defs/Inner"}}),
        "Inner": closed({"y": string()}),
    }
    accepted(closed({"v": {"$ref": "#/$defs/Outer"}}, **{"$defs": defs}))


def test_the_definition_check_counts_a_use_inside_items_and_alternatives() -> None:
    defs = {"A": closed({"x": string()}), "B": closed({"y": string()})}
    uses_both = {
        "list": {"type": "array", "items": {"$ref": "#/$defs/A"}},
        "either": {"anyOf": [{"$ref": "#/$defs/B"}, {"type": "null"}]},
    }
    accepted(closed(uses_both, **{"$defs": defs}))
