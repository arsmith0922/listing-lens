"""Every way the memo command ends (D74): its exit code, its one fixed line, the cost line wherever
the model step was reached and nowhere else, nothing saved, and no value: never an argument, the
contact, the key, a company's name, a tool's own error text or an exception's message."""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pytest

from listinglens.llm.budget import Budget
from listinglens.llm.models import StopReason
from listinglens.workflow import command, run
from listinglens.workflow import command_text as text
from listinglens.workflow.run import OpenTools
from tests.command_support import (
    AGMH,
    CONTACT,
    KEY_CANARY,
    Model,
    broken,
    fixed_clock,
    in_process,
    memo_folder,
    other_server,
    replies,
    swapped,
)

__all__ = ["memo_folder"]
SECRETS = (CONTACT, KEY_CANARY, "AGM GROUP", "Company not found", "SECRET-VALUE", "SECRETVAL")
COST = "Cost: {d} dollars, {t} tokens, price table version 1. Model calls made: {n}."


def ended(
    capsys: pytest.CaptureFixture[str],
    argv: Sequence[str],
    tools: OpenTools | None = None,
    model: Model | None = None,
) -> tuple[int, list[str]]:
    code = command.main(
        [*argv, "--out", "out"], open_tools=tools or broken(), model_source=model,
        now=fixed_clock,
    )  # fmt: skip
    captured = capsys.readouterr()
    assert captured.out == ""
    assert not [s for s in SECRETS if s in captured.err]
    assert not Path("out").exists() or list(Path("out").iterdir()) == []
    return code, captured.err.splitlines()


@pytest.mark.parametrize(
    ("argv", "line"),
    [
        (("--listing-type", "continued", "--pathway", "traditional_ipo"), text.ONE_COMPANY),
        (("--cik", "1", "--ticker", "X", "--listing-type", "continued", "--pathway",
          "traditional_ipo"), text.ONE_COMPANY),
        (("--cik", "SECRET-VALUE", "--listing-type", "continued", "--pathway", "traditional_ipo"),
         text.BAD_OPTION.format(option="cik")),
        (("--cik", "SECRETVAL", "--listing-type", "continued", "--pathway", "traditional_ipo"),
         text.BAD_OPTION.format(option="cik")),
        (("--cik", "1", "--listing-type", "SECRET-VALUE", "--pathway", "traditional_ipo"),
         text.BAD_OPTION.format(option="listing-type")),
        (("--cik", "1", "--listing-type", "continued", "--pathway", "SECRET-VALUE"),
         text.BAD_OPTION.format(option="pathway")),
        ((*AGMH, "--tier", "SECRET-VALUE"), text.BAD_OPTION.format(option="tier")),
        ((*AGMH, "--limit", "0"), text.BAD_OPTION.format(option="limit")),
        ((*AGMH, "--limit", "SECRET-VALUE"), text.BAD_OPTION.format(option="limit")),
        ((*AGMH, "--SECRET-VALUE", "x"), text.BAD_ARGUMENTS),
        (("--cik", "1", "--listing-type", "continued"), text.BAD_ARGUMENTS),
    ],
)  # fmt: skip
def test_a_bad_argument_exits_2_before_anything_is_called(
    memo_folder: Path, capsys: pytest.CaptureFixture[str], argv: tuple[str, ...], line: str
) -> None:
    model = Model()
    assert ended(capsys, argv, model=model) == (text.EXIT_ARGUMENT, [line])
    assert model.client is None


@pytest.mark.parametrize(
    ("variable", "value", "line"),
    [
        ("SEC_EDGAR_CONTACT", None, text.NO_CONTACT),
        ("SEC_EDGAR_CONTACT", "your-email@example.com", text.NO_CONTACT),
        ("LISTINGLENS_CACHE_DIR", None, text.NO_CACHE),
        ("LISTINGLENS_CACHE_DIR", "relative/cache", text.NO_CACHE),
        ("LISTINGLENS_CACHE_DIR", "<a file>", text.BAD_CACHE),
    ],
)
def test_a_setting_that_is_missing_or_unusable_exits_3(
    memo_folder: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str | None,
    line: str,
) -> None:
    if value is None:
        monkeypatch.delenv(variable)
    elif value == "<a file>":
        (memo_folder / "a-file").write_text("x")
        monkeypatch.setenv(variable, str(memo_folder / "a-file"))
    else:
        monkeypatch.setenv(variable, value)
    model = Model()
    assert ended(capsys, AGMH, model=model) == (text.EXIT_CONFIG, [line])
    assert model.client is None


def test_the_settings_are_read_from_the_environment_then_dot_env_in_the_working_folder(
    memo_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SEC_EDGAR_CONTACT")
    monkeypatch.delenv("LISTINGLENS_CACHE_DIR")
    cache = memo_folder / "from-dot-env"
    Path(".env").write_text(
        f"SEC_EDGAR_CONTACT=dotenv@example.com\nLISTINGLENS_CACHE_DIR={cache}\n", "ascii"
    )
    settings = command._settings()
    assert (settings.sec_edgar_contact, settings.listinglens_cache_dir) == (
        "dotenv@example.com", cache
    )  # fmt: skip
    assert cache.is_dir() and settings.listinglens_anthropic_api_key is None


def test_no_key_exits_5_and_a_general_anthropic_key_is_never_used(
    memo_folder: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY_CANARY)
    assert ended(capsys, AGMH) == (text.EXIT_NO_KEY, [text.NO_KEY])


def test_an_output_folder_that_cannot_be_written_exits_7_before_any_call(
    memo_folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    Path("out").write_text("a file, not a folder")
    model = Model()
    code = command.main(
        [*AGMH, "--out", "out"], open_tools=broken(), model_source=model, now=fixed_clock
    )
    assert (code, capsys.readouterr().err.splitlines()) == (text.EXIT_FOLDER, [text.BAD_OUT])
    assert model.client is not None and model.client.calls == ()


def test_the_tools_failing_exits_4_without_a_cost_line(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    unknown = ("--cik", "1", "--listing-type", "continued", "--pathway", "traditional_ipo")
    cases: list[tuple[Sequence[str], OpenTools, str]] = [
        (unknown, in_process(tmp_path / "a"), text.TOOL_ERROR.format(tool="resolve_company")),
        (AGMH, swapped(tmp_path / "b", "resolve_company", None), text.TOOL_REFUSED.format(
            tool="resolve_company", field="<payload>", detail="it is not valid JSON")),
        (AGMH, other_server(), text.SERVER_STOPPED),
        (AGMH, broken(), text.SERVER_STOPPED),
        (AGMH, swapped(tmp_path / "c", "list_filings", '"<b>6-K</b>"'),
         text.NO_FACTS.format(name="IdentityRefused")),
    ]  # fmt: skip
    for argv, tools, line in cases:
        model = Model()
        assert ended(capsys, argv, tools, model) == (text.EXIT_TOOLS, [line])
        assert model.client is not None and model.client.calls == ()


def test_the_model_step_failing_exits_6_with_the_cost_line(
    memo_folder: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one = COST.format(d="0.04550750", t="12,141", n=1)
    two = COST.format(d="0.09101500", t="24,282", n=2)
    cases: list[tuple[Model, Budget | None, list[str]]] = [
        (Model(replies(None, StopReason.TRUNCATED)), None,
         [text.WRITER_FAILED.format(words="cut off at the output limit"), one]),
        (Model(replies("{}")), None,
         [text.REJECTED.format(rules="shape"), two]),
        (Model(replies("{}")), Budget(max_attempts=1, max_tokens=120_000,
                                      max_dollars=Decimal("1.00")),
         [text.BUDGET_STOP.format(cap="attempt"), one]),
        (Model(), Budget(max_attempts=2, max_tokens=1, max_dollars=Decimal("1.00")),
         [text.BUDGET_STOP.format(cap="token"), COST.format(d="0", t="0", n=0)]),
        (Model(), Budget(max_attempts=2, max_tokens=120_000, max_dollars=Decimal("0.01")),
         [text.BUDGET_STOP.format(cap="dollar"), COST.format(d="0", t="0", n=0)]),
        (Model(replies("{}")[1:]), None,
         [text.MODEL_FAILED.format(name="RecordingMissing"), COST.format(d="0", t="0", n=0)]),
    ]  # fmt: skip
    for index, (model, budget, lines) in enumerate(cases):
        monkeypatch.setattr(command, "BUDGET", budget or command.BUDGET)
        tools = in_process(tmp_path / str(index))
        assert ended(capsys, AGMH, tools, model) == (text.EXIT_MODEL, lines), index


def test_a_memo_folder_that_exists_or_cannot_be_written_saves_nothing_and_shows_the_cost(
    memo_folder: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one = COST.format(d="0.04550750", t="12,141", n=1)
    (Path("out") / "AGMH-20261122T120000Z").mkdir(parents=True)
    code = command.main(
        [*AGMH, "--out", "out"], open_tools=in_process(tmp_path / "a"), model_source=Model(),
        now=fixed_clock,
    )  # fmt: skip
    captured = capsys.readouterr()
    assert (code, captured.err.splitlines()) == (text.EXIT_FOLDER, [text.FOLDER_EXISTS, one])
    assert [p.name for p in Path("out").iterdir()] == ["AGMH-20261122T120000Z"]
    assert list((Path("out") / "AGMH-20261122T120000Z").iterdir()) == []
    (Path("out") / "AGMH-20261122T120000Z").rmdir()

    def refuse(*args: object, **kwargs: object) -> str:
        raise OSError(CONTACT)

    monkeypatch.setattr(tempfile, "mkdtemp", refuse)
    lines = [text.FOLDER_UNWRITABLE, one]
    assert ended(capsys, AGMH, in_process(tmp_path / "b"), Model()) == (text.EXIT_FOLDER, lines)


def test_a_crash_exits_1_naming_only_the_error_class(
    memo_folder: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def crash(*args: object) -> None:
        raise RuntimeError(CONTACT)

    monkeypatch.setattr(run, "record_of", crash)
    lines = [text.CRASH.format(name="RuntimeError"), COST.format(d="0.04550750", t="12,141", n=1)]
    assert ended(capsys, AGMH, in_process(tmp_path), Model()) == (text.EXIT_CRASH, lines)


def test_the_word_tables_cover_every_reason_and_every_cap() -> None:
    assert set(text.WRITER_WORDS) == {"refused", "truncated", "context_full", "empty"}
    assert set(text.CAP_WORDS) == {"attempts", "tokens", "dollars"}
    exits = [v for k, v in vars(text).items() if k.startswith("EXIT_")]
    assert sorted(exits) == [0, 1, 2, 3, 4, 5, 6, 7]
