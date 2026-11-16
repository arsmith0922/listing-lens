from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Annotated, Final, Literal, NoReturn

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from listinglens.core.errors import InputValidationError, RecordingInvalid
from listinglens.core.validation import summarize_validation_error
from listinglens.llm.fingerprint import FINGERPRINT_FORMAT, request_fingerprint
from listinglens.llm.ledger import Fingerprint
from listinglens.llm.models import CONFIG, ModelRequest, ModelResponse, StopReason

# The recorded model answer (D60): one JSON file holding a request, the answer it got and the
# input bound the client reported, found later by the request's fingerprint. A recording has no
# field for a header, a key or any transport detail. The loader is as strict as the price table
# (D58) and adds one rule that covers key order, indentation, ASCII, LF and the final newline at
# once: the file must equal exactly what recording_text writes from what it parsed.
RECORDING_FORMAT: Final = "llm-recording-v1"
MAX_RECORDING_BYTES = 1_048_576
MANIFEST_FILE = "manifest.json"
HAND_ID_PREFIX = "hand-"
Source = Literal["hand", "live"]
RecordedAt = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00$"),
]


def _request_from_json(value: object) -> object:
    if isinstance(value, dict) and isinstance(value.get("messages"), list):
        return {**value, "messages": tuple(value["messages"])}
    return value


def _response_from_json(value: object) -> object:
    if isinstance(value, dict) and isinstance(value.get("stop"), str):
        try:
            return {**value, "stop": StopReason(value["stop"])}
        except ValueError:
            raise ValueError("stop is not a known stop reason") from None
    return value


class Recording(BaseModel):
    model_config = CONFIG

    format: Literal["llm-recording-v1"]
    fingerprint_format: str
    fingerprint: Fingerprint
    source: Source
    recorded_at: RecordedAt
    bound: Annotated[int, Field(gt=0)]
    request: Annotated[ModelRequest, BeforeValidator(_request_from_json)]
    response: Annotated[ModelResponse, BeforeValidator(_response_from_json)]

    @model_validator(mode="after")
    def _the_parts_agree_and_keep_the_meters_promises(self) -> Recording:
        try:
            datetime.fromisoformat(self.recorded_at)
        except ValueError as exc:
            raise ValueError("recorded_at is not a real date and time") from exc
        if self.fingerprint_format != FINGERPRINT_FORMAT:
            raise ValueError("made under another fingerprint format")
        if self.fingerprint != request_fingerprint(self.request):
            raise ValueError("the fingerprint does not match the stored request")
        usage = self.response.usage
        if usage.prompt_tokens > self.bound:
            raise ValueError("the response used more input tokens than the bound")
        if usage.output_tokens > self.request.max_tokens:
            raise ValueError("the response used more output tokens than the limit")
        if self.response.served_model != self.request.model:
            raise ValueError("the response came from another model than the request named")
        request_id = self.response.request_id
        hand_id = request_id is None or request_id.startswith(HAND_ID_PREFIX)
        if (self.source == "hand") != hand_id:
            raise ValueError("the request id does not fit the source")
        return self


def make_recording(
    request: ModelRequest,
    *,
    bound: int,
    response: ModelResponse,
    source: Source,
    recorded_at: str,
) -> Recording:
    return Recording(
        format=RECORDING_FORMAT,
        fingerprint_format=FINGERPRINT_FORMAT,
        fingerprint=request_fingerprint(request),
        source=source,
        recorded_at=recorded_at,
        bound=bound,
        request=request,
        response=response,
    )


def recording_filename(purpose: str, fingerprint: str) -> str:
    """The purpose and the first twelve characters of the fingerprint; a colon, which the slug
    allows and Windows does not, is written as an underscore."""
    return f"{purpose.replace(':', '_')}-{fingerprint[:12]}.json"


def recording_text(recording: Recording) -> str:
    """The one text form of a recording: sorted keys, indent 2, ASCII, LF, one final newline."""
    document = recording.model_dump(mode="json")
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def manifest_entry(recording: Recording, text: str) -> dict[str, str]:
    return {
        "file": recording_filename(recording.request.purpose, recording.fingerprint),
        "fingerprint": recording.fingerprint,
        "model": recording.request.model,
        "purpose": recording.request.purpose,
        "recorded_at": recording.recorded_at,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source": recording.source,
    }


def write_recording(directory: Path, recording: Recording) -> dict[str, str]:
    """Write the exact bytes (never through a text mode, so no platform can change a newline)
    and return the manifest entry for them."""
    text = recording_text(recording)
    directory.mkdir(parents=True, exist_ok=True)
    name = recording_filename(recording.request.purpose, recording.fingerprint)
    (directory / name).write_bytes(text.encode("utf-8"))
    return manifest_entry(recording, text)


def write_manifest(directory: Path, entries: Sequence[Mapping[str, str]]) -> None:
    """Merge entries into the folder's manifest by file name (a new entry replaces the old one
    of its file, the others stay) and write it sorted by file, indent 2, LF only."""
    path = directory / MANIFEST_FILE
    existing: list[dict[str, str]] = json.loads(path.read_text("utf-8")) if path.exists() else []
    merged = {entry["file"]: dict(entry) for entry in existing}
    merged.update({entry["file"]: dict(entry) for entry in entries})
    text = json.dumps([merged[name] for name in sorted(merged)], indent=2, sort_keys=True)
    path.write_bytes(text.encode("utf-8"))


def _refuse_number(text: str) -> NoReturn:
    raise ValueError(f"a number with a decimal point or exponent ({text[:20]})")


def _refuse_constant(name: str) -> NoReturn:
    raise ValueError(f"{name[:20]} is not allowed")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key appears twice in one object")
    return dict(pairs)


def load_recording(source: Traversable) -> Recording:
    """Load and check one recording file. Any problem is RecordingInvalid naming the file and
    the field; the detail never echoes the request or the answer."""
    label = source.name
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise RecordingInvalid(label, "<read>", type(exc).__name__) from exc
    if len(raw) > MAX_RECORDING_BYTES:
        raise RecordingInvalid(label, "<size>", f"more than {MAX_RECORDING_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
        data = json.loads(
            text,
            parse_float=_refuse_number,
            parse_constant=_refuse_constant,
            object_pairs_hook=_no_duplicate_keys,
        )
    except RecursionError as exc:
        raise RecordingInvalid(label, "<json>", "nested too deeply") from exc
    except ValueError as exc:
        raise RecordingInvalid(label, "<json>", str(exc)[:200]) from exc
    try:
        recording = Recording.model_validate(data)
    except ValidationError as exc:
        field, detail = summarize_validation_error("Recording", exc)
        raise RecordingInvalid(label, field, detail) from exc
    except InputValidationError as exc:
        raise RecordingInvalid(label, exc.field, str(exc.value)[:200]) from exc
    if recording_text(recording) != text:
        raise RecordingInvalid(label, "<format>", "not in the canonical form of recording_text")
    if label != recording_filename(recording.request.purpose, recording.fingerprint):
        raise RecordingInvalid(label, "<name>", "the file name does not match its request")
    return recording


def load_recordings(directory: Traversable) -> tuple[Recording, ...]:
    """Load every recording in a scenario folder, in file-name order. The folder holds
    recordings and its manifest only; a stray file or two recordings of one request is refused."""
    try:
        entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
    except OSError as exc:
        raise RecordingInvalid(directory.name, "<directory>", type(exc).__name__) from exc
    found: dict[str, Recording] = {}
    for entry in entries:
        if entry.name == MANIFEST_FILE:
            continue
        if not entry.is_file() or not entry.name.endswith(".json"):
            raise RecordingInvalid(entry.name, "<file>", "a scenario folder holds recordings only")
        recording = load_recording(entry)
        if recording.fingerprint in found:
            raise RecordingInvalid(entry.name, "fingerprint", "another recording has this one")
        found[recording.fingerprint] = recording
    return tuple(found.values())
