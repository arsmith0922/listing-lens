"""Support for the drafting script's tests (D68): the script loaded by path, and a scripted writer
client that answers every request with a draft built from the facts the request carries, so the
script, the writer step and the checker run together with no model and no network. Nothing here
calls a model, and the script is only ever run through its keyword-only test seams."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from types import ModuleType

from listinglens.core.config import Settings
from listinglens.core.errors import UnpricedUsage
from listinglens.llm.models import ModelRequest, ModelResponse, StopReason
from listinglens.llm.usage import Usage
from listinglens.memo import narrative as n
from listinglens.memo.narrative import Claim, Narrative, Section
from listinglens.memo.prompt import user_turn
from listinglens.memo.view import WriterView
from tests.test_memo_checker_sets import section_of, text_for

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "draft_memos.py"
CANARY = "canaryqzv"
FIRST, RETRY = "memo.writer", "memo.writer_retry"


@cache
def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("draft_memos", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FLAWS = {
    "digit": f"{CANARY} was 12 here.",
    "lists": f"{CANARY} had millions, a price target and delisting is certain.",
}


def draft_text(view: WriterView, *, flaw: str | None = None) -> str:
    """A draft with one claim for each primary fact, each text opening with the canary, which
    passes the checker; with a flaw, one more claim that does not: a digit, or words from each of
    the three lists."""
    claims: dict[str, list[Claim]] = {name: [] for name in n.SECTIONS}
    for fact_id in view.primary:
        text = f"{CANARY} " + text_for(view.kinds[fact_id], fact_id)
        claims[section_of(view, fact_id)].append(
            Claim(kind="fact", text=text, refs=(fact_id,), basis=())
        )
    if flaw is not None:
        first = view.primary[0]
        extra = Claim(kind="fact", text=FLAWS[flaw], refs=(first,), basis=())
        claims[section_of(view, first)].append(extra)
    draft = Narrative(**{name: Section(claims=tuple(found)) for name, found in claims.items()})
    return draft.model_dump_json()


def usage() -> Usage:
    return Usage(
        input_tokens=8_000,
        output_tokens=2_000,
        cache_write_5m_tokens=0,
        cache_write_1h_tokens=0,
        cache_read_tokens=0,
        thinking_tokens=500,
    )


def reply(
    request: ModelRequest, text: str, stop: StopReason = StopReason.COMPLETED
) -> ModelResponse:
    return ModelResponse(
        text="" if stop is StopReason.REFUSED else text,
        stop=stop,
        usage=usage(),
        served_model=request.model,
        request_id="req_draft_" + request.purpose.replace(".", "_"),
    )


class WriterClient:
    """A ModelClient that finds the draft a request is about by its facts, and plays what it was
    told for that draft: "pass" (the default), "retry" (a first draft with a digit, then a good
    one),
    "lists" (a first draft with list words, then a good one), "reject" (two drafts with a digit),
    "refused", "truncated", "error" (a typed model error) or "retry_error" (a first draft with a
    digit, then a typed model error on the retry)."""

    def __init__(self, drafts: Mapping[str, WriterView], plan: Mapping[str, str] | None = None):
        self.by_user = {user_turn(view): name for name, view in drafts.items()}
        self.views = dict(drafts)
        self.plan = dict(plan or {})
        self.bound = 40_000
        self.log: list[tuple[str, str]] = []
        self.requests: list[ModelRequest] = []
        self.responses: list[ModelResponse] = []

    def name_of(self, request: ModelRequest) -> str:
        return self.by_user[request.messages[0].text]

    def input_token_bound(self, request: ModelRequest) -> int:
        self.log.append(("bound", request.purpose))
        return self.bound

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.log.append(("complete", request.purpose))
        self.requests.append(request)
        name = self.name_of(request)
        view, how = self.views[name], self.plan.get(name, "pass")
        retry = request.purpose == RETRY
        if how == "error" or (how == "retry_error" and retry):
            raise UnpricedUsage("scripted")
        if how == "refused":
            return reply(request, "", StopReason.REFUSED)
        if how == "truncated":
            return reply(request, draft_text(view)[:40], StopReason.TRUNCATED)
        flaw = {"retry": "digit", "retry_error": "digit", "lists": "lists", "reject": "digit"}.get(
            how
        )
        response = reply(
            request, draft_text(view, flaw=None if retry and how != "reject" else flaw)
        )
        self.responses.append(response)
        return response


def run(module: ModuleType, client: WriterClient, out: Path) -> int:
    def factory(settings: Settings) -> WriterClient:
        assert settings.listinglens_anthropic_api_key is not None
        return client

    try:
        module.main((), client_source=factory, output_dir=out)
    except SystemExit as exc:
        assert isinstance(exc.code, int)
        return exc.code
    return 0
