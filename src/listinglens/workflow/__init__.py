"""The steps that sit between the memo's pure layer and the model (D68), and the record of a memo
(D72). A step takes a model client (normally the run meter) and returns typed results or a typed
error. Nothing here opens a connection, reads the environment, reads a clock or prints."""

from __future__ import annotations

from listinglens.workflow.record import MemoRecord, build_record, provenance
from listinglens.workflow.verify import check_record
from listinglens.workflow.writer import WriterConfig, Written, write_narrative

__all__ = [
    "MemoRecord",
    "WriterConfig",
    "Written",
    "build_record",
    "check_record",
    "provenance",
    "write_narrative",
]
