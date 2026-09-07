from __future__ import annotations

from pathlib import Path

from tests.conftest import diff_baseline, read_baseline


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
