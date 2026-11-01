from __future__ import annotations

from mcp_types import CallToolResult, TextContent
from pydantic import BaseModel

# A tool result with both payloads (D47): the structured content, and the same data as compact
# JSON text for hosts that read only text. The SDK's own text copy is indented, which is about a
# third larger for no reader's benefit.
#
# structured_content is the Python-mode dump on purpose. When a tool returns a CallToolResult
# under Annotated[CallToolResult, Model] the SDK validates structured_content against Model in
# Python mode, and these models are strict, so dates and tuples must still be dates and tuples;
# the SDK then serializes them to the JSON the client receives (ISO dates, arrays).


def to_result(model: BaseModel) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=model.model_dump_json(by_alias=True))],
        structured_content=model.model_dump(mode="python", by_alias=True),
    )
