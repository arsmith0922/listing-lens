from __future__ import annotations

from listinglens.memo.render_model import READING_LABEL, RenderedClaim, RenderedMemo

# The plain-text projection of a rendered memo (D71): the form the golden tests pin and the console
# will show. It carries the scope note and the disclosure wherever the memo is shown. The scope
# note, a blank line, the AI disclosure, a blank line; then each section that has claims, its
# heading on a line of its own (under Exchange status, the exchange note first, then a blank line),
# one line for each claim, which an inference begins with the reading label and which ends in a
# space and its source marks in square brackets, and a blank line after the section; then the line
# Sources and one line for each source, "{n}. {label}", each followed by its links one to a line
# indented four spaces. Terms are plain words. No wrapping, LF line endings, a final newline, ASCII
# only.
INDENT = "    "


def _line(claim: RenderedClaim) -> str:
    label = READING_LABEL if claim.kind == "inference" else ""
    return label + "".join(segment.text for segment in claim.segments) + f" [{claim.marks}]"


def to_text(memo: RenderedMemo) -> str:
    lines = [memo.scope_note.text, "", memo.ai_disclosure.text, ""]
    for section in memo.sections:
        if not section.claims:
            continue
        lines.append(section.heading)
        if section.name == "exchange_status":
            lines += [memo.exchange_note.text, ""]
        lines += [_line(claim) for claim in section.claims]
        lines.append("")
    lines.append("Sources")
    for source in memo.sources:
        lines.append(f"{source.number}. {source.label}")
        lines += [INDENT + link for link in source.links]
    return "\n".join(lines) + "\n"
