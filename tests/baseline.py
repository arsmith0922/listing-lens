from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


def read_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


def diff_baseline(expected: set[str], actual: set[str]) -> str | None:
    missing = expected - actual
    unexpected = actual - expected
    if not missing and not unexpected:
        return None
    parts = []
    if missing:
        parts.append(f"recorded in known_failing.txt but did not xfail: {sorted(missing)}")
    if unexpected:
        parts.append(f"xfailed but not recorded in known_failing.txt: {sorted(unexpected)}")
    return "; ".join(parts)


@dataclass(frozen=True)
class RunSelection:
    """What a pytest invocation selected; only an unrestricted run can check the baseline."""

    explicit_args: bool
    keyword: str
    markexpr: str
    last_failed: bool
    failed_first: bool
    stop_early: bool
    collect_only: bool
    stepwise: bool
    deselect: tuple[str, ...]

    @classmethod
    def from_config(cls, config: pytest.Config) -> RunSelection:
        option = config.option
        return cls(
            explicit_args=config.args_source is not pytest.Config.ArgsSource.TESTPATHS,
            keyword=str(getattr(option, "keyword", "")),
            markexpr=str(getattr(option, "markexpr", "")),
            last_failed=bool(getattr(option, "lf", False)),
            failed_first=bool(getattr(option, "failedfirst", False)),
            stop_early=bool(getattr(option, "maxfail", None)),
            collect_only=bool(getattr(option, "collectonly", False)),
            stepwise=bool(getattr(option, "stepwise", False)),
            deselect=tuple(str(item) for item in (getattr(option, "deselect", None) or ())),
        )


def is_full_suite(selection: RunSelection) -> bool:
    """True only for a bare run of the configured testpaths with no selection flag."""
    return not (
        selection.explicit_args
        or selection.keyword
        or selection.markexpr
        or selection.last_failed
        or selection.failed_first
        or selection.stop_early
        or selection.collect_only
        or selection.stepwise
        or selection.deselect
    )
