from __future__ import annotations

from decimal import Decimal

import pytest

from listinglens.core.errors import StandardsConfigError
from listinglens.standards.yaml_loader import MAX_FILE_BYTES, parse_yaml


def _parse(text: str) -> object:
    return parse_yaml(text.encode("utf-8"), name="t.yaml")


def _rejects(text: str, match: str) -> None:
    with pytest.raises(StandardsConfigError, match=match) as excinfo:
        _parse(text)
    assert excinfo.value.path == "t.yaml"
    assert excinfo.value.record == "<file>"


def test_it_returns_plain_python_values() -> None:
    data = _parse("a: 1\nb: true\nc: ~\nd: text\ne: [1, 2]\nf: {g: 0.5}\n")
    assert data == {
        "a": 1,
        "b": True,
        "c": None,
        "d": "text",
        "e": [1, 2],
        "f": {"g": Decimal("0.5")},
    }


@pytest.mark.parametrize("token", ["0.123456789012345678", "1.5", "-2.25", "0.10", "100.0"])
def test_a_decimal_token_is_an_exact_decimal_with_its_digits_kept(token: str) -> None:
    value = _parse(f"v: {token}\n")
    assert isinstance(value, dict)
    assert isinstance(value["v"], Decimal)
    assert str(value["v"]) == token


def test_an_integer_stays_an_integer_not_a_float() -> None:
    value = _parse("v: 5000000\n")
    assert value == {"v": 5000000}
    assert isinstance(value, dict)
    assert type(value["v"]) is int


@pytest.mark.parametrize(
    "token",
    [
        "0755",
        "0o17",
        "0x1F",
        "0b11",
        "1_000",
        "1e3",
        "1.5e3",
        ".5",
        "5.",
        "1:30",
        "1:30:00",
        "+.5",
        "1.0.0",
    ],
)
def test_numeric_looking_text_that_is_not_a_plain_decimal_stays_a_string(token: str) -> None:
    """YAML 1.1 would read these as octal, hex, binary, grouped, exponent, or sexagesimal."""
    assert _parse(f"v: {token}\n") == {"v": token}


@pytest.mark.parametrize(
    "word", ["yes", "no", "on", "off", "y", "n", "True", "False", "TRUE", "Yes"]
)
def test_bool_words_other_than_true_and_false_stay_strings(word: str) -> None:
    assert _parse(f"v: {word}\n") == {"v": word}


@pytest.mark.parametrize("word", ["Null", "NULL", "none"])
def test_null_words_other_than_null_and_tilde_stay_strings(word: str) -> None:
    assert _parse(f"v: {word}\n") == {"v": word}


@pytest.mark.parametrize(
    "token", ["2024-01-01", "2024-01-01 10:00:00", "2024-01-01T10:00:00Z", "2024-1-1"]
)
def test_dates_stay_strings_so_the_iso_gate_decides(token: str) -> None:
    assert _parse(f"v: {token}\n") == {"v": token}


def test_a_key_with_no_value_is_an_empty_string_never_null() -> None:
    """A half-edited `effective_to:` must not silently become an open-ended rule."""
    assert _parse("v:\n") == {"v": ""}
    assert _parse("v: ~\n") == {"v": None}
    assert _parse("v: null\n") == {"v": None}


def test_a_compact_date_is_an_integer_which_the_date_gate_then_refuses() -> None:
    assert _parse("v: 20240101\n") == {"v": 20240101}


def test_a_block_scalar_keeps_its_text() -> None:
    assert _parse("v: >-\n  one\n  two\n") == {"v": "one two"}


@pytest.mark.parametrize(
    "text",
    ["a: 1\na: 2\n", "outer:\n  k: 1\n  k: 2\n", "- {k: 1, k: 2}\n", "a: 1\n'a': 2\n"],
    ids=["top", "nested", "flow", "quoted-twin"],
)
def test_a_duplicate_key_is_rejected_not_last_wins(text: str) -> None:
    _rejects(text, "duplicate key")


@pytest.mark.parametrize("text", ["1: x\n", "true: x\n", "? [a, b]\n: x\n", "null: x\n"])
def test_mapping_keys_must_be_strings(text: str) -> None:
    _rejects(text, "keys must be strings")


@pytest.mark.parametrize(
    "text",
    ["a: &x 1\nb: 2\n", "a: &x 1\nb: *x\n", "- &r {k: 1}\n- *r\n", "a: *undefined\n"],
    ids=["anchor", "alias", "anchored-map", "undefined-alias"],
)
def test_anchors_and_aliases_are_rejected(text: str) -> None:
    with pytest.raises(StandardsConfigError):
        _parse(text)
    _rejects("a: &x 1\nb: 2\n", "anchors and aliases are not allowed")


@pytest.mark.parametrize(
    "text",
    [
        "a: !!str 5\n",
        "a: !!int '5'\n",
        "a: !!python/object:os.system x\n",
        "a: !custom x\n",
        "!!map {a: 1}\n",
    ],
)
def test_explicit_tags_are_rejected(text: str) -> None:
    _rejects(text, "explicit tags are not allowed")


def test_a_merge_key_is_not_a_merge() -> None:
    """With no anchors there is nothing to merge, and the key stays an ordinary string key that
    the schema then refuses as an unknown field."""
    assert _parse("<<: {a: 1}\n") == {"<<": {"a": 1}}


def test_only_one_document_is_allowed() -> None:
    _rejects("a: 1\n---\nb: 2\n", "expected a single document")


def test_an_empty_file_is_none() -> None:
    assert _parse("") is None
    assert _parse("# only a comment\n") is None


def test_a_utf8_byte_order_mark_is_accepted() -> None:
    """Editors on Windows add one; PyYAML skips it, and this pins that behavior."""
    assert parse_yaml(b"\xef\xbb\xbfa: 1\n", name="t.yaml") == {"a": 1}


@pytest.mark.parametrize(
    "text", ["a: [1, 2\n", "a: b: c\n", "a:\n\t- 1\n", "- a\nb: 1\n", "a: 'unterminated\n"]
)
def test_yaml_syntax_errors_are_typed(text: str) -> None:
    with pytest.raises(StandardsConfigError) as excinfo:
        _parse(text)
    assert excinfo.value.field == "<yaml>"
    assert len(excinfo.value.detail) <= 500


def test_invalid_utf8_is_typed() -> None:
    with pytest.raises(StandardsConfigError) as excinfo:
        parse_yaml(b"a: \xff\xfe\n", name="t.yaml")
    assert excinfo.value.field == "<encoding>"


def test_the_size_cap_is_enforced_at_the_boundary() -> None:
    at_cap = b"#" * (MAX_FILE_BYTES - 1) + b"\n"
    assert len(at_cap) == MAX_FILE_BYTES
    assert parse_yaml(at_cap, name="t.yaml") is None
    with pytest.raises(StandardsConfigError) as excinfo:
        parse_yaml(at_cap + b"#", name="t.yaml")
    assert excinfo.value.field == "<size>"


def test_a_long_syntax_error_message_is_bounded() -> None:
    with pytest.raises(StandardsConfigError) as excinfo:
        _parse("a: [" + "x" * 5000 + "\n")
    assert len(excinfo.value.detail) <= 500
