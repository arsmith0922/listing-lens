"""The memo command with tracing (D76), end to end in process with fixed clocks and ids and the
Langfuse client over a recording transport: the exact request of three runs, D74's output to the
byte with the keys blank, one fixed line for each way a trace is refused or not sent with the exit
code and the files unchanged, a deadline, one guard around opening, building and sending, no secret
but in the Authorization header, nothing sent after an early stop, and no record byte moved."""

from __future__ import annotations

import base64
import hashlib
import threading
import time
from pathlib import Path

import httpx
import pytest

from listinglens.tracing.config import TracingSettings
from listinglens.tracing.tracer import Build, SendResult, Tracer
from listinglens.workflow import command, trace
from listinglens.workflow import command_text as text
from listinglens.workflow.writer import parse_draft
from tests import command_support as cs
from tests import trace_support as ts
from tests.command_support import AGMH, Model, fixed_clock, in_process, memo_folder
from tests.test_workflow_command import assert_the_oracle
from tests.trace_support import PUBLIC, SECRET, URL, Recorder, run_traced, set_keys

__all__ = ["memo_folder"]
FAILED = ("--cik", "1", "--listing-type", "continued", "--pathway", "traditional_ipo")
TOOL_LINE = "No memo: the tool resolve_company returned an error."
SENT = "Trace sent to Langfuse: 00000000000000000000000000000001"
AUTH = "Basic " + base64.b64encode(f"{PUBLIC}:{SECRET}".encode()).decode("ascii")
KEYS = (
    "Trace not sent: only one of LISTINGLENS_LANGFUSE_PUBLIC_KEY and "
    "LISTINGLENS_LANGFUSE_SECRET_KEY is set."
)
HOST = "Trace not sent: LISTINGLENS_LANGFUSE_HOST is not one of Langfuse's cloud hosts."
TIMEOUT = "Trace not sent: Langfuse did not answer in time."
CONNECTION = "Trace not sent: the connection to Langfuse failed."
ONE = "423d2238be0a23b826bda2c12a3cca0b04d73a0124b868fa22768a0ade430a0e"
RETRIED = "ec485eccf2da00f5ece766fd61b4b7465067b04fb3a11089080020ead01359a2"
FAILURE = "1f94cf558ff31808eab359e2dd826c9e6c2f8551028d0d6813a278c7464582f3"


def _saved(folder: Path) -> dict[str, bytes]:
    (saved,) = (folder / "out").iterdir()
    return {p.name: p.read_bytes() for p in sorted(saved.iterdir())}


@pytest.mark.parametrize(
    ("run", "sha", "size"), [("one", ONE, 49_574), ("retried", RETRIED, 97_044),
                             ("failed", FAILURE, 3_511)],
)  # fmt: skip
def test_the_exact_request_of_a_one_attempt_a_retried_and_a_failed_run(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch, run: str, sha: str, size: int,
) -> None:  # fmt: skip
    set_keys(monkeypatch)
    model = Model(ts.retried_replies()) if run == "retried" else None
    traced = run_traced(capsys, monkeypatch, tmp_path, FAILED if run == "failed" else AGMH,
                        model=model)  # fmt: skip
    (request,) = traced.recorder.requests
    assert (request.method, str(request.url)) == ("POST", URL)
    assert request.headers["authorization"] == AUTH
    assert request.headers["x-langfuse-ingestion-version"] == "4"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["user-agent"] == "ListingLens/0.1.0"
    assert (hashlib.sha256(request.content).hexdigest(), len(request.content)) == (sha, size)
    if run == "failed":
        assert (traced.code, traced.out) == (text.EXIT_TOOLS, "")
        assert traced.err.splitlines() == [TOOL_LINE, SENT]
        return
    assert (traced.code, traced.err) == (0, "") and traced.out.endswith(f"\n{SENT}\n")
    if run == "one":
        assert_the_oracle(memo_folder / "out", traced.out.removesuffix(f"{SENT}\n"))
    else:
        assert b'"attempts":2' in _saved(memo_folder)["record.json"]


@pytest.mark.parametrize("injected", [True, False])
def test_blank_keys_send_nothing_and_print_exactly_what_d74_prints(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], injected: bool
) -> None:
    recorder = Recorder()
    code = command.main(
        [*AGMH, "--out", "out"], open_tools=in_process(tmp_path), model_source=Model(),
        now=fixed_clock, tracer_source=ts.tracer_over(recorder) if injected else None,
    )  # fmt: skip
    captured = capsys.readouterr()
    assert (code, captured.err, recorder.requests) == (0, "", [])
    assert_the_oracle(memo_folder / "out", captured.out)


def test_the_general_langfuse_names_are_never_used(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    """Change A: keys under Langfuse's general names, in the environment and in the working
    folder's .env, belong to another project; the command sends nothing and prints what D74 does."""
    for variable, value in zip(
        ts.GENERAL, (PUBLIC, SECRET, "https://cloud.langfuse.com"), strict=True
    ):
        monkeypatch.setenv(variable, value)
    (memo_folder / ".env").write_text(
        f"LANGFUSE_PUBLIC_KEY={PUBLIC}\nLANGFUSE_SECRET_KEY={SECRET}\n"
    )
    traced = run_traced(capsys, monkeypatch, tmp_path, AGMH)
    assert (traced.code, traced.err, traced.recorder.requests) == (0, "", [])
    assert_the_oracle(memo_folder / "out", traced.out)


@pytest.mark.parametrize(
    ("public", "secret", "host", "line"),
    [
        (PUBLIC, None, None, KEYS),
        (None, SECRET, None, KEYS),
        (PUBLIC, SECRET, "http://us.cloud.langfuse.com", HOST),
        (PUBLIC, SECRET, "https://us.cloud.langfuse.com.example.com", HOST),
        (PUBLIC, SECRET, "https://us.cloud.langfuse.com/api", HOST),
    ],
)
def test_one_key_or_a_host_off_the_list_sends_nothing_and_changes_nothing_else(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch, public: str | None, secret: str | None, host: str | None,
    line: str,
) -> None:  # fmt: skip
    set_keys(monkeypatch, public, secret, host)
    traced = run_traced(capsys, monkeypatch, tmp_path, AGMH)
    assert (traced.code, traced.err, traced.recorder.requests) == (0, f"{line}\n", [])
    assert_the_oracle(memo_folder / "out", traced.out)


@pytest.mark.parametrize(
    ("recorder", "line"),
    [
        (Recorder(error=httpx.ReadTimeout("slow")), TIMEOUT),
        (Recorder(error=httpx.ConnectError("refused")), CONNECTION),
        (Recorder(404), "Trace not sent: Langfuse answered HTTP 404."),
        (Recorder(500), "Trace not sent: Langfuse answered HTTP 500."),
        (Recorder(307, headers={"location": URL}), "Trace not sent: Langfuse answered HTTP 307."),
    ],
)
def test_a_failed_send_changes_neither_the_exit_code_nor_the_files(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch, recorder: Recorder, line: str,
) -> None:  # fmt: skip
    set_keys(monkeypatch)
    traced = run_traced(capsys, monkeypatch, tmp_path, AGMH, recorder=recorder)
    assert (traced.code, traced.err, len(recorder.requests)) == (0, f"{line}\n", 1)
    assert_the_oracle(memo_folder / "out", traced.out)
    recorder.requests.clear()
    failed = run_traced(capsys, monkeypatch, tmp_path, FAILED, recorder=recorder)
    assert (failed.code, failed.err.splitlines()) == (text.EXIT_TOOLS, [TOOL_LINE, line])


class _Timed:
    def __init__(self, inner: Tracer, took: list[float]) -> None:
        self.inner, self.took = inner, took

    def send(self, build: Build) -> SendResult | None:
        started = time.monotonic()
        try:
            return self.inner.send(build)
        finally:
            self.took.append(time.monotonic() - started)


def test_the_deadline_holds_the_command_no_longer_than_it(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    """Change B: a Langfuse that never answers costs the run the deadline (here 0.2 seconds) and
    the timed-out line; the hold is released after 5 seconds, so without a deadline it is longer."""
    set_keys(monkeypatch)
    hold, took = threading.Event(), list[float]()
    release = threading.Timer(5.0, hold.set)
    release.start()
    opened = ts.tracer_over(Recorder(hold=hold), deadline=0.2)
    try:
        code = command.main(
            [*AGMH, "--out", "out"], open_tools=in_process(tmp_path), model_source=Model(),
            now=fixed_clock, tracer_source=lambda s: _Timed(opened(s), took),
        )  # fmt: skip
    finally:
        hold.set()
        release.cancel()
    captured = capsys.readouterr()
    assert (code, captured.err) == (0, TIMEOUT + "\n")
    assert_the_oracle(memo_folder / "out", captured.out)
    assert len(took) == 1 and took[0] < 2.0, f"the send held the run {took[0]:.1f} s"


def _raise(*_: object, **__: object) -> TracingSettings:
    raise ValueError(f"{PUBLIC} {cs.CONTACT}")


@pytest.mark.parametrize("where", ["encode", "tracer", "record"])
def test_a_trace_that_cannot_be_built_changes_nothing(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch, where: str,
) -> None:  # fmt: skip
    """Changes C and E: anything that goes wrong in opening the tracer, building the trace or
    sending it is one line naming the class only, a trace that disagrees with the record among
    them, and none changes the exit code, the lines before it or the files."""
    set_keys(monkeypatch)
    if where == "tracer":
        monkeypatch.setattr(command, "TracingSettings", _raise)
    elif where == "encode":
        monkeypatch.setattr(trace, "encode", _raise)
    else:  # the retried run's first findings recomputed as none: not the record's
        monkeypatch.setattr(trace, "parse_draft", lambda t, v: (parse_draft(t, v)[0], ()))
    name = "RecordInvalid" if where == "record" else "ValueError"
    line = f"Trace not sent: an unexpected error ({name})."
    model = Model(ts.retried_replies()) if where == "record" else None
    traced = run_traced(capsys, monkeypatch, tmp_path, AGMH, model=model)
    assert (traced.code, traced.err, traced.recorder.requests) == (0, f"{line}\n", [])
    if where == "record":
        assert b'"attempts":2' in _saved(memo_folder)["record.json"]
        return
    assert_the_oracle(memo_folder / "out", traced.out)
    failed = run_traced(capsys, monkeypatch, tmp_path, FAILED)
    assert (failed.code, failed.err.splitlines()) == (text.EXIT_TOOLS, [TOOL_LINE, line])


@pytest.mark.parametrize("argv", [AGMH, FAILED])
def test_no_secret_reaches_the_body_the_lines_or_the_files(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch, argv: tuple[str, ...],
) -> None:  # fmt: skip
    set_keys(monkeypatch)
    monkeypatch.setenv("LISTINGLENS_ANTHROPIC_API_KEY", cs.KEY_CANARY)
    traced = run_traced(capsys, monkeypatch, tmp_path, argv)
    (request,) = traced.recorder.requests
    files = b"".join(_saved(memo_folder).values()) if argv == AGMH else b""
    canaries = (cs.KEY_CANARY, cs.CONTACT, PUBLIC, SECRET, AUTH.removeprefix("Basic "))
    for place in (request.content, traced.out.encode(), traced.err.encode(), files):
        leaked = [i for i, c in enumerate(canaries) if c.encode() in place]
        assert leaked == [], "a secret reached the body, a line or a file"
    headers = [(k, v) for k, v in request.headers.raw if k.lower() != b"authorization"]
    leaked = [i for i, c in enumerate(canaries) if any(c.encode() in v for _, v in headers)]
    assert leaked == [], "a secret reached a header other than Authorization"
    assert request.headers["authorization"] == AUTH


@pytest.mark.parametrize(
    ("argv", "setup", "code"),
    [
        (("--cik", "x", "--listing-type", "continued", "--pathway", "traditional_ipo"), "", 2),
        (AGMH, "contact", 3),
        (AGMH, "key", 5),
        (AGMH, "folder", 7),
    ],
)
def test_runs_that_stop_early_send_nothing(
    memo_folder: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    argv: tuple[str, ...], setup: str, code: int,
) -> None:  # fmt: skip
    set_keys(monkeypatch)
    if setup == "contact":
        monkeypatch.delenv("SEC_EDGAR_CONTACT")
    if setup == "folder":
        Path("out").write_text("a file, not a folder")
    recorder = Recorder()
    ended = command.main(
        [*argv, "--out", "out"], open_tools=cs.broken(), now=fixed_clock,
        model_source=None if setup == "key" else Model(), tracer_source=ts.tracer_over(recorder),
        trace_clock=ts.StepClock(), trace_ids=ts.CountIds(),
    )  # fmt: skip
    captured = capsys.readouterr()
    assert (ended, captured.out, recorder.requests) == (code, "", [])
    assert len(captured.err.splitlines()) == 1 and "Trace" not in captured.err


def test_tracing_changes_no_record_byte(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    plain, traced = Model(ts.retried_replies()), Model(ts.retried_replies())
    command.main([*AGMH, "--out", "plain"], open_tools=in_process(tmp_path / "a"),
                 model_source=plain, now=fixed_clock)  # fmt: skip
    set_keys(monkeypatch)
    recorder = Recorder()
    command.main([*AGMH, "--out", "traced"], open_tools=in_process(tmp_path / "b"),
                 model_source=traced, now=fixed_clock, tracer_source=ts.tracer_over(recorder),
                 trace_clock=ts.StepClock(), trace_ids=ts.CountIds())  # fmt: skip
    capsys.readouterr()
    (a,), (b,) = (memo_folder / "plain").iterdir(), (memo_folder / "traced").iterdir()
    files = [{p.name: p.read_bytes() for p in folder.iterdir()} for folder in (a, b)]
    assert files[0] == files[1] and len(files[0]) == 3
    assert plain.client is not None and traced.client is not None
    assert plain.client.calls == traced.client.calls and len(recorder.requests) == 1
