from __future__ import annotations

import zipfile
from collections.abc import Generator, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Self

import pytest

from listinglens.core.errors import StandardsConfigError
from listinglens.standards.enums import ProxyPolicy, TranslationPolicy
from listinglens.standards.loader import default_source, load_ruleset
from listinglens.standards.ruleset import Ruleset
from tests.standards_helpers import POLICY_YAML, SYNTHETIC_DIR, record, write_ruleset

RuleFiles = Mapping[str, Sequence[Mapping[str, object]] | str]


def _load(tmp_path: Path, files: RuleFiles, *, policy: str | None = POLICY_YAML) -> Ruleset:
    return load_ruleset(write_ruleset(tmp_path / "set", files, policy=policy))


def _error(
    tmp_path: Path, files: RuleFiles, *, policy: str | None = POLICY_YAML
) -> StandardsConfigError:
    with pytest.raises(StandardsConfigError) as excinfo:
        _load(tmp_path, files, policy=policy)
    return excinfo.value


def _v(rule_id: str = "SYN-V", /, **overrides: object) -> dict[str, object]:
    return record(rule_id=rule_id, **overrides)


def test_the_synthetic_ruleset_loads_in_file_then_record_order() -> None:
    ruleset = load_ruleset(SYNTHETIC_DIR)
    ids = [rule.rule_id for rule in ruleset.rules]
    assert len(ids) == 14
    assert ids[:2] == ["SYN-C-HOLDERS", "SYN-C-BID"]
    assert ids[-1] == "SYN-GS-RECENT-TWO"
    assert ruleset.policy.translation.value is TranslationPolicy.ALLOW_FLAGGED
    assert ruleset.policy.proxy.value is ProxyPolicy.OFF


def test_the_packaged_default_loads_from_inside_the_package() -> None:
    source = default_source()
    assert source.is_dir()
    assert source.joinpath("policy.yaml").is_file()
    ruleset = load_ruleset()
    assert ruleset.policy.translation.value is TranslationPolicy.ALLOW_FLAGGED
    assert ruleset.policy.proxy.value is ProxyPolicy.OFF
    assert "basis" not in str(ruleset.rules)


def test_a_ruleset_loads_from_inside_a_zip_archive_as_it_does_from_a_wheel(
    tmp_path: Path,
) -> None:
    """The loader takes any directory-like source, not only a pathlib path, so the packaged
    rulesets work from an installed wheel (checked for real at build time, see D32)."""
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for source in sorted(SYNTHETIC_DIR.glob("*.yaml")):
            bundle.write(source, f"listinglens/rulesets/nasdaq/{source.name}")
    ruleset = load_ruleset(zipfile.Path(archive, "listinglens/rulesets/nasdaq/"))
    assert [r.rule_id for r in ruleset.rules] == [
        r.rule_id for r in load_ruleset(SYNTHETIC_DIR).rules
    ]


def test_a_ruleset_with_only_a_policy_is_valid_and_empty(tmp_path: Path) -> None:
    assert _load(tmp_path, {}).rules == ()


def test_rule_files_load_in_name_order_whatever_the_write_order(tmp_path: Path) -> None:
    files = {"b.yaml": [_v("SYN-B")], "a.yaml": [_v("SYN-A")]}
    assert [r.rule_id for r in _load(tmp_path, files).rules] == ["SYN-A", "SYN-B"]


class _ReverseListing(Path):
    """A directory source whose listing comes back in reverse name order, as an archive might."""

    def iterdir(self) -> Generator[Self, None, None]:
        yield from sorted(super().iterdir(), key=lambda entry: entry.name, reverse=True)


def test_files_are_read_in_name_order_even_if_the_source_lists_them_otherwise(
    tmp_path: Path,
) -> None:
    directory = write_ruleset(tmp_path / "set", {"a.yaml": [_v("SYN-A")], "b.yaml": [_v("SYN-B")]})
    reversed_source = _ReverseListing(directory)
    assert [e.name for e in reversed_source.iterdir()][:2] == ["policy.yaml", "b.yaml"]
    assert [r.rule_id for r in load_ruleset(reversed_source).rules] == ["SYN-A", "SYN-B"]


def test_other_files_and_subdirectories_are_ignored(tmp_path: Path) -> None:
    directory = write_ruleset(tmp_path / "set", {"a.yaml": [_v()], "notes.txt": "garbage: ["})
    (directory / "sub").mkdir()
    (directory / "sub" / "x.yaml").write_text("garbage: [", encoding="utf-8")
    assert [r.rule_id for r in load_ruleset(directory).rules] == ["SYN-V"]


def test_a_missing_directory_is_typed(tmp_path: Path) -> None:
    with pytest.raises(StandardsConfigError) as excinfo:
        load_ruleset(tmp_path / "nowhere")
    assert excinfo.value.field == "<directory>"


def test_the_policy_file_is_required(tmp_path: Path) -> None:
    error = _error(tmp_path, {"a.yaml": [_v()]}, policy=None)
    assert error.field == "policy.yaml"
    assert error.record == "<ruleset>"


@pytest.mark.parametrize(
    "policy",
    [
        "translation: {value: convert, basis: b}\nproxy: {value: 'off', basis: b}\n",
        "translation: {value: allow_flagged, basis: b}\n",
        "- not a mapping\n",
        "",
    ],
    ids=["bad-enum", "missing-proxy", "list", "empty"],
)
def test_a_malformed_policy_is_typed(tmp_path: Path, policy: str) -> None:
    error = _error(tmp_path, {}, policy=policy)
    assert error.record == "<policy>"
    assert error.path == "set/policy.yaml"


@pytest.mark.parametrize("content", ["a: 1\n", "", "just text\n"], ids=["mapping", "empty", "text"])
def test_a_rule_file_must_be_a_list_of_records(tmp_path: Path, content: str) -> None:
    error = _error(tmp_path, {"a.yaml": content})
    assert (error.field, error.record) == ("<root>", "<file>")


def test_a_bad_record_names_the_file_the_rule_and_the_field(tmp_path: Path) -> None:
    error = _error(tmp_path, {"a.yaml": [_v(), _v("SYN-BAD", tier="bogus")]})
    assert (error.path, error.record, error.field) == ("set/a.yaml", "SYN-BAD", "tier")


def test_a_record_with_no_usable_rule_id_is_labelled_by_position(tmp_path: Path) -> None:
    ok = _v()
    without_id = {k: v for k, v in record().items() if k != "rule_id"}
    error = _error(tmp_path, {"a.yaml": [ok, without_id]})
    assert error.record == "#1"
    assert _error(tmp_path / "second", {"a.yaml": "- not a mapping\n"}).record == "#0"


def test_an_overlong_rule_id_is_truncated_in_the_error(tmp_path: Path) -> None:
    error = _error(tmp_path, {"a.yaml": [_v("x" * 400)]})
    assert len(error.record) == 128


def test_an_unknown_key_is_rejected(tmp_path: Path) -> None:
    assert _error(tmp_path, {"a.yaml": [_v(surprise=1)]}).field == "surprise"


YAML_RULE = """\
- rule_id: SYN-Y
  exchange: nasdaq
  tier: capital
  listing_type: continued
  pathways: [traditional_ipo]
  metric: {kind: concept, concept: stockholders_equity}
  window: {kind: instant}
  comparison: gte
  threshold: THRESHOLD
  threshold_unit: usd
  effective_from: FROM
  citation:
    rule_section: SYN
    rule_url: https://example.invalid/x
    quoted_text: Synthetic quotation.
    retrieved_on: 2026-01-02
  verification: {verified: false}
"""


def _yaml_rule(threshold: str = "1", effective_from: str = "2020-01-01") -> str:
    return YAML_RULE.replace("THRESHOLD", threshold).replace("FROM", effective_from)


def test_a_yaml_decimal_threshold_arrives_exact(tmp_path: Path) -> None:
    ruleset = _load(tmp_path, {"a.yaml": _yaml_rule(threshold="0.123456789012345678")})
    assert ruleset.rules[0].threshold == Decimal("0.123456789012345678")
    assert str(ruleset.rules[0].threshold) == "0.123456789012345678"


@pytest.mark.parametrize(
    ("threshold", "effective_from", "field"),
    [
        ("'5'", "2020-01-01", "threshold"),
        ("5e3", "2020-01-01", "threshold"),
        ("yes", "2020-01-01", "threshold"),
        ("", "2020-01-01", "threshold"),
        ("1", "20200101", "effective_from"),
        ("1", "2020-1-1", "effective_from"),
        ("1", "'2020-01-01 10:00:00'", "effective_from"),
        ("1", "", "effective_from"),
    ],
    ids=[
        "quoted",
        "exponent",
        "bool-word",
        "blank",
        "compact-date",
        "short-date",
        "datetime",
        "blank-date",
    ],
)
def test_yaml_values_the_gates_refuse_are_typed_errors(
    tmp_path: Path, threshold: str, effective_from: str, field: str
) -> None:
    error = _error(tmp_path, {"a.yaml": _yaml_rule(threshold, effective_from)})
    assert (error.record, error.field) == ("SYN-Y", field)


def test_a_duplicate_key_inside_a_record_is_typed(tmp_path: Path) -> None:
    text = _yaml_rule().replace("comparison: gte", "comparison: gte\n  comparison: lte")
    error = _error(tmp_path, {"a.yaml": text})
    assert "duplicate key" in error.detail


def test_a_half_edited_empty_effective_to_does_not_become_open_ended(tmp_path: Path) -> None:
    text = _yaml_rule() + "  effective_to:\n"
    assert _error(tmp_path, {"a.yaml": text}).field == "effective_to"


def test_versions_may_touch_and_may_be_listed_in_any_order(tmp_path: Path) -> None:
    first = _v(effective_to="2024-06-01")
    second = _v(effective_from="2024-06-01", threshold=2)
    ruleset = _load(tmp_path, {"a.yaml": [second, first]})
    assert [r.threshold for r in ruleset.rules] == [Decimal(2), Decimal(1)]


def test_the_same_version_twice_is_rejected_even_across_files(tmp_path: Path) -> None:
    error = _error(tmp_path, {"a.yaml": [_v()], "b.yaml": [_v()]})
    assert (error.record, error.field) == ("SYN-V", "effective_from")
    assert "twice" in error.detail


@pytest.mark.parametrize(
    "later",
    [
        {"effective_from": "2024-05-31"},
        {"effective_from": "2023-01-01"},
    ],
    ids=["overlap", "inside"],
)
def test_overlapping_versions_are_rejected(tmp_path: Path, later: dict[str, object]) -> None:
    first = _v(effective_to="2024-06-01")
    error = _error(tmp_path, {"a.yaml": [first, _v(**later)]})
    assert "overlaps" in error.detail


def test_an_open_ended_version_cannot_be_followed_by_another(tmp_path: Path) -> None:
    error = _error(tmp_path, {"a.yaml": [_v(), _v(effective_from="2024-06-01")]})
    assert "overlaps" in error.detail


@pytest.mark.parametrize(
    ("field", "value"),
    [("tier", "global"), ("listing_type", "initial"), ("standard_id", "SYN-OTHER")],
)
def test_a_rule_keeps_its_identity_across_versions(tmp_path: Path, field: str, value: str) -> None:
    named = {"standard_id": "SYN-S", "standard_name": "Synthetic"}
    first = _v(effective_to="2024-06-01", **named)
    changed = {**named, "effective_from": "2024-06-01", field: value}
    error = _error(tmp_path, {"a.yaml": [first, _v(**changed)]})
    assert error.field == field


@pytest.mark.parametrize(
    ("field", "value"),
    [("standard_name", "Different"), ("tier", "global"), ("listing_type", "initial")],
)
def test_the_rules_of_a_standard_agree(tmp_path: Path, field: str, value: str) -> None:
    named = {"standard_id": "SYN-S", "standard_name": "Synthetic"}
    first = _v("SYN-1", **named)
    second = _v("SYN-2", **{**named, field: value})
    assert _error(tmp_path, {"a.yaml": [first, second]}).field == field


def test_an_explicit_requirement_cannot_collide_with_another_rules_id(tmp_path: Path) -> None:
    named = {"standard_id": "SYN-S", "standard_name": "Synthetic"}
    plain = _v("SYN-A", **named)
    grouped = _v("SYN-B", requirement="SYN-A", **named)
    error = _error(tmp_path, {"a.yaml": [plain, grouped]})
    assert (error.record, error.field) == ("SYN-B", "requirement")


def test_a_requirement_may_be_named_after_the_rule_that_carries_it(tmp_path: Path) -> None:
    named = {"standard_id": "SYN-S", "standard_name": "Synthetic"}
    own = _v("SYN-A", requirement="SYN-A", **named)
    assert len(_load(tmp_path, {"a.yaml": [own]}).rules) == 1
