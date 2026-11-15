from __future__ import annotations

from typing import Protocol

from listinglens.llm.models import ModelRequest, ModelResponse


class ModelClient(Protocol):
    """The one way anything in ListingLens talks to a model (D57). Both methods block on the
    caller's thread (D42); there is no async, no streaming and no pool in the interface. The
    real client is an adapter in its own file, the fake replays recordings, and the run meter
    wraps either, so the reader and the memo writer cannot tell them apart."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Send the request and return the response. A refusal or a cut-off answer comes back as
        a typed stop; a missing key, a transport failure or an unusable response is an error."""
        ...

    def input_token_bound(self, request: ModelRequest) -> int:
        """An upper bound on the input tokens of the request (never below the true count). The
        budget needs a bound, not an exact figure: a provider with a counting endpoint may return
        its count, and one without may return a conservative local bound."""
        ...
