from __future__ import annotations

import hashlib

from listinglens.llm.models import ModelRequest
from listinglens.llm.schema import canonical_json

# The identity of a request (D57), used to find its recording. Eight fields decide it: the format
# version, the model, the system text, its cache lifetime, the messages, the schema text, the
# output limit and the effort. The purpose and the format's name are labels and are left out, so
# renaming a call site never breaks a replay.
FINGERPRINT_FORMAT = "llm-request-v1"


def canonical_request(request: ModelRequest) -> str:
    return canonical_json(
        {
            "format": FINGERPRINT_FORMAT,
            "model": request.model,
            "system": request.system,
            "system_cache": request.system_cache,
            "messages": [{"role": m.role, "text": m.text} for m in request.messages],
            "schema": request.response_format.schema_text,
            "max_tokens": request.max_tokens,
            "effort": request.effort,
        }
    )


def request_fingerprint(request: ModelRequest) -> str:
    return hashlib.sha256(canonical_request(request).encode("utf-8")).hexdigest()
