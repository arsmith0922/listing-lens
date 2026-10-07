from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from _pytest.config import _prepareconfig

from tests.baseline import RunSelection, diff_baseline, is_full_suite, read_baseline

BARE = RunSelection(
    explicit_args=False,
    keyword="",
    markexpr="",
    last_failed=False,
    failed_first=False,
    stop_early=False,
    collect_only=False,
    stepwise=False,
    deselect=(),
)


def test_read_baseline_ignores_blank_lines_and_comments(tmp_path: Path) -> None:
    baseline = tmp_path / "known_failing.txt"
    baseline.write_text(
        "# a comment\n\ntests/test_x.py::test_a\n  \ntests/test_x.py::test_b\n",
        encoding="utf-8",
    )
    assert read_baseline(baseline) == {"tests/test_x.py::test_a", "tests/test_x.py::test_b"}


def test_read_baseline_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_baseline(tmp_path / "does_not_exist.txt") == set()


def test_diff_baseline_matching_sets_is_none() -> None:
    both = {"tests/test_x.py::test_a"}
    assert diff_baseline(both, both) is None


def test_diff_baseline_reports_missing_expected_xfail() -> None:
    expected = {"tests/test_x.py::test_a"}
    actual: set[str] = set()
    mismatch = diff_baseline(expected, actual)
    assert mismatch is not None
    assert "did not xfail" in mismatch
    assert "test_a" in mismatch


def test_diff_baseline_reports_unexpected_xfail() -> None:
    expected: set[str] = set()
    actual = {"tests/test_x.py::test_b"}
    mismatch = diff_baseline(expected, actual)
    assert mismatch is not None
    assert "not recorded in known_failing.txt" in mismatch
    assert "test_b" in mismatch


def test_bare_run_is_a_full_suite() -> None:
    assert is_full_suite(BARE) is True


@pytest.mark.parametrize(
    "selection",
    [
        replace(BARE, explicit_args=True),
        replace(BARE, keyword="needle"),
        replace(BARE, markexpr="slow"),
        replace(BARE, last_failed=True),
        replace(BARE, failed_first=True),
        replace(BARE, stop_early=True),
        replace(BARE, collect_only=True),
        replace(BARE, stepwise=True),
        replace(BARE, deselect=("tests/test_x.py::test_a",)),
    ],
)
def test_any_selection_means_not_a_full_suite(selection: RunSelection) -> None:
    assert is_full_suite(selection) is False


@pytest.mark.parametrize(
    ("args", "expected_full"),
    [
        ([], True),
        (["tests/test_errors.py"], False),
        (["tests"], False),
        (["-k", "needle"], False),
        (["-m", "slow"], False),
        (["--lf"], False),
        (["--ff"], False),
        (["-x"], False),
        (["--maxfail=2"], False),
        (["--collect-only"], False),
        (["--deselect", "tests/test_x.py::test_a"], False),
        (["-q"], True),
    ],
)
def test_real_pytest_config_is_classified_by_its_invocation(
    args: list[str], expected_full: bool
) -> None:
    config = _prepareconfig(args)
    try:
        assert is_full_suite(RunSelection.from_config(config)) is expected_full
    finally:
        config._ensure_unconfigure()
