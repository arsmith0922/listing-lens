from __future__ import annotations

from collections.abc import Iterable

from listinglens.core.errors import RecordingInvalid, RecordingMissing
from listinglens.llm.fingerprint import request_fingerprint
from listinglens.llm.models import ModelRequest, ModelResponse
from listinglens.llm.recording import Recording

# The fake client (D60): a ModelClient that replays recordings, so the reader, the memo writer
# and the run meter cannot tell it from the real adapter. It takes loaded recordings and does no
# I/O of its own. A request is found by its fingerprint alone (the purpose is a label, D57), a
# miss in either method is RecordingMissing and there is never a default answer.


class FakeModelClient:
    def __init__(self, recordings: Iterable[Recording]) -> None:
        self._by_fingerprint: dict[str, Recording] = {}
        for recording in recordings:
            if recording.fingerprint in self._by_fingerprint:
                raise RecordingInvalid("<set>", "fingerprint", "two recordings have one request")
            self._by_fingerprint[recording.fingerprint] = recording
        self._calls: list[tuple[str, str]] = []

    @property
    def calls(self) -> tuple[tuple[str, str], ...]:
        """Every call answered so far as ("bound" or "complete", fingerprint), in order."""
        return tuple(self._calls)

    def unused(self) -> tuple[str, ...]:
        """The fingerprints of the recordings no call has asked for, in either method, sorted.
        A scenario that ends with a non-empty list holds a stale recording."""
        asked = {fingerprint for _, fingerprint in self._calls}
        return tuple(sorted(set(self._by_fingerprint) - asked))

    def input_token_bound(self, request: ModelRequest) -> int:
        return self._find(request, "bound").bound

    def complete(self, request: ModelRequest) -> ModelResponse:
        return self._find(request, "complete").response

    def _find(self, request: ModelRequest, kind: str) -> Recording:
        fingerprint = request_fingerprint(request)
        recording = self._by_fingerprint.get(fingerprint)
        if recording is None:
            raise RecordingMissing(fingerprint, request.purpose)
        self._calls.append((kind, fingerprint))
        return recording
