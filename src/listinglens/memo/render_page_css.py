from __future__ import annotations

import base64
import hashlib
from typing import Final

# The page's style (D73), approved by Austin from the preview built from run 2's agmh.one draft and
# kept byte for byte: one line of the approved text to each item below (a long line is written as
# adjacent pieces, which Python joins with nothing between them), joined by LF, with a final LF.
# The style element holds exactly this text, and the page's Content-Security-Policy allows a style
# only by its SHA-256, so the page refuses any style it does not carry.
_LINES: Final = (
    ":root { --ink: #1d1b18; --quiet: #6b655c; --rule: #d9d3c7; --accent: #1f3a5f; "
    "--paper: #ffffff; }",
    "* { box-sizing: border-box; }",
    "html { background: var(--paper); }",
    "body { margin: 0 auto; max-width: 40rem; padding: 3.5rem 1.5rem 4rem; color: var(--ink);",
    '  font-family: Charter, "Bitstream Charter", "Sitka Text", Cambria, "Iowan Old Style", '
    "Georgia, serif;",
    "  font-size: 1.0625rem; line-height: 1.6; font-kerning: normal; "
    "text-rendering: optimizeLegibility; }",
    "header { border-bottom: 1px solid var(--rule); padding-bottom: 1.5rem; "
    "margin-bottom: 0.5rem; }",
    ".kicker { font-variant-caps: all-small-caps; letter-spacing: 0.08em; color: var(--quiet); "
    "margin: 0 0 0.4rem; font-size: 1rem; }",
    "h1 { font-size: 2rem; line-height: 1.2; font-weight: 600; margin: 0 0 0.5rem; "
    "color: var(--accent); letter-spacing: 0.005em; }",
    ".dek { margin: 0; color: var(--quiet); }",
    ".about { font-size: 0.9375rem; font-style: italic; color: var(--quiet); "
    "margin: 1.25rem 0 0; }",
    ".about p { margin: 0 0 0.6rem; }",
    "section { border-top: 1px solid var(--rule); padding-top: 1.1rem; margin-top: 1.75rem; }",
    "header + section { border-top: 0; }",
    "h2 { font-size: 1.0625rem; font-weight: 600; font-variant-caps: all-small-caps; "
    "letter-spacing: 0.1em; color: var(--accent); margin: 0 0 0.6rem; }",
    "p { margin: 0 0 0.8rem; hyphens: auto; }",
    ".note { font-size: 0.9375rem; font-style: italic; color: var(--quiet); }",
    ".reading { font-style: italic; padding-left: 1.25rem; }",
    ".reading .label { font-style: normal; font-variant-caps: all-small-caps; "
    "letter-spacing: 0.08em; color: var(--quiet); margin-right: 0.35rem; }",
    ".reading .term { font-style: italic; }",
    ".term { font-variant-caps: all-small-caps; letter-spacing: 0.04em; }",
    ".num { font-variant-numeric: lining-nums tabular-nums; white-space: nowrap; }",
    ".mark { font-size: 0.68em; line-height: 0; margin-left: 0.12em; "
    "font-variant-numeric: lining-nums; }",
    ".mark a, .sources a { color: inherit; text-decoration: none; }",
    ".mark a:hover, .sources a:hover { text-decoration: underline; }",
    ".sources ol { padding-left: 1.6rem; margin: 0; font-size: 0.875rem; line-height: 1.5; "
    "color: var(--quiet); }",
    ".sources li { margin-bottom: 0.3rem; overflow-wrap: anywhere; }",
    "dl { margin: 0; font-size: 0.9375rem; }",
    "dt { margin-top: 0.5rem; }",
    "dd { margin: 0 0 0 1.25rem; color: var(--quiet); }",
    "footer { border-top: 1px solid var(--rule); margin-top: 2.5rem; padding-top: 1rem; "
    "font-size: 0.8125rem; color: var(--quiet); line-height: 1.5; }",
    "footer p { margin: 0 0 0.3rem; }",
    "@media print {",
    "  html, body { background: #fff; }",
    "  body { max-width: none; padding: 0; font-size: 10.5pt; }",
    "  section { break-inside: avoid-page; }",
    '  .sources a::after { content: " " attr(href); }',
    "}",
)
PAGE_CSS: Final = "\n".join(_LINES) + "\n"


def style_hash(css: str = PAGE_CSS) -> str:
    """The CSP source for the style: sha256- and the base64 of the SHA-256 of its ASCII bytes."""
    digest = hashlib.sha256(css.encode("ascii")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")
