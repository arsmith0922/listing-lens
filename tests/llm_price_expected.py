"""The independent copy of the price table and builders for malformed tables (D58).

The copy below is typed by hand from Anthropic's pricing page (read 2026-11-15) and never read
from price_table.json, so a price changed without a decision fails a test."""

from __future__ import annotations

import json
from pathlib import Path

PAGE = "https://platform.claude.com/docs/en/about-claude/pricing"
RATE_NAMES = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"

HAIKU_LOW: dict[str, object] = {
    "label": "Claude Haiku 5.5 (for prompts up to 100,000 tokens)",
    "up_to_prompt_tokens": 100000,
    "input": "0.10",
    "output": "0.50",
    "cache_write_5m": "0.125",
    "cache_write_1h": "0.20",
    "cache_read": "0.01",
}
HAIKU_HIGH: dict[str, object] = {
    "label": "Claude Haiku 5.5 (for prompts over 100,000 tokens)",
    "up_to_prompt_tokens": None,
    "input": "0.50",
    "output": "2.50",
    "cache_write_5m": "0.625",
    "cache_write_1h": "1.00",
    "cache_read": "0.05",
}
SONNET_ONLY: dict[str, object] = {
    "label": "Claude Sonnet 5.5",
    "up_to_prompt_tokens": None,
    "input": "2.00",
    "output": "10.00",
    "cache_write_5m": "2.50",
    "cache_write_1h": "4.00",
    "cache_read": "0.10",
}


def band(base: dict[str, object] | None = None, /, **overrides: object) -> dict[str, object]:
    return {**(base or HAIKU_LOW), **overrides}


def entry(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "model": HAIKU,
        "source_url": PAGE,
        "checked_on": "2026-11-15",
        "checked_by": "Austin Smith",
        "bands": [band(HAIKU_LOW), band(HAIKU_HIGH)],
    }
    return {**fields, **overrides}


def sonnet_entry(**overrides: object) -> dict[str, object]:
    return entry(model=SONNET, bands=[band(SONNET_ONLY)], **overrides)


def table(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "format": "llm-price-table-v1",
        "table_version": 1,
        "currency": "USD",
        "unit": "per_million_tokens",
        "models": [entry(), sonnet_entry()],
    }
    return {**fields, **overrides}


def expected_document() -> dict[str, object]:
    """The whole file as it must read when parsed with plain json."""
    return table()


def drop(mapping: dict[str, object], *keys: str) -> dict[str, object]:
    return {key: value for key, value in mapping.items() if key not in keys}


def write_text(directory: Path, text: str) -> Path:
    path = directory / "price_table.json"
    path.write_text(text, encoding="utf-8")
    return path


def write_table(directory: Path, document: object) -> Path:
    return write_text(directory, json.dumps(document))
